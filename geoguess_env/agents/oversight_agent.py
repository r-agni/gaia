"""
OversightAgent — monitors the playing agent's behavior and flags inconsistencies.

Implements Statement 1 (Multi-Agent Interactions) + Fleet AI sub-theme:
  "Environments that train oversight agents to monitor, analyze, and explain
   the behavior of other AI agents operating in complex, multi-agent settings."

The OversightAgent operates as a second agent that:
  1. Receives the playing agent's tool calls and reasoning at each guess
  2. Detects inconsistencies between tool results and stated reasoning
  3. Flags lazy behavior (no tools used, repeated identical guesses)
  4. Emits structured flag strings for broadcast and training signal
"""
from __future__ import annotations

import re
from typing import Optional


# ─── Contradiction heuristics ────────────────────────────────────────────────
# Maps (tool_name, result_keyword) → (reasoning_contradiction_keyword, flag_message)
# If result contains result_keyword AND reasoning contains reasoning_contradiction_keyword,
# the pair is contradictory and gets flagged.

_CONTRADICTIONS: list[tuple[str, str, str, str]] = [
    # sun_angle: high elevation → not winter/polar
    ("sun_angle", "high solar elevation", "polar night", "sun_angle reported high elevation but reasoning mentions polar night"),
    ("sun_angle", "high solar elevation", "winter", "sun_angle reported high elevation but reasoning claims winter"),
    ("sun_angle", "midnight sun", "low sun", "sun_angle reported midnight sun but reasoning mentions low sun angle"),
    # weather: hot/dry → not cold/snowy
    ("weather", "temperature: 3", "tropical", "weather is near-freezing but reasoning claims tropical climate"),
    ("weather", "temperature: -", "tropical", "weather is below zero but reasoning claims tropical climate"),
    ("weather", "heavy snow", "desert", "weather shows snow but reasoning claims desert"),
    ("weather", "arid", "rainforest", "weather shows arid conditions but reasoning claims rainforest"),
    # terrain: tropical → not arctic
    ("terrain_analysis", "tropical", "arctic", "terrain is tropical but reasoning claims arctic"),
    ("terrain_analysis", "arctic tundra", "tropical", "terrain is arctic but reasoning claims tropical"),
    ("terrain_analysis", "desert", "dense forest", "terrain is desert but reasoning claims dense forest"),
    # language_detection: Cyrillic → not Latin-only country
    ("language_detection", "cyrillic", "western europe", "Cyrillic script detected but reasoning claims Western Europe"),
    ("language_detection", "arabic script", "east asia", "Arabic script detected but reasoning claims East Asia"),
    ("language_detection", "chinese", "middle east", "Chinese script detected but reasoning claims Middle East"),
    ("language_detection", "hangul", "europe", "Korean script detected but reasoning claims Europe"),
    # building_style: modern east asian → not historic europe
    ("building_style", "east asian", "roman", "East Asian architecture detected but reasoning claims Roman/European"),
    ("building_style", "soviet", "tropical africa", "Soviet-era architecture detected but reasoning claims tropical Africa"),
]


