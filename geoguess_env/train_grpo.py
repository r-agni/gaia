"""
GeoGuess GRPO training script.

Uses TRL GRPOTrainer and computes environment reward by executing parsed
completions against the GeoGuess OpenEnv endpoint.
"""
from __future__ import annotations

import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import List

from datasets import Dataset


_AUTO_FINALIZE_TOOLS = ("terrain_analysis", "sun_angle", "language_detection")


def _int_env(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _num_generations(default: int) -> int:
    # GRPO needs grouped generations for stable advantage normalization.
    # Values < 2 can yield degenerate std/advantage behavior.
    return max(_int_env("NUM_GENERATIONS", default), 2)


def load_geoguess_dataset(path: str = "data/training_1k.jsonl", limit: int = 0) -> Dataset:
    """Load training JSONL and map rows to prompt records."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            prompt = (
                "Round 1: Identify the location shown.\n"
                f"Initial scene: {d.get('initial_scene_description', 'A road through an unknown landscape.')}\n"
                "Available tools: globe_view, street_view, terrain_analysis, "
                "weather, sun_angle, building_style, language_detection\n"
                "Tool budget: 7 steps. Max guesses: 2.\n"
                "Submit a tool call or a guess in JSON format."
            )
            records.append(
                {
                    "location_id": d["location_id"],
                    "prompt": prompt,
                    "country_code": d.get("country_code", ""),
                    "region": d.get("region", ""),
                }
            )
            if limit > 0 and len(records) >= limit:
                break
    return Dataset.from_list(records)


def _parse_multi_turn(text: str):
    """Parse a sequence of GeoGuessAction payloads from model output."""
    from agents.output_parser import parse_llm_actions
    from geoguess.models import GeoGuessAction

    actions = parse_llm_actions(text)
    if not actions:
        actions = [
            GeoGuessAction(
                action_type="guess",
                guess_lat=20.0,
                guess_lon=15.0,
                reasoning="parse failure fallback",
            )
        ]
    return actions


def _auto_finalize_action(obs, finalize_steps: int):
    """Produce a deterministic non-degenerate action to finish truncated rollouts."""
    from geoguess.models import GeoGuessAction

    seen_tools = {
        str(tr.get("tool_name", "")).strip().lower()
        for tr in (obs.tool_results or [])
        if isinstance(tr, dict)
    }

    # Gather at least some evidence if budget permits, reducing lazy-guess flags.
    if obs.steps_remaining > obs.guesses_remaining:
        for tool_name in _AUTO_FINALIZE_TOOLS:
            if tool_name not in seen_tools:
                return GeoGuessAction(
                    action_type="tool_call",
                    tool_name=tool_name,
                    reasoning="auto-finalize: gather minimum evidence before guessing",
                )

    # If a previous guess exists, nudge from it so repeats are avoided.
    if obs.guesses:
        last = obs.guesses[-1]
        try:
            base_lat = float(last.get("lat", 20.0))
            base_lon = float(last.get("lon", 15.0))
        except Exception:
            base_lat = 20.0
            base_lon = 15.0
        lat = max(-90.0, min(90.0, base_lat + (((finalize_steps % 5) - 2) * 0.9)))
        lon = max(-180.0, min(180.0, base_lon + ((((finalize_steps + 2) % 7) - 3) * 1.1)))
    else:
        # Deterministic spread across the globe to avoid collapsing to one anchor point.
        lat = ((-45.0 + (finalize_steps * 23.0)) % 140.0) - 70.0
        lon = ((-170.0 + (finalize_steps * 47.0)) % 340.0) - 170.0

    return GeoGuessAction(
        action_type="guess",
        guess_lat=round(lat, 4),
        guess_lon=round(lon, 4),
        reasoning="auto-finalize fallback guess",
    )


def _run_env_episode(completion_text: str, location_id: str | None, env_url: str) -> float:
    """Execute parsed actions against the environment and return terminal reward."""
    from client.env_client import GeoGuessEnvClient

    env = GeoGuessEnvClient(
        base_url=env_url,
        connect_timeout_s=float(os.environ.get("GEOGUESS_CONNECT_TIMEOUT_S", "10")),
        message_timeout_s=float(os.environ.get("GEOGUESS_MESSAGE_TIMEOUT_S", "20")),
    )
    try:
        reset_kwargs = {"dataset_id": "training_1k"}
        if location_id:
            reset_kwargs["location_id"] = location_id
        obs = env.reset(**reset_kwargs)

        reward = 0.0
        for action in _parse_multi_turn(completion_text):
            if obs.done:
                break
            result = env.step(action)
            obs = result.observation
            if result.done:
                reward = float(result.reward or 0.0)
                break

        # If the parsed completion ends before episode termination, keep
        # advancing with cheap fallback guesses so training rollouts end and
        # backend history/runtime views reflect ongoing GRPO activity.
        finalize_steps = 0
        while not obs.done and finalize_steps < 64:
            result = env.step(_auto_finalize_action(obs, finalize_steps))
            obs = result.observation
            finalize_steps += 1
            if result.done:
                reward = float(result.reward or 0.0)
                break

        return reward
    finally:
        # Ensure the WS session is not leaked across reward calls.
        env.close()


def _format_reward(text: str) -> float:
    """Secondary reward: output parseability/structure."""
    score = 0.0
    if '"reasoning"' in text and len(text) > 50:
        score += 0.1
    if '"action_type"' in text:
        score += 0.1
    if '"guess_lat"' in text and '"guess_lon"' in text:
        score += 0.15
    try:
        for match in re.finditer(r"\{[^{}]+\}", text):
            obj = json.loads(match.group())
            if obj.get("action_type") in ("tool_call", "guess"):
                score += 0.15
                break
    except Exception:
        pass
    return min(score, 1.0)


def reward_from_env(prompts, completions, location_id=None, **kwargs) -> List[float]:
    """
    Reward each completion by executing its actions in GeoGuessEnv.

    TRL repeats side columns to align with generated completions, so location_id
    is expected to align 1:1 with completions.
    """
    env_url = os.environ.get("GEOGUESS_ENV_URL", "ws://localhost:8001")
    n = len(completions)
    rollout_retries = max(int(os.environ.get("GEOGUESS_ROLLOUT_RETRIES", "1")), 0)

    if not isinstance(location_id, list):
        location_ids = [None] * n
    else:
        location_ids = list(location_id[:n])
        if len(location_ids) < n:
            location_ids.extend([None] * (n - len(location_ids)))

    rewards: List[float] = []
    success_count = 0
    error_count = 0
    started = time.time()
    for idx, completion in enumerate(completions):
        reward = 0.0
        done = False
        for attempt in range(rollout_retries + 1):
            try:
                reward = _run_env_episode(str(completion), location_ids[idx], env_url)
                done = True
                success_count += 1
                break
            except Exception as e:
                if attempt < rollout_retries:
                    continue
                error_count += 1
                print(
                    f"[reward_from_env] rollout_failed idx={idx} "
                    f"location_id={location_ids[idx]!r} retries={rollout_retries} err={e}",
                    flush=True,
                )
                traceback.print_exc()
        rewards.append(reward if done else 0.0)
    elapsed_s = time.time() - started
    print(
        f"[reward_from_env] completions={n} success={success_count} "
        f"errors={error_count} elapsed_s={elapsed_s:.2f}",
        flush=True,
    )
    return rewards


def reward_format_quality(prompts, completions, **kwargs) -> List[float]:
    """Secondary reward that encourages parseable action payloads."""
    return [_format_reward(str(c)) for c in completions]


if __name__ == "__main__":
    import torch
    from transformers import AutoTokenizer
    from trl import GRPOConfig, GRPOTrainer

    model_id = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    dataset_path = os.environ.get("DATASET_PATH", "data/training_1k.jsonl")
    vllm_url = os.environ.get("VLLM_SERVER_URL", "http://localhost:8000")
    output_dir = os.environ.get("OUTPUT_DIR", "./geoguess-grpo-out")
    use_vllm = os.environ.get("USE_VLLM", "true").strip().lower() == "true"
    data_limit = _int_env("TRAIN_DATA_LIMIT", 0)

    if not Path(dataset_path).exists():
        print(f"Dataset not found at {dataset_path}.")
        print("Run: python -m geoguess.scripts.build_datasets")
        raise SystemExit(1)

    dataset = load_geoguess_dataset(dataset_path, limit=data_limit)
    print(f"Loaded {len(dataset)} training examples from {dataset_path}")

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    grpo_kwargs = dict(
        output_dir=output_dir,
        num_train_epochs=_int_env("TRAIN_EPOCHS", 3),
        per_device_train_batch_size=_int_env("TRAIN_BATCH_SIZE", 2),
        gradient_accumulation_steps=_int_env("TRAIN_GRAD_ACCUM", 8),
        learning_rate=1e-5,
        max_completion_length=_int_env("MAX_COMPLETION_LENGTH", 1024),
        temperature=0.8,
        num_generations=_num_generations(8),
        logging_steps=_int_env("LOGGING_STEPS", 1),
        save_steps=_int_env("SAVE_STEPS", 200),
        report_to="none",
        bf16=False,
        fp16=False,
    )
    max_steps = _int_env("MAX_STEPS", 0)
    if max_steps > 0:
        grpo_kwargs["max_steps"] = max_steps
        grpo_kwargs["num_train_epochs"] = 1

    has_cuda = torch.cuda.is_available()
    if not has_cuda:
        # CPU fallback mode needs much smaller settings for stability.
        use_vllm = False
        grpo_kwargs.update(
            per_device_train_batch_size=_int_env("CPU_BATCH_SIZE", 1),
            gradient_accumulation_steps=_int_env("CPU_GRAD_ACCUM", 1),
            max_completion_length=_int_env("CPU_MAX_COMPLETION", 64),
            num_generations=max(_int_env("CPU_NUM_GENERATIONS", 2), 2),
            logging_steps=1,
        )
        print("No CUDA detected. Using CPU-safe GRPO settings and disabling vLLM.")
    elif not use_vllm:
        # Non-vLLM mode is heavier; use safer defaults so rollouts complete and
        # backend training history updates regularly during long runs.
        grpo_kwargs.update(
            per_device_train_batch_size=_int_env("NOVLLM_BATCH_SIZE", 1),
            gradient_accumulation_steps=_int_env("NOVLLM_GRAD_ACCUM", 1),
            max_completion_length=_int_env("NOVLLM_MAX_COMPLETION", 64),
            num_generations=max(_int_env("NOVLLM_NUM_GENERATIONS", 2), 2),
            logging_steps=1,
        )
        print("vLLM disabled with CUDA available. Using reduced non-vLLM GRPO settings.")

    if use_vllm:
        grpo_kwargs.update(
            use_vllm=True,
            vllm_mode="server",
            vllm_server_base_url=vllm_url,
        )
    else:
        grpo_kwargs.update(use_vllm=False)
    config = GRPOConfig(**grpo_kwargs)

    trainer = GRPOTrainer(
        model=model_id,
        processing_class=tokenizer,
        reward_funcs=[reward_from_env, reward_format_quality],
        train_dataset=dataset,
        args=config,
    )

    print(f"Starting GRPO training with model: {model_id}")
    print(f"cuda_available={has_cuda}")
    print(f"use_vllm={use_vllm}")
    if data_limit > 0:
        print(f"train_data_limit={data_limit}")
    if max_steps > 0:
        print(f"max_steps={max_steps}")
    if use_vllm:
        print(f"vLLM server: {vllm_url}")
    print(f"GeoGuessEnv server: {os.environ.get('GEOGUESS_ENV_URL', 'ws://localhost:8001')}")

    try:
        trainer.train()
        trainer.save_model(output_dir)
        print(f"Training complete. Model saved to {output_dir}")
    except Exception:
        print("GRPO training failed with exception:")
        traceback.print_exc()
        raise
