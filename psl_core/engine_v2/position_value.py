"""Unified position value function - foundation for all spatial decisions.

Outputs how valuable a given (x, y) position is for a team's attack.
Used by: carrier direction, pass target selection, off-ball movement, defensive positioning.
"""

from __future__ import annotations

import math
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import EngineConfig
    from .pitch import Pitch


def position_value(
    x: float,
    y: float,
    pitch: "Pitch",
    attacking_right: bool,
    opponent_positions: List[Tuple[float, float]],
    teammate_positions: List[Tuple[float, float]],
    config: "EngineConfig",
) -> float:
    """Compute the attacking value of position (x, y).

    Returns a float roughly in [0, 1] where higher = more dangerous for the opponent.

    Factors:
    1. Goal proximity — closer to opponent goal = higher
    2. Space — fewer opponents nearby = higher
    3. No crowding — too many teammates nearby = lower
    4. Shooting zone — bonus if within shooting range
    5. Central bonus — central positions slightly more valuable than extreme flanks
    """
    # Normalize x-progress toward opponent goal (0 = own goal, 1 = opp goal)
    if attacking_right:
        x_progress = x / pitch.length
    else:
        x_progress = 1.0 - (x / pitch.length)

    # 1. Goal proximity (exponential toward goal)
    goal_proximity = 0.1 + 0.9 * (x_progress ** 1.3)

    # 2. Space (fewer opponents nearby = better)
    opp_count = 0
    for ox, oy in opponent_positions:
        d = math.sqrt((x - ox) ** 2 + (y - oy) ** 2)
        if d < 12.0:
            opp_count += 1.0 - d / 12.0  # closer opponents count more
    space_factor = 1.0 / (1.0 + opp_count * 0.8)  # much stronger penalty

    # 3. Crowding penalty (too many teammates = redundant)
    tm_count = 0
    for tx, ty in teammate_positions:
        d = math.sqrt((x - tx) ** 2 + (y - ty) ** 2)
        if d < 8.0:
            tm_count += 1
    crowding_factor = 1.0 / (1.0 + tm_count * 0.25)

    # 4. Shooting zone bonus
    if attacking_right:
        dist_to_goal = math.sqrt((x - pitch.length) ** 2 + (y - pitch.width / 2) ** 2)
    else:
        dist_to_goal = math.sqrt(x ** 2 + (y - pitch.width / 2) ** 2)

    shot_zone_bonus = 1.0
    if dist_to_goal < config.shot_max_distance:
        shot_zone_bonus = 1.0 + 0.5 * (1.0 - dist_to_goal / config.shot_max_distance)

    # 5. Zone weight: based on angle to goal center (central = high, byline/corner = low)
    if attacking_right:
        goal_x = pitch.length
    else:
        goal_x = 0.0
    goal_y = pitch.width / 2.0
    
    # Vector from position to goal center
    dx_to_goal = goal_x - x
    dy_to_goal = goal_y - y
    dist_to_goal_center = math.sqrt(dx_to_goal * dx_to_goal + dy_to_goal * dy_to_goal)
    
    if dist_to_goal_center > 1.0:
        # Angle factor: directly facing goal = 1.0, extreme side = low
        # Use the ratio of x-component to total distance (how direct the path to goal is)
        directness = abs(dx_to_goal) / dist_to_goal_center  # 1.0 = directly facing, 0 = alongside goal line
        zone_weight = 0.3 + 0.7 * directness
    else:
        zone_weight = 1.0  # very close to goal, always high
    
    # Extra penalty for byline area (close to goal line but wide angle)
    if x_progress > 0.85:  # in final 15% of pitch
        y_center_dist = abs(y - pitch.width / 2) / (pitch.width / 2)
        if y_center_dist > 0.5:  # wide area near goal line
            zone_weight *= 0.4  # byline/corner area — low value

    # Combine
    value = goal_proximity * space_factor * crowding_factor * shot_zone_bonus * zone_weight

    # Clamp
    return max(0.01, min(1.0, value))


def position_value_batch(
    candidates: List[Tuple[float, float]],
    pitch: "Pitch",
    attacking_right: bool,
    opponent_positions: List[Tuple[float, float]],
    teammate_positions: List[Tuple[float, float]],
    config: "EngineConfig",
) -> List[float]:
    """Compute position_value for multiple positions (batch helper)."""
    return [
        position_value(x, y, pitch, attacking_right, opponent_positions, teammate_positions, config)
        for x, y in candidates
    ]