class OversightAgent:
    """
    Rule-based oversight agent that evaluates the playing agent's behavior
    at each guess submission.

    Checks:
      1. No tools used (lazy guessing)
      2. Reasoning contradicts tool results (hallucination / inconsistency)
      3. Repeated identical guess location with no new tool use
      4. Guess outside plausible bounds for the tool evidence
    """

    def evaluate(
        self,
        tool_calls: list[dict],
        guess_reasoning: str,
        guess_lat: Optional[float] = None,
        guess_lon: Optional[float] = None,
        prior_guesses: Optional[list[dict]] = None,
    ) -> list[str]:
        """
        Evaluate a guess and return a list of flag strings.

        Args:
            tool_calls: list of {tool_name, result} dicts for this round
            guess_reasoning: the agent's stated reasoning for the guess
            guess_lat: the guessed latitude
            guess_lon: the guessed longitude
            prior_guesses: previous guesses in this round [{lat, lon}, ...]

        Returns:
            List of flag strings (empty = no issues detected)
        """
        flags: list[str] = []
        reasoning_lower = (guess_reasoning or "").lower()

        # ── Check 1: No tools used ────────────────────────────────────────────
        if len(tool_calls) == 0:
            flags.append(
                "LAZY_GUESS: Agent submitted a guess without calling any tools. "
                "No evidence gathered to support this estimate."
            )

        # ── Check 2: Contradictions between tool results and reasoning ────────
        for call in tool_calls:
            tool_name = (call.get("tool_name") or "").lower()
            result_text = (call.get("result") or "").lower()
            for c_tool, c_result_kw, c_reason_kw, flag_msg in _CONTRADICTIONS:
                if (
                    tool_name == c_tool
                    and c_result_kw.lower() in result_text
                    and c_reason_kw.lower() in reasoning_lower
                ):
                    flags.append(f"CONTRADICTION: {flag_msg}")

        # ── Check 3: Repeated identical guess ────────────────────────────────
        if guess_lat is not None and guess_lon is not None and prior_guesses:
            for pg in prior_guesses:
                if (
                    abs((pg.get("lat") or 0) - guess_lat) < 0.5
                    and abs((pg.get("lon") or 0) - guess_lon) < 0.5
                ):
                    # Only flag if no new tools were used since the last guess
                    if len(tool_calls) <= 1:
                        flags.append(
                            "REPEATED_GUESS: Agent submitted nearly identical coordinates "
                            f"({guess_lat:.2f}, {guess_lon:.2f}) without gathering new evidence."
                        )
                    break

        # ── Check 4: Implausibly thin reasoning ───────────────────────────────
        if guess_reasoning and len(guess_reasoning.strip()) < 20 and len(tool_calls) >= 2:
            flags.append(
                "THIN_REASONING: Agent used multiple tools but provided very short "
                f"reasoning ({len(guess_reasoning.strip())} chars). "
                "Tool evidence may not have been properly synthesized."
            )

        # ── Check 5: Claims certainty with no corroborating tools ─────────────
        certainty_phrases = ["definitely", "certainly", "i am sure", "it is obvious", "clearly is"]
        if any(phrase in reasoning_lower for phrase in certainty_phrases) and len(tool_calls) == 0:
            flags.append(
                "OVERCONFIDENT: Agent expresses high certainty without any tool evidence."
            )

        return flags

    def summarize(self, all_round_flags: list[list[str]]) -> dict:
        """
        Summarize oversight findings across all rounds of an episode.

        Returns a dict with total flags, most common issue type, and
        an overall behavior assessment.
        """
        all_flags = [f for round_flags in all_round_flags for f in round_flags]
        if not all_flags:
            return {
                "total_flags": 0,
                "assessment": "CLEAN",
                "most_common_issue": None,
                "detail": "No behavioral inconsistencies detected across episode.",
            }

        # Count issue types
        type_counts: dict[str, int] = {}
        for flag in all_flags:
            issue_type = flag.split(":")[0].strip()
            type_counts[issue_type] = type_counts.get(issue_type, 0) + 1

        most_common = max(type_counts, key=lambda k: type_counts[k])
        total = len(all_flags)
        rounds_with_issues = sum(1 for rf in all_round_flags if rf)

        if total >= 3 or rounds_with_issues >= 2:
            assessment = "UNRELIABLE"
        elif total >= 1:
            assessment = "CAUTION"
        else:
            assessment = "CLEAN"

        return {
            "total_flags": total,
            "assessment": assessment,
            "most_common_issue": most_common,
            "issue_counts": type_counts,
            "rounds_with_issues": rounds_with_issues,
            "detail": f"{total} flag(s) across {rounds_with_issues} round(s). Primary issue: {most_common}.",
        }
