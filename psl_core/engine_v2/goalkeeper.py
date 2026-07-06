"""Goalkeeper-specific model (Phase 2).

Implements the GK chain:
  Positioning -> Reaction -> Saving

Also handles rush-out decisions and distribution after saves.
"""

from __future__ import annotations

import math
import random
from typing import Tuple, TYPE_CHECKING

from .physics import distance, move_toward, player_speed

if TYPE_CHECKING:
    from .player import Player
    from .config import EngineConfig
    from .pitch import Pitch


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def compute_gk_save_probability(
    gk: "Player",
    shot_target: Tuple[float, float],
    shot_origin: Tuple[float, float],
    config: "EngineConfig",
) -> float:
    """Compute goalkeeper save probability using the 3-stage model.

    Stage 1 - Positioning: determines where GK is when shot is taken.
        High Positioning = less position error = covers more angle.
    Stage 2 - Reaction: delay before GK starts moving.
        High Reaction = less delay = reaches more shots.
    Stage 3 - Saving: actual save probability given reach attempt.
        High Saving = better reach and handling.
    """
    gk_saving = gk.abilities.get("GK_Saving", 50)
    gk_positioning = gk.abilities.get("GK_Positioning", 50)
    gk_reaction = gk.abilities.get("GK_Reaction", 50)

    # Stage 1: Positioning - position error reduces effective coverage.
    # The keeper does not need to cover the full x distance to the goal line;
    # shot-stopping reach is mostly lateral, with a smaller depth-position cost.
    position_error = (100 - gk_positioning) * config.gk_position_error_factor
    goal_x = config.pitch_length if shot_target[0] >= config.pitch_length / 2.0 else 0.0
    ideal_depth = goal_x - 4.5 if goal_x > 0 else 4.5
    lateral_dist = abs(gk.pos[1] - shot_target[1])
    depth_error = max(0.0, abs(gk.pos[0] - ideal_depth) - 2.0) * 0.35
    effective_dist = lateral_dist + depth_error + position_error

    # Stage 2: Reaction - delay factor reduces save window
    # Higher reaction = smaller delay = better chance
    reaction_factor = 1.0 - (100 - gk_reaction) * config.gk_reaction_delay_factor
    reaction_factor = max(0.3, min(1.0, reaction_factor))

    # Stage 3: Saving - actual save probability
    saving_ability = gk_saving / 100.0

    # Combined save probability
    # Base from config, scaled by all three stages
    base = config.gk_save_base

    # Target reach: shots near the post are harder, but ordinary central shots
    # should remain highly saveable.
    reach_factor = max(0.25, 1.0 - effective_dist / 9.0)

    # Shot distance affects GK: close shots give less reaction time; long shots
    # are easier to read. This is continuous, not a hard long-shot rule.
    shot_dist = distance(shot_origin, shot_target)
    reaction_window = 0.52 + 0.48 * _smoothstep(9.0, 30.0, shot_dist)
    long_shot_read = 1.0 + 0.18 * _smoothstep(24.0, 42.0, shot_dist)

    save_prob = (
        0.08
        + base * 0.25
        + saving_ability * 0.18
        + reach_factor * 0.18
        + reaction_factor * 0.08
        + reaction_window * 0.10
    ) * long_shot_read
    return max(0.10, min(0.90, save_prob))


def should_rush_out(
    gk: "Player",
    attacker_pos: Tuple[float, float],
    config: "EngineConfig",
) -> bool:
    """Decide whether GK should rush out to meet an attacker.

    Decision quality linked to GK_Positioning and IQ.
    """
    dist_to_attacker = distance(gk.pos, attacker_pos)

    # Only consider rushing if attacker is within rush distance
    if dist_to_attacker > config.gk_rush_distance:
        return False

    # Decision quality based on Positioning and IQ
    positioning = gk.abilities.get("GK_Positioning", 50)
    iq = gk.abilities.get("IQ", 50)
    decision_quality = (positioning * 0.6 + iq * 0.4) / 100.0

    # Rush when attacker is close and 1v1 - higher quality = better timing
    rush_threshold = 0.3 + decision_quality * 0.4  # 0.3-0.7
    proximity_factor = max(0, 1.0 - dist_to_attacker / config.gk_rush_distance)

    return proximity_factor > rush_threshold


def compute_rush_speed(gk: "Player", config: "EngineConfig") -> float:
    """Compute GK rush-out speed (uses Speed attribute)."""
    return player_speed(gk.speed_value, config.player_max_speed, config.player_min_speed)


def choose_distribution(
    gk: "Player",
    config: "EngineConfig",
    attacking_right: bool,
    pitch_length: float,
) -> Tuple[str, Tuple[float, float]]:
    """Choose distribution type after save (short throw vs long kick).

    Returns: (distribution_type, target_position)
    """
    iq = gk.abilities.get("IQ", 50)
    short_passing = gk.abilities.get("Short_Passing", 50)
    long_passing = gk.abilities.get("Long_Passing", 50)

    # Higher IQ = more likely to choose optimally based on situation
    # For now, simple heuristic: prefer short if high short_passing, long if high long_passing
    short_score = short_passing / 100.0 + iq / 200.0
    long_score = long_passing / 100.0

    if short_score > long_score + random.uniform(-0.1, 0.1):
        # Short distribution
        dist_type = "short"
        if attacking_right:
            target_x = random.uniform(15.0, 35.0)
        else:
            target_x = random.uniform(pitch_length - 35.0, pitch_length - 15.0)
        target_y = gk.pos[1] + random.uniform(-15.0, 15.0)
    else:
        # Long distribution
        dist_type = "long"
        if attacking_right:
            target_x = random.uniform(40.0, 70.0)
        else:
            target_x = random.uniform(pitch_length - 70.0, pitch_length - 40.0)
        target_y = random.uniform(15.0, 53.0)

    return dist_type, (target_x, target_y)
