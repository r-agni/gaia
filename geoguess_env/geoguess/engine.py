"""
GeoGuessr game engine.

Manages the full episode lifecycle:
  - N rounds per episode
  - Each round: agent calls tools (up to budget) then submits a lat/lon guess
  - Rewards computed from Haversine distance + country/region bonuses
"""
from __future__ import annotations

import random
import uuid
from typing import List, Optional

from .locations import generate_scene_description, sample_locations
from .models import (
    AVAILABLE_TOOLS,
    GeoGuessAction,
    GeoGuessEngineState,
    GeoGuessObservation,
    GeoLocation,
    GuessRecord,
    RoundState,
    ToolResult,
)
from .rewards import check_country_region, compute_episode_reward, compute_round_reward
from .tools import resolve_tool

# Import oversight agent (lives in agents/ directory alongside llm_agent etc.)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from agents.oversight_agent import OversightAgent as _OversightAgent
    _oversight = _OversightAgent()
except Exception:
    _oversight = None


class GeoGuessEngine:
    """
    Stateful game engine for one GeoGuessr episode.

    Usage:
        engine = GeoGuessEngine()
        obs = await engine.reset(dataset_id="world_cities_5k", total_rounds=5, seed=42)
        while not engine.state.is_terminal:
            action = agent.act(obs)
            obs, reward, done = await engine.step(action)
    """

    def __init__(self) -> None:
        self.state: Optional[GeoGuessEngineState] = None

    # ─── Public API ──────────────────────────────────────────────────────────

    async def reset(
        self,
        dataset_id: str = "world_cities_5k",
        total_rounds: int = 5,
        max_steps_per_round: int = 7,
        max_guesses_per_round: int = 2,
        seed: int = 0,
        location_id: Optional[str] = None,
        training_mode: bool = False,
        training_episode: int = 0,
    ) -> GeoGuessObservation:
        """Start a new episode. Returns the first observation."""
        locations = sample_locations(dataset_id, total_rounds, seed=seed, location_id=location_id)
        while len(locations) < total_rounds:
            locations += locations
        locations = locations[:total_rounds]

        rounds: List[RoundState] = []
        for i, loc in enumerate(locations):
            scene = generate_scene_description(loc, rng=random.Random(seed * 1000 + i))
            rounds.append(RoundState(
                round_number=i,
                location=loc,
                initial_scene_description=scene,
            ))

        self.state = GeoGuessEngineState(
            dataset_id=dataset_id,
            episode_id=str(uuid.uuid4())[:8],
            current_round=0,
            total_rounds=total_rounds,
            max_steps_per_round=max_steps_per_round,
            max_guesses_per_round=max_guesses_per_round,
            rounds=rounds,
            training_mode=training_mode,
            training_episode=training_episode,
        )
        return self._make_observation()

    async def step(
        self,
        action: GeoGuessAction,
    ) -> tuple[GeoGuessObservation, float, bool]:
        """
        Advance by one action (tool call or guess).

        Returns:
            (observation, reward, done)
            reward is 0.0 for tool calls; round_score for guesses
        """
        assert self.state is not None, "Call reset() before step()"
        s = self.state

        if s.is_terminal:
            return self._make_observation(), 0.0, True

        round_state = s.rounds[s.current_round]

        # ── Tool call ────────────────────────────────────────────────────────
        if action.action_type == "tool_call":
            if round_state.step >= s.max_steps_per_round:
                return await self._force_round_end()

            tool_name = action.tool_name or ""
            if tool_name not in AVAILABLE_TOOLS:
                result = ToolResult(
                    tool_name=tool_name,
                    invoked_at_step=round_state.step,
                    result_text=f"Unknown tool '{tool_name}'. Available: {AVAILABLE_TOOLS}",
                )
            else:
                result = await resolve_tool(
                    tool_name=tool_name,
                    location=round_state.location,
                    params=action.tool_params or {},
                    step=round_state.step,
                )

            round_state.tool_results.append(result)
            round_state.tools_budget_used += 1
            round_state.step += 1

            # If budget exhausted with no guess submitted → force end
            if round_state.step >= s.max_steps_per_round and not round_state.guesses:
                return await self._force_round_end()

            return self._make_observation(), 0.0, False

        # ── Guess ────────────────────────────────────────────────────────────
        if action.action_type == "guess":
            guess_lat = max(-90.0, min(90.0, float(action.guess_lat or 0.0)))
            guess_lon = max(-180.0, min(180.0, float(action.guess_lon or 0.0)))

            tool_names_used = [tr.tool_name for tr in round_state.tool_results]
            reward, dist_km = compute_round_reward(
                guess_lat=guess_lat,
                guess_lon=guess_lon,
                secret_location=round_state.location,
                tools_used=round_state.tools_budget_used,
                tool_names_used=tool_names_used,
            )
            correct_country, correct_region = check_country_region(
                guess_lat, guess_lon, round_state.location
            )

            record = GuessRecord(
                lat=guess_lat,
                lon=guess_lon,
                reasoning=action.reasoning or "",
                distance_km=dist_km,
                score=reward,
                correct_country=correct_country,
                correct_region=correct_region,
                step=round_state.step,
            )
            round_state.guesses.append(record)
            round_state.step += 1

            # ── Oversight evaluation ──────────────────────────────────────────
            if _oversight is not None:
                try:
                    tool_calls_for_oversight = [
                        {"tool_name": tr.tool_name, "result": tr.result_text}
                        for tr in round_state.tool_results
                    ]
                    prior_guesses = [
                        {"lat": g.lat, "lon": g.lon}
                        for g in round_state.guesses[:-1]  # exclude the just-added guess
                    ]
                    flags = _oversight.evaluate(
                        tool_calls=tool_calls_for_oversight,
                        guess_reasoning=action.reasoning or "",
                        guess_lat=guess_lat,
                        guess_lon=guess_lon,
                        prior_guesses=prior_guesses,
                    )
                    round_state.oversight_flags.extend(flags)
                except Exception:
                    pass

            round_over = (
                len(round_state.guesses) >= s.max_guesses_per_round
                or round_state.step >= s.max_steps_per_round
            )

            if round_over:
                round_state.round_score = max(g.score for g in round_state.guesses)
                round_state.is_terminal = True
                return await self._advance_or_end(round_reward=round_state.round_score)

            return self._make_observation(), 0.0, False

        return self._make_observation(), 0.0, False

    # ─── Internal helpers ─────────────────────────────────────────────────────

    async def _force_round_end(self) -> tuple[GeoGuessObservation, float, bool]:
        s = self.state
        round_state = s.rounds[s.current_round]
        round_state.round_score = 0.0
        round_state.is_terminal = True
        return await self._advance_or_end(round_reward=0.0)

    async def _advance_or_end(
        self, round_reward: float
    ) -> tuple[GeoGuessObservation, float, bool]:
        s = self.state
        completed_scores = [r.round_score for r in s.rounds[: s.current_round + 1]]
        s.episode_score = compute_episode_reward(completed_scores)

        next_round = s.current_round + 1
        if next_round >= s.total_rounds:
            s.is_terminal = True
            return self._make_observation(), round_reward, True

        s.current_round = next_round
        return self._make_observation(), round_reward, False

    def _make_observation(self) -> GeoGuessObservation:
        s = self.state
        round_state = s.rounds[s.current_round]
        steps_remaining = max(0, s.max_steps_per_round - round_state.step)
        guesses_remaining = max(0, s.max_guesses_per_round - len(round_state.guesses))

        tool_results_dicts = [
            {"tool_name": tr.tool_name, "step": tr.invoked_at_step, "result": tr.result_text}
            for tr in round_state.tool_results
        ]
        guesses_dicts = [
            {
                "lat": g.lat,
                "lon": g.lon,
                "distance_km": g.distance_km,
                "score": g.score,
                "correct_country": g.correct_country,
                "correct_region": g.correct_region,
            }
            for g in round_state.guesses
        ]

        prompt = self._build_prompt(
            round_state=round_state,
            steps_remaining=steps_remaining,
            guesses_remaining=guesses_remaining,
            total_rounds=s.total_rounds,
            episode_score=s.episode_score,
            max_steps=s.max_steps_per_round,
        )

        return GeoGuessObservation(
            round_number=s.current_round,
            total_rounds=s.total_rounds,
            step=round_state.step,
            max_steps_per_round=s.max_steps_per_round,
            initial_scene_description=round_state.initial_scene_description,
            tool_results=tool_results_dicts,
            guesses=guesses_dicts,
            steps_remaining=steps_remaining,
            guesses_remaining=guesses_remaining,
            episode_score=s.episode_score,
            available_tools=AVAILABLE_TOOLS,
            prompt=prompt,
        )

    @staticmethod
    def _build_prompt(
        round_state: RoundState,
        steps_remaining: int,
        guesses_remaining: int,
        total_rounds: int,
        episode_score: float,
        max_steps: int,
    ) -> str:
        lines = [
            f"GEOGUESS ROUND {round_state.round_number + 1}/{total_rounds} "
            f"-- STEP {round_state.step}/{max_steps}",
            f"GUESSES REMAINING: {guesses_remaining}  |  STEPS REMAINING: {steps_remaining}",
            f"EPISODE SCORE: {episode_score:.3f}",
            "",
            "INITIAL SCENE DESCRIPTION:",
            round_state.initial_scene_description,
        ]

        if round_state.tool_results:
            lines += ["", f"TOOL RESULTS ({len(round_state.tool_results)} tool calls used):"]
            for tr in round_state.tool_results:
                lines.append(f"  [{tr.tool_name.upper()}]: {tr.result_text}")

        if round_state.guesses:
            lines += ["", "PREVIOUS GUESSES THIS ROUND:"]
            for i, g in enumerate(round_state.guesses, 1):
                lines.append(
                    f"  Guess {i}: ({g.lat:.4f}, {g.lon:.4f}) "
                    f"-- Distance: {g.distance_km:.1f} km, Score: {g.score:.3f}"
                )

        lines += ["", f"AVAILABLE TOOLS: {', '.join(AVAILABLE_TOOLS)}"]
        return "\n".join(lines)

    def get_full_state_dict(self) -> dict:
        """Serialise engine state for WebSocket broadcast."""
        if self.state is None:
            return {}
        s = self.state
        round_state = s.rounds[s.current_round] if s.rounds else None

        cur_guess_lat = None
        cur_guess_lon = None
        if round_state and round_state.guesses:
            last = round_state.guesses[-1]
            cur_guess_lat = last.lat
            cur_guess_lon = last.lon

        secret_lat = None
        secret_lon = None
        secret_country = "??"
        secret_region = "??"
        if round_state and round_state.is_terminal:
            secret_lat = round_state.location.lat
            secret_lon = round_state.location.lon
            secret_country = round_state.location.country_name
            secret_region = round_state.location.region

        tool_calls = []
        guesses_list = []
        if round_state:
            tool_calls = [
                {"tool_name": tr.tool_name, "step": tr.invoked_at_step, "result": tr.result_text}
                for tr in round_state.tool_results
            ]
            guesses_list = [
                {
                    "lat": g.lat,
                    "lon": g.lon,
                    "distance_km": g.distance_km,
                    "score": g.score,
                    "correct_country": g.correct_country,
                    "correct_region": g.correct_region,
                    "step": g.step,
                }
                for g in round_state.guesses
            ]

        round_history = []
        for r in s.rounds[: s.current_round]:
            best = max(r.guesses, key=lambda g: g.score) if r.guesses else None
            round_history.append({
                "round_number": r.round_number,
                "score": r.round_score,
                "distance_km": best.distance_km if best else None,
                "secret_lat": r.location.lat,
                "secret_lon": r.location.lon,
                "guess_lat": best.lat if best else None,
                "guess_lon": best.lon if best else None,
                "secret_country": r.location.country_name,
                "secret_region": r.location.region,
            })

        # Oversight summary across all completed rounds
        all_round_flags = [r.oversight_flags for r in s.rounds[: s.current_round + 1]]
        oversight_summary = {}
        if _oversight is not None:
            try:
                oversight_summary = _oversight.summarize(all_round_flags)
            except Exception:
                pass

        return {
            "episode_id": s.episode_id,
            "current_round": s.current_round,
            "total_rounds": s.total_rounds,
            "is_terminal": s.is_terminal,
            "episode_score": s.episode_score,
            "secret_lat": secret_lat,
            "secret_lon": secret_lon,
            "secret_country": secret_country,
            "secret_region": secret_region,
            "current_guess_lat": cur_guess_lat,
            "current_guess_lon": cur_guess_lon,
            "guesses": guesses_list,
            "tool_calls": tool_calls,
            "round_history": round_history,
            "training_mode": s.training_mode,
            "episode": s.training_episode,
            "oversight_flags": round_state.oversight_flags if round_state else [],
            "oversight_summary": oversight_summary,
        }
