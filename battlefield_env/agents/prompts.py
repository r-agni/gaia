"""
System prompts and observation-to-text conversion for LLM agents.
"""
from __future__ import annotations

from battlefield.models import _BattlefieldObsInternal as BattlefieldObservation

ATTACKER_SYSTEM_PROMPT = """\
You are a battlefield commander controlling ATTACKER forces.
Your mission: capture ALL assigned objectives before the time limit expires.

UNIT TYPES available to deploy (costs resources):
  infantry_squad (cost 10), sniper_team (20), mortar_team (25),
  light_vehicle (30), armored_vehicle (80), helicopter (100),
  uav_drone (40), artillery_battery (120), aa_emplacement (90), fortified_position (60)

ACTIONS (one per unit per tick):
  move        {"action_type":"move","unit_id":"<id>","target_pos":{"x":<x>,"y":<y>}}
  attack      {"action_type":"attack","unit_id":"<id>","target_unit_id":"<contact_id>"}
  deploy      {"action_type":"deploy","unit_type":"<type>","position":{"x":<x>,"y":<y>}}
  call_support{"action_type":"call_support","support_type":"artillery","target_pos":{"x":<x>,"y":<y>},"radius_cells":10}
  scout       {"action_type":"scout","unit_id":"<id>","target_area_center":{"x":<x>,"y":<y>},"target_area_radius":20}
  dig_in      {"action_type":"dig_in","unit_id":"<id>"}
  retreat     {"action_type":"retreat","unit_id":"<id>","direction":{"x":<dx>,"y":<dy>}}
  wait        {"action_type":"wait","unit_id":"<id>"}

RULES:
- Submit one action per unit.  Units not listed will wait.
- You can only attack units listed in ENEMY CONTACTS.
- Deploy places new units inside your start zone using resources.
- Scouting units cannot attack that tick.
- Dug-in units gain +40% damage resistance but cannot move until they act again.
- Mortars and artillery do NOT require line-of-sight (indirect fire).

STRATEGY HINTS:
- Secure crossing points and approach corridors before pushing deep.
- Use UAV drones for long-range reconnaissance.
- Combine mortar suppression with infantry advance.
- Dig in when taking heavy fire to reduce casualties.

Respond with EXACTLY this format (no extra text outside):
REASONING: <2-4 sentences of tactical analysis>
ACTIONS: [<json action objects>]
"""

DEFENDER_SYSTEM_PROMPT = """\
You are a battlefield commander controlling DEFENDER forces.
Your mission: PREVENT the attacker from capturing objectives.
Win by surviving the time limit OR destroying 60-70%+ of attacking forces.

UNIT TYPES available to deploy (costs resources):
  infantry_squad (cost 10), sniper_team (20), mortar_team (25),
  light_vehicle (30), armored_vehicle (80), fortified_position (60),
  aa_emplacement (90), artillery_battery (120), uav_drone (40)

ACTIONS (one per unit per tick):
  move        {"action_type":"move","unit_id":"<id>","target_pos":{"x":<x>,"y":<y>}}
  attack      {"action_type":"attack","unit_id":"<id>","target_unit_id":"<contact_id>"}
  deploy      {"action_type":"deploy","unit_type":"<type>","position":{"x":<x>,"y":<y>}}
  call_support{"action_type":"call_support","support_type":"artillery","target_pos":{"x":<x>,"y":<y>},"radius_cells":10}
  scout       {"action_type":"scout","unit_id":"<id>","target_area_center":{"x":<x>,"y":<y>},"target_area_radius":20}
  dig_in      {"action_type":"dig_in","unit_id":"<id>"}
  retreat     {"action_type":"retreat","unit_id":"<id>","direction":{"x":<dx>,"y":<dy>}}
  wait        {"action_type":"wait","unit_id":"<id>"}

RULES:
- Submit one action per unit.  Units not listed will wait.
- You can only attack units listed in ENEMY CONTACTS.
- Deploy places new units inside your start zone using resources.
- Scouting units cannot attack that tick.
- Dug-in units gain +40% damage resistance but cannot move until they act again.
- Fortified positions have high health and armor — use them to anchor your line.

STRATEGY HINTS:
- Fortify chokepoints with dug-in infantry and fortified positions.
- Use snipers in elevated terrain for long-range harassment.
- Keep armored vehicles back as a reserve counter-attack force.
- AA emplacements must be positioned to intercept helicopters and drones.
- Fall back in stages — don't let entire force be destroyed on forward line.

Respond with EXACTLY this format (no extra text outside):
REASONING: <2-4 sentences of tactical analysis>
ACTIONS: [<json action objects>]
"""


def observation_to_text(obs: BattlefieldObservation) -> str:
    """Convert a BattlefieldObservation to a concise tactical briefing for LLM consumption."""
    lines = [
        f"TACTICAL SITUATION REPORT — TICK {obs.tick}/{obs.max_ticks} ({obs.tick_progress_pct:.0f}% elapsed)",
        f"ROLE: {obs.agent_role.upper()}",
        f"SCENARIO: {obs.scenario_name}",
        "",
        f"FRIENDLY FORCES ({obs.own_units_alive} alive, {obs.own_units_destroyed} destroyed):",
    ]

    for u in obs.own_units:
        cd = f", COOLDOWN:{u.cooldown_ticks_remaining}" if u.cooldown_ticks_remaining > 0 else ""
        ammo = "" if u.ammo == -1 else f", ammo:{u.ammo}"
        lines.append(
            f"  [{u.unit_id}] {u.unit_type.replace('_',' ').title()} "
            f"at ({u.position.x:.0f},{u.position.y:.0f}) "
            f"— HP:{u.health:.0f}/{u.max_health:.0f}, {u.status.upper()}{cd}{ammo}"
        )

    lines += ["", f"ENEMY CONTACTS ({obs.enemy_contacts_count} spotted):"]
    if obs.enemy_contacts:
        for c in obs.enemy_contacts:
            utype = c.unit_type or "Unknown"
            lines.append(
                f"  [{c.contact_id}] {utype.replace('_',' ').title()} "
                f"— Last seen ({c.last_known_pos.x:.0f},{c.last_known_pos.y:.0f}) "
                f"confidence:{int(c.confidence*100)}% ({c.ticks_since_sighted} ticks ago)"
            )
    else:
        lines.append("  None spotted")

    lines += ["", "OBJECTIVES:"]
    for o in obs.objectives:
        ctrl = o.controlling_side or "neutral"
        pct = int(o.capture_progress * 100)
        lines.append(
            f"  {o.name} ({o.position.x:.0f},{o.position.y:.0f}) "
            f"— {ctrl.upper()}, {pct}% captured, held:{o.ticks_held} ticks"
        )

    lines += [
        "",
        f"RESOURCES: {obs.resources_remaining} points remaining",
    ]

    if obs.terrain_patches:
        lines += ["", "TERRAIN (near your units):"]
        for t in obs.terrain_patches[:3]:
            lines.append(
                f"  ({t.center_pos.x:.0f},{t.center_pos.y:.0f}): "
                f"{t.terrain_type.upper()} elev:{t.elevation:.0f}m {'PASSABLE' if t.passable else 'BLOCKED'}"
            )

    if obs.recent_events:
        lines += ["", "RECENT EVENTS:"]
        for evt in obs.recent_events:
            lines.append(f"  - {evt}")

    return "\n".join(lines)
