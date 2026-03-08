"""
GeoGuessr GRPO Training Script
TRL + OpenEnv pattern: https://huggingface.co/docs/trl/openenv

Training loop:
  1. Load JSONL dataset of (location_id, initial_scene_description) pairs as HF Dataset
  2. Format each example as an initial GeoGuessr observation prompt
  3. rollout_func: for each prompt, run the model through a single-round game
     (tool calls + final guess) against the GeoGuessEnv server
  4. Reward = Haversine distance score + country/region bonuses - tool penalty
  5. GRPOTrainer updates model weights

Run:
  # GPU 0: start vLLM server
  trl vllm-serve --model $BASE_MODEL --host 0.0.0.0 --port 8000

  # GPU 1: start GeoGuessEnv server
  uvicorn geoguess.server:app --host 0.0.0.0 --port 8001

  # GPU 1+: train
  CUDA_VISIBLE_DEVICES=1 python train_grpo.py
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, List

from datasets import Dataset


# ─── Dataset ─────────────────────────────────────────────────────────────────


def load_geoguess_dataset(path: str = "data/training_1k.jsonl") -> Dataset:
    """
    Load the training JSONL and convert to HF Dataset.
    Each row becomes one prompt (the initial scene description).
    """
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            prompt = (
                f"Round 1: Identify the location shown.\n"
                f"Initial scene: {d.get('initial_scene_description', 'A road through an unknown landscape.')}\n"
                f"Available tools: globe_view, street_view, terrain_analysis, "
                f"weather, sun_angle, building_style, language_detection\n"
                f"Tool budget: 7 steps. Max guesses: 2.\n"
                f"Submit a tool call or a guess in JSON format."
            )
            records.append({
                "location_id": d["location_id"],
                "prompt": prompt,
                "country_code": d.get("country_code", ""),
                "region": d.get("region", ""),
            })
    return Dataset.from_list(records)


# ─── Rollout function ─────────────────────────────────────────────────────────


def rollout_func(prompts: List[Any], trainer) -> dict:
    """
    Custom rollout for GeoGuessr.

    For each prompt:
      1. Generate a multi-turn completion from the model
      2. Parse tool calls + final guess from the completion
      3. Step the environment for each action
      4. Collect terminal reward
    """
    from trl.trainer.grpo_trainer import generate_rollout_completions
    from geoguess.models import GeoGuessAction, AVAILABLE_TOOLS
    from agents.output_parser import parse_llm_output
    import asyncio

    env_url = os.environ.get("GEOGUESS_ENV_URL", "ws://localhost:8001")

    # Generate completions
    outputs = generate_rollout_completions(trainer, prompts)

    env_rewards: List[float] = []
    format_rewards: List[float] = []
    all_prompt_ids = []
    all_completion_ids = []
    all_logprobs = []

    for i, output in enumerate(outputs):
        location_id = prompts[i]["location_id"] if isinstance(prompts[i], dict) else None

        try:
            # Connect to env and run one round
            from client.env_client import GeoGuessEnvClient
            env = GeoGuessEnvClient(base_url=env_url)
            reset_kwargs = {"dataset_id": "training_1k"}
            if location_id:
                reset_kwargs["location_id"] = location_id
            obs = env.reset(**reset_kwargs)

            # Parse multi-turn actions from the completion
            actions = _parse_multi_turn(output.text)
            round_reward = 0.0
            for action in actions:
                if obs.done:
                    break
                result = env.step(action)
                obs = result.observation
                if result.done:
                    round_reward = result.reward or 0.0
                    break

            env_rewards.append(round_reward)
        except Exception:
            env_rewards.append(0.0)

        format_rewards.append(_format_reward(output.text))
        all_prompt_ids.append(output.prompt_ids)
        all_completion_ids.append(output.completion_ids)
        all_logprobs.append(output.logprobs)

    return {
        "prompt_ids": all_prompt_ids,
        "completion_ids": all_completion_ids,
        "logprobs": all_logprobs,
        "env_reward": env_rewards,
        "format_reward": format_rewards,
    }


def _parse_multi_turn(text: str):
    """Parse a sequence of GeoGuessActions from LLM output text."""
    from agents.output_parser import parse_llm_output
    from geoguess.models import GeoGuessAction

    actions = []
    # Find all JSON-like objects
    for match in re.finditer(r'\{[^{}]+\}', text, re.DOTALL):
        raw = match.group()
        try:
            obj = json.loads(raw.replace("'", '"'))
            if obj.get("action_type") in ("tool_call", "guess"):
                action = parse_llm_output(raw)
                actions.append(action)
        except Exception:
            continue

    if not actions:
        # Fallback: single guess at world centroid
        actions = [GeoGuessAction(
            action_type="guess",
            guess_lat=20.0,
            guess_lon=15.0,
            reasoning="parse failure fallback",
        )]
    return actions


def _format_reward(text: str) -> float:
    """Secondary reward: is the output well-formed?"""
    score = 0.0
    if '"reasoning"' in text and len(text) > 50:
        score += 0.1
    if '"action_type"' in text:
        score += 0.1
    if '"guess_lat"' in text and '"guess_lon"' in text:
        score += 0.15
    try:
        for match in re.finditer(r'\{[^{}]+\}', text):
            obj = json.loads(match.group())
            if obj.get("action_type") in ("tool_call", "guess"):
                score += 0.15
                break
    except Exception:
        pass
    return min(score, 1.0)


# ─── Reward functions for GRPO ────────────────────────────────────────────────


def reward_from_env(completions, **kwargs) -> List[float]:
    """Pass environment distance reward to trainer."""
    env_rewards = kwargs.get("env_reward", [])
    if env_rewards:
        return [float(r) for r in env_rewards]
    return [0.0] * len(completions)


def reward_format_quality(completions, **kwargs) -> List[float]:
    """Pass format quality reward to trainer."""
    fmt_rewards = kwargs.get("format_reward", [])
    if fmt_rewards:
        return [float(r) for r in fmt_rewards]
    return [_format_reward(c) for c in completions]


# ─── Main ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    from trl import GRPOConfig, GRPOTrainer

    MODEL_ID = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    DATASET_PATH = os.environ.get("DATASET_PATH", "data/training_1k.jsonl")
    VLLM_URL = os.environ.get("VLLM_SERVER_URL", "http://localhost:8000")
    OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./geoguess-grpo-out")
    USE_VLLM = os.environ.get("USE_VLLM", "true").strip().lower() == "true"

    if not Path(DATASET_PATH).exists():
        print(f"Dataset not found at {DATASET_PATH}.")
        print("Run: python -m geoguess.scripts.build_datasets")
        raise SystemExit(1)

    dataset = load_geoguess_dataset(DATASET_PATH)
    print(f"Loaded {len(dataset)} training examples from {DATASET_PATH}")

    config_kwargs = dict(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=1e-5,
        max_new_tokens=1024,                 # room for tool calls + reasoning + guess
        temperature=0.8,
        num_generations=8,                   # G in GRPO (samples per prompt)
        logging_steps=10,
        save_steps=200,
        report_to="none",
    )
    if USE_VLLM:
        # H100 path: vLLM on one GPU, training on another.
        config_kwargs.update(
            use_vllm=True,
            vllm_mode="server",
            vllm_server_base_url=VLLM_URL,
        )
    else:
        config_kwargs.update(use_vllm=False)
    config = GRPOConfig(**config_kwargs)

    trainer = GRPOTrainer(
        model=MODEL_ID,
        reward_funcs=[reward_from_env, reward_format_quality],
        train_dataset=dataset,
        rollout_func=rollout_func,
        args=config,
    )

    print(f"Starting GRPO training with model: {MODEL_ID}")
    print(f"use_vllm={USE_VLLM}")
    if USE_VLLM:
        print(f"vLLM server: {VLLM_URL}")
    print(f"GeoGuessEnv server: {os.environ.get('GEOGUESS_ENV_URL', 'ws://localhost:8001')}")
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    print(f"Training complete. Model saved to {OUTPUT_DIR}")
