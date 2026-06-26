"""PSL Core Formation - pure formation ability computation."""

from __future__ import annotations

from typing import List, Optional, Tuple

from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER, FORMATION


def get_formation_positions(formation_type: str) -> List[str]:
    f = FORMATION.get(formation_type)
    if f is None:
        f = FORMATION["442"]
    return f["positions"]


def get_formation_coordinates(formation_type: str) -> List[tuple]:
    f = FORMATION.get(formation_type)
    if f is None:
        f = FORMATION["442"]
    return f["coordinates"]


def compute_formation_abilities(
    positions: List[str],
    real_overalls: List[Optional[int]],
) -> Tuple[int, int, int, int]:
    total = 0
    forward = 0
    midfield = 0
    guard = 0
    forward_count = 0
    midfield_count = 0
    guard_count = 0

    for i, pos in enumerate(positions):
        if pos in FORWARD:
            forward_count += 1
        elif pos in MIDFIELD:
            midfield_count += 1
        elif pos in GUARD or pos in GOALKEEPER:
            guard_count += 1

        ov = real_overalls[i] if i < len(real_overalls) else None
        if ov is None:
            continue

        total += ov
        if pos in FORWARD:
            forward += ov
        elif pos in MIDFIELD:
            midfield += ov
        elif pos in GUARD or pos in GOALKEEPER:
            guard += ov

    forward_count = max(forward_count, 1)
    midfield_count = max(midfield_count, 1)
    guard_count = max(guard_count, 1)
    return (total, forward // forward_count, midfield // midfield_count, guard // guard_count)


def position_fit_bonus(player_positions: List[str], slot: str) -> int:
    if not player_positions:
        return 0
    primary = player_positions[0]

    if slot in player_positions:
        return 18 if slot == primary else 12
    if slot in ("LCB", "CB", "RCB"):
        if any(p in ("CB", "LCB", "RCB") for p in player_positions):
            return 10
        if any(p in ("CDM", "LDM", "RDM") for p in player_positions):
            return 1
        if any(p in ("LB", "RB", "LWB", "RWB") for p in player_positions):
            return -8
    if slot in ("LB", "RB", "LWB", "RWB"):
        if any(p in ("LB", "RB", "LWB", "RWB") for p in player_positions):
            return 10
        if any(p in ("CB", "LCB", "RCB") for p in player_positions):
            return -6

    from psl_core.card import position_group
    sg = position_group(slot)
    player_lines = {position_group(p) for p in player_positions}
    if sg == "GK" or "GK" in player_lines:
        return 0 if sg == "GK" and "GK" in player_lines else -80
    if sg in player_lines:
        return 4
    return -35
