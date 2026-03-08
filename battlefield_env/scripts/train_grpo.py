"""
Battlefield GRPO Training with TRL + OpenEnv
============================================

Trains an LLM to command attacker forces in BattlefieldEnv using GRPO
(Group Relative Policy Optimization) via TRL's GRPOTrainer.

The model plays as the attacker; a RuleBasedAgent plays the defender.
Three reward signals are used:
  - reward_win        : 1.0 if attacker wins the episode, else 0.0
  - reward_objectives : fraction of objectives captured at episode end
  - reward_format     : mean per-turn score (1.0 per turn with valid REASONING+ACTIONS)

Usage
-----
# Install training deps first (from battlefield_env/ directory):
    pip install -e ".[training]"

# Single GPU — colocate vLLM (recommended for development):
    python scripts/train_grpo.py

# 2+ GPUs — separate vLLM server:
    CUDA_VISIBLE_DEVICES=0 trl vllm-serve --model Qwen/Qwen2.5-0.5B-Instruct \\
        --host 0.0.0.0 --port 8000
    CUDA_VISIBLE_DEVICES=1 python scripts/train_grpo.py \\
        --vllm-mode server --vllm-server-url http://localhost:8000

The BattlefieldEnv server must be running before training starts:
    uvicorn battlefield.server:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

# ── path setup: works from anywhere inside or outside battlefield_env/ ────────
_HERE = Path(__file__).resolve().parent.parent  # battlefield_env/
sys.path.insert(0, str(_HERE))

from datasets import Dataset
from transformers import AutoTokenizer
from trl import GRPOConfig, GRPOTrainer
from trl.experimental.openenv import generate_rollout_completions

from agents.output_parser import parse_llm_output
from agents.prompts import ATTACKER_SYSTEM_PROMPT, observation_to_text
from agents.rule_agent import RuleBasedAgent
from battlefield.models import (
    BattlefieldAction,
    BattlefieldCombinedAction,
    BattlefieldObservation,
    GridPos,
    _BattlefieldObsInternal,
    EnemyContact,
    ObjectiveState,
    TerrainPatch,
    UnitObservation,
)
from client.env_client import BattlefieldEnvClient

logger = logging.getLogger(__name__)

# ─── Format reward regex ─────────────────────────────────────────────────────
_FORMAT_RE = re.compile(
    r"REASONING\s*:.*\S.*ACTIONS\s*:\s*\[",
    re.DOTALL | re.IGNORECASE,
)


# ─── Pydantic → internal obs conversion ─────────────────────────────────────

def _pydantic_obs_to_internal(obs: BattlefieldObservation) -> _BattlefieldObsInternal:
    """
    Convert the Pydantic BattlefieldObservation (dict-based fields from HTTP)
    into the internal dataclass that observation_to_text() and RuleBasedAgent expect.
    """
    def _gp(d: dict) -> GridPos:
        return GridPos(float(d.get("x", 0)), float(d.get("y", 0)))

    own_units = [
        UnitObservation(
            unit_id=u["unit_id"],
            unit_type=u["unit_type"],
            position=_gp(u["position"]),
            health=float(u.get("health", 0)),
            max_health=float(u.get("max_health", 100)),
            ammo=int(u.get("ammo", -1)),
            status=u.get("status", "active"),
            cooldown_ticks_remaining=int(u.get("cooldown_ticks_remaining", 0)),
            heading_deg=float(u.get("heading_deg", 0)),
        )
        for u in obs.own_units
        if isinstance(u, dict)
    ]

    enemy_contacts = [
        EnemyContact(
            contact_id=c["contact_id"],
            unit_type=c.get("unit_type"),
            last_known_pos=_gp(c["last_known_pos"]),
            confidence=float(c.get("confidence", 1.0)),
            ticks_since_sighted=int(c.get("ticks_since_sighted", 0)),
        )
        for c in obs.enemy_contacts
        if isinstance(c, dict)
    ]

    objectives = [
        ObjectiveState(
            objective_id=o["objective_id"],
            name=o.get("name", ""),
            position=_gp(o["position"]),
            controlling_side=o.get("controlling_side"),
            capture_progress=float(o.get("capture_progress", 0)),
            ticks_held=int(o.get("ticks_held", 0)),
        )
        for o in obs.objectives
        if isinstance(o, dict)
    ]

    terrain_patches = [
        TerrainPatch(
            center_pos=_gp(t["center_pos"]),
            terrain_type=t.get("terrain_type", "OPEN"),
            elevation=float(t.get("elevation", 0)),
            passable=bool(t.get("passable", True)),
        )
        for t in obs.terrain_patches
        if isinstance(t, dict)
    ]

    return _BattlefieldObsInternal(
        agent_role=obs.agent_role,
        tick=obs.tick,
        max_ticks=obs.max_ticks,
        own_units=own_units,
        enemy_contacts=enemy_contacts,
        objectives=objectives,
        terrain_patches=terrain_patches,
        resources_remaining=obs.resources_remaining,
        scenario_name=obs.scenario_name,
        own_units_alive=obs.own_units_alive,
        own_units_destroyed=obs.own_units_destroyed,
        enemy_contacts_count=obs.enemy_contacts_count,
        tick_progress_pct=obs.tick_progress_pct,
        recent_events=list(obs.recent_events),
    )


# ─── Reward functions ─────────────────────────────────────────────────────────

def reward_win(completions: list[str], **kwargs: Any) -> list[float]:
    """1.0 if the attacker won the episode, else 0.0."""
    values = kwargs.get("win_reward", [])
    if not values:
        return [0.0] * len(completions)
    return [float(v) for v in values]


def reward_objectives(completions: list[str], **kwargs: Any) -> list[float]:
    """Fraction of objectives the attacker captured by episode end (0.0–1.0)."""
    values = kwargs.get("obj_reward", [])
    if not values:
        return [0.0] * len(completions)
    return [float(v) for v in values]


def reward_format(completions: list[str], **kwargs: Any) -> list[float]:
    """
    Mean fraction of turns where the completion contained a valid
    REASONING: ... ACTIONS: [...] structure.
    Encourages well-structured tactical output throughout the episode.
    """
    values = kwargs.get("fmt_reward", [])
    if not values:
        return [0.0] * len(completions)
    return [float(v) for v in values]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _objectives_captured_fraction(obs: BattlefieldObservation) -> float:
    """Fraction of objectives controlled by attacker at this observation."""
    objs = [o for o in obs.objectives if isinstance(o, dict)]
    if not objs:
        return 0.0
    attacker_owned = sum(1 for o in objs if o.get("controlling_side") == "attacker")
    return attacker_owned / len(objs)


def _action_to_dict(a) -> dict:
    """Serialize an action sub-object (dataclass or Pydantic model) to dict."""
    if hasattr(a, "model_dump"):
        return a.model_dump()
    if hasattr(a, "__dataclass_fields__"):
        import dataclasses
        return dataclasses.asdict(a)
    return vars(a)


# ─── Episode rollout ──────────────────────────────────────────────────────────

def _run_episode(
    trainer: GRPOTrainer,
    env_client: BattlefieldEnvClient,
    tokenizer: AutoTokenizer,
    scenario_id: str,
    defender_agent: RuleBasedAgent,
    max_ticks_guard: int = 200,
) -> dict[str, Any]:
    """
    Run one full Battlefield episode.

    - Attacker  → LLM via TRL's generate_rollout_completions
    - Defender  → RuleBasedAgent (no training gradient)

    Returns a dict with per-episode scalars and token lists.
    """
    result = env_client.reset(scenario_id=scenario_id)
    obs: BattlefieldObservation = result.observation
    defender_agent.reset()

    ep_prompt_ids: list = []
    ep_completion_ids: list = []
    ep_logprobs: list = []
    fmt_scores: list[float] = []
    last_win_reward = 0.0
    last_obj_reward = 0.0
    ticks_elapsed = 0

    while not result.done and ticks_elapsed < max_ticks_guard:
        ticks_elapsed += 1

        # Convert Pydantic obs → internal for observation_to_text / rule agent
        obs_internal = _pydantic_obs_to_internal(obs)

        # ── Attacker: LLM ────────────────────────────────────────────────────
        messages = [
            {"role": "system", "content": ATTACKER_SYSTEM_PROMPT},
            {"role": "user", "content": observation_to_text(obs_internal)},
        ]
        prompt_text = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
        )

        rollout_out = generate_rollout_completions(trainer, [prompt_text])[0]
        ep_prompt_ids.extend(rollout_out["prompt_ids"])
        ep_completion_ids.extend(rollout_out["completion_ids"])
        ep_logprobs.extend(rollout_out["logprobs"])

        completion_text = rollout_out.get("text") or tokenizer.decode(
            rollout_out["completion_ids"], skip_special_tokens=True
        )

        # Format score for this turn
        fmt_scores.append(1.0 if _FORMAT_RE.search(completion_text) else 0.0)

        # Parse completion → attacker BattlefieldAction (Pydantic)
        known_unit_ids = [u.unit_id for u in obs_internal.own_units]
        parsed = parse_llm_output(completion_text, "attacker", obs.tick, known_unit_ids)
        attacker_action = BattlefieldAction(
            agent_role="attacker",
            actions=[_action_to_dict(a) for a in parsed.actions],
            reasoning=parsed.reasoning,
            timestamp_tick=obs.tick,
        )

        # ── Defender: rule-based ─────────────────────────────────────────────
        # Build a minimal defender obs: same objectives (so the rule agent can
        # navigate) but empty own_units (no defender units visible to attacker).
        defender_obs_internal = _BattlefieldObsInternal(
            agent_role="defender",
            tick=obs.tick,
            max_ticks=obs.max_ticks,
            own_units=[],           # attacker obs doesn't see defender units
            enemy_contacts=[],
            objectives=obs_internal.objectives,
            terrain_patches=[],
            resources_remaining=0,
            scenario_name=obs_internal.scenario_name,
            own_units_alive=0,
            own_units_destroyed=0,
            enemy_contacts_count=0,
            tick_progress_pct=obs_internal.tick_progress_pct,
        )
        defender_internal = asyncio.run(defender_agent.act(defender_obs_internal))
        defender_action = BattlefieldAction(
            agent_role="defender",
            actions=[_action_to_dict(a) for a in defender_internal.actions],
            reasoning=defender_internal.reasoning,
            timestamp_tick=obs.tick,
        )

        combined = BattlefieldCombinedAction(
            attacker_action=attacker_action,
            defender_action=defender_action,
        )

        result = env_client.step(combined)
        obs = result.observation
        last_win_reward = float(result.reward or 0.0)
        last_obj_reward = _objectives_captured_fraction(obs)

    # Mean format score over all turns in this episode
    fmt_reward = sum(fmt_scores) / len(fmt_scores) if fmt_scores else 0.0

    return {
        "prompt_ids": ep_prompt_ids,
        "completion_ids": ep_completion_ids,
        "logprobs": ep_logprobs,
        "win_reward": last_win_reward,
        "obj_reward": last_obj_reward,
        "fmt_reward": fmt_reward,
    }


# ─── Rollout function factory ─────────────────────────────────────────────────

def make_rollout_func(
    env_client: BattlefieldEnvClient,
    tokenizer: AutoTokenizer,
    scenario_id: str,
):
    """Returns a rollout_func closure bound to env_client, tokenizer, scenario."""
    defender_agent = RuleBasedAgent(role="defender")

    def rollout_func(prompts: list[str], trainer: GRPOTrainer) -> dict[str, list]:
        """
        Called by GRPOTrainer once per batch.
        Runs one full Battlefield episode per prompt entry.

        Returns the four required keys plus extra kwargs forwarded to reward_funcs:
            prompt_ids     : list[list[int]]
            completion_ids : list[list[int]]
            logprobs       : list[list[float]]
            win_reward     : list[float]
            obj_reward     : list[float]
            fmt_reward     : list[float]
        """
        all_prompt_ids: list = []
        all_completion_ids: list = []
        all_logprobs: list = []
        win_rewards: list[float] = []
        obj_rewards: list[float] = []
        fmt_rewards: list[float] = []

        for i, _ in enumerate(prompts):
            logger.info("Episode %d/%d — scenario=%s", i + 1, len(prompts), scenario_id)
            try:
                ep = _run_episode(
                    trainer=trainer,
                    env_client=env_client,
                    tokenizer=tokenizer,
                    scenario_id=scenario_id,
                    defender_agent=defender_agent,
                )
            except Exception as exc:
                logger.error("Episode %d failed: %s", i + 1, exc, exc_info=True)
                ep = {
                    "prompt_ids": [],
                    "completion_ids": [],
                    "logprobs": [],
                    "win_reward": 0.0,
                    "obj_reward": 0.0,
                    "fmt_reward": 0.0,
                }

            all_prompt_ids.append(ep["prompt_ids"])
            all_completion_ids.append(ep["completion_ids"])
            all_logprobs.append(ep["logprobs"])
            win_rewards.append(ep["win_reward"])
            obj_rewards.append(ep["obj_reward"])
            fmt_rewards.append(ep["fmt_reward"])

            logger.info(
                "Episode %d done — win=%.2f obj=%.2f fmt=%.2f",
                i + 1, ep["win_reward"], ep["obj_reward"], ep["fmt_reward"],
            )

        return {
            "prompt_ids": all_prompt_ids,
            "completion_ids": all_completion_ids,
            "logprobs": all_logprobs,
            "win_reward": win_rewards,
            "obj_reward": obj_rewards,
            "fmt_reward": fmt_rewards,
        }

    return rollout_func


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train a battlefield commander LLM with GRPO + BattlefieldEnv"
    )
    p.add_argument(
        "--model-id",
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="HuggingFace model ID to fine-tune (default: Qwen/Qwen2.5-0.5B-Instruct)",
    )
    p.add_argument(
        "--env-host",
        default="ws://127.0.0.1:8001",
        help="WebSocket URL of the BattlefieldEnv server (default: ws://127.0.0.1:8001)",
    )
    p.add_argument(
        "--scenario-id",
        default="crossing_at_korzha",
        help="Scenario ID to train on (default: crossing_at_korzha)",
    )
    p.add_argument(
        "--vllm-mode",
        choices=["colocate", "server"],
        default="colocate",
        help="vLLM execution mode — 'colocate' (1 GPU) or 'server' (2+ GPUs)",
    )
    p.add_argument(
        "--vllm-server-url",
        default="http://localhost:8000",
        help="vLLM server base URL (used when --vllm-mode=server)",
    )
    p.add_argument(
        "--num-episodes",
        type=int,
        default=512,
        help="Training dataset size in episodes (default: 512)",
    )
    p.add_argument(
        "--num-generations",
        type=int,
        default=4,
        help="GRPO group size — episodes per prompt (default: 4)",
    )
    p.add_argument(
        "--max-completion-length",
        type=int,
        default=600,
        help="Max tokens per LLM completion per turn (default: 600)",
    )
    p.add_argument(
        "--output-dir",
        default="./output/battlefield-grpo",
        help="Checkpoint output directory (default: ./output/battlefield-grpo)",
    )
    p.add_argument("--num-train-epochs", type=int, default=1)
    p.add_argument("--per-device-train-batch-size", type=int, default=4)
    p.add_argument("--gradient-accumulation-steps", type=int, default=4)
    p.add_argument("--learning-rate", type=float, default=5e-6)
    return p.parse_args()


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    args = parse_args()

    logger.info("Loading tokenizer: %s", args.model_id)
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Training dataset — one placeholder entry per episode.
    # Actual prompts are generated from live env observations inside rollout_func.
    dataset = Dataset.from_dict({
        "prompt": [
            f"You are a battlefield commander. Scenario: {args.scenario_id}"
        ] * args.num_episodes
    })
    logger.info("Dataset: %d episodes, scenario='%s'", args.num_episodes, args.scenario_id)

    logger.info("Connecting to BattlefieldEnv at %s", args.env_host)
    env_client = BattlefieldEnvClient(base_url=args.env_host)

    # GRPOConfig
    grpo_kwargs: dict = dict(
        use_vllm=True,
        vllm_mode=args.vllm_mode,
        num_train_epochs=args.num_train_epochs,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion_length,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        output_dir=args.output_dir,
        logging_steps=1,
        save_steps=50,
        report_to="none",
    )
    if args.vllm_mode == "server":
        grpo_kwargs["vllm_server_base_url"] = args.vllm_server_url

    grpo_config = GRPOConfig(**grpo_kwargs)

    rollout_func = make_rollout_func(
        env_client=env_client,
        tokenizer=tokenizer,
        scenario_id=args.scenario_id,
    )

    trainer = GRPOTrainer(
        model=args.model_id,
        processing_class=tokenizer,
        reward_funcs=[reward_win, reward_objectives, reward_format],
        train_dataset=dataset,
        args=grpo_config,
        rollout_func=rollout_func,
    )

    logger.info(
        "Starting GRPO training — model=%s, vllm_mode=%s, output=%s",
        args.model_id, args.vllm_mode, args.output_dir,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    logger.info("Training complete. Model saved to %s", args.output_dir)


if __name__ == "__main__":
    main()
