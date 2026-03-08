"""
GeoGuess GRPO training script.

Uses TRL GRPOTrainer and computes environment reward by executing parsed
completions against the GeoGuess OpenEnv endpoint.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List

from datasets import Dataset


def load_geoguess_dataset(path: str = "data/training_1k.jsonl") -> Dataset:
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
    return Dataset.from_list(records)


def _parse_multi_turn(text: str):
    """Parse a sequence of GeoGuessAction payloads from model output."""
    from agents.output_parser import parse_llm_output
    from geoguess.models import GeoGuessAction

    actions = []
    for match in re.finditer(r"\{[^{}]+\}", text, re.DOTALL):
        raw = match.group()
        try:
            obj = json.loads(raw.replace("'", '"'))
            if obj.get("action_type") in ("tool_call", "guess"):
                action = parse_llm_output(raw)
                actions.append(action)
        except Exception:
            continue

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


def _run_env_episode(completion_text: str, location_id: str | None, env_url: str) -> float:
    """Execute parsed actions against the environment and return terminal reward."""
    from client.env_client import GeoGuessEnvClient

    env = GeoGuessEnvClient(base_url=env_url)
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
    return reward


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

    if not isinstance(location_id, list):
        location_ids = [None] * n
    else:
        location_ids = list(location_id[:n])
        if len(location_ids) < n:
            location_ids.extend([None] * (n - len(location_ids)))

    rewards: List[float] = []
    for idx, completion in enumerate(completions):
        try:
            rewards.append(_run_env_episode(str(completion), location_ids[idx], env_url))
        except Exception:
            rewards.append(0.0)
    return rewards


def reward_format_quality(prompts, completions, **kwargs) -> List[float]:
    """Secondary reward that encourages parseable action payloads."""
    return [_format_reward(str(c)) for c in completions]


if __name__ == "__main__":
    from transformers import AutoTokenizer
    from trl import GRPOConfig, GRPOTrainer

    model_id = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    dataset_path = os.environ.get("DATASET_PATH", "data/training_1k.jsonl")
    vllm_url = os.environ.get("VLLM_SERVER_URL", "http://localhost:8000")
    output_dir = os.environ.get("OUTPUT_DIR", "./geoguess-grpo-out")
    use_vllm = os.environ.get("USE_VLLM", "true").strip().lower() == "true"

    if not Path(dataset_path).exists():
        print(f"Dataset not found at {dataset_path}.")
        print("Run: python -m geoguess.scripts.build_datasets")
        raise SystemExit(1)

    dataset = load_geoguess_dataset(dataset_path)
    print(f"Loaded {len(dataset)} training examples from {dataset_path}")

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    grpo_kwargs = dict(
        output_dir=output_dir,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=1e-5,
        max_completion_length=1024,
        temperature=0.8,
        num_generations=8,
        logging_steps=10,
        save_steps=200,
        report_to="none",
    )
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
    print(f"use_vllm={use_vllm}")
    if use_vllm:
        print(f"vLLM server: {vllm_url}")
    print(f"GeoGuessEnv server: {os.environ.get('GEOGUESS_ENV_URL', 'ws://localhost:8001')}")

    trainer.train()
    trainer.save_model(output_dir)
    print(f"Training complete. Model saved to {output_dir}")
