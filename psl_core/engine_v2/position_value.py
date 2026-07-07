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


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def position_value(
    x: float,
    y: float,
    pitch: "Pitch",
    attacking_right: bool,
    opponent_positions: List[Tuple[float, float]],
    teammate_positions: List[Tuple[float, float]],
    config: "EngineConfig",
    runner_formation_pos: Tuple[float, float] = None,
) -> float:
    """Compute the attacking value of position (x, y).

    Returns a float roughly in [0, 1] where higher = more dangerous for the opponent.

    Factors:
    1. Goal proximity -- closer to opponent goal = higher
    2. Space -- fewer opponents nearby = higher
    3. No crowding -- too many teammates nearby = lower
    4. Shooting zone -- bonus if within shooting range
    5. Central bonus -- central positions slightly more valuable than extreme flanks
    6. Role distance decay -- soft penalty for being far from formation base (optional)
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
        dx = x - ox
        dy = y - oy
        d2 = dx * dx + dy * dy
        if d2 < 225.0:
            d = math.sqrt(d2)
            opp_count += (1.0 - d / 15.0) ** 0.7  # smooth decay
    # Defenders in final third have extra impact (they're organized to deny space)
    defender_weight = 1.2 if x_progress > 0.7 else 0.8
    space_factor = 1.0 / (1.0 + opp_count * defender_weight)

    # 3. Crowding penalty (too many teammates = redundant)
    tm_count = 0
    for tx, ty in teammate_positions:
        dx = x - tx
        dy = y - ty
        if dx * dx + dy * dy < 64.0:
            tm_count += 1
    crowding_factor = 1.0 / (1.0 + tm_count * 0.25)

    # 4. Shooting zone bonus
    if attacking_right:
        dist_to_goal = math.sqrt((x - pitch.length) ** 2 + (y - pitch.width / 2) ** 2)
    else:
        dist_to_goal = math.sqrt(x ** 2 + (y - pitch.width / 2) ** 2)

    box_danger = 1.0 - _smoothstep(12.0, 24.0, dist_to_goal)
    shot_zone_bonus = 0.86 + 0.64 * box_danger

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

    # Extra penalty for byline area (close to goal line but wide angle). This
    # is softened when team-mates occupy central box spaces, because the value
    # then comes from cut-back/cross creation rather than shooting angle.
    if x_progress > 0.85:  # in final 15% of pitch
        y_center_dist = abs(y - pitch.width / 2) / (pitch.width / 2)
        if y_center_dist > 0.5:  # wide area near goal line
            box_presence = 0.0
            for tx, ty in teammate_positions:
                tm_progress = tx / pitch.length if attacking_right else 1.0 - (tx / pitch.length)
                if tm_progress > 0.78:
                    centrality = 1.0 - min(1.0, abs(ty - pitch.width / 2) / (pitch.width / 2))
                    box_presence = max(box_presence, centrality)
            creation_value = _smoothstep(0.20, 0.75, box_presence)
            zone_weight *= 0.40 + 0.38 * creation_value

    # Long-range central areas are useful for circulation, but should not look
    # nearly as valuable as entering the box.
    if dist_to_goal > 28.0:
        zone_weight *= 0.72 + 0.28 * (1.0 - _smoothstep(28.0, 52.0, dist_to_goal))

    # Combine
    value = goal_proximity * space_factor * crowding_factor * shot_zone_bonus * zone_weight

    # 6. Role distance decay: soft pull toward formation base position
    if runner_formation_pos is not None:
        role_dist = math.sqrt(
            (x - runner_formation_pos[0]) ** 2 + (y - runner_formation_pos[1]) ** 2
        )
        role_distance_factor = max(0.2, 1.0 - role_dist / 30.0)
        value *= role_distance_factor

    # Clamp
    return max(0.01, min(1.0, value))


def receive_reachability(
    target_pos: Tuple[float, float],
    runner_pos: Tuple[float, float],
    runner_speed: float,
    opponent_positions: List[Tuple[float, float]],
    opponent_speeds: List[float],
    ball_pos: Tuple[float, float],
    ball_speed: float,
    config: "EngineConfig",
) -> float:
    """Can a teammate reach target_pos before defenders?

    Returns a value in [0, 1]: higher = runner arrives first with good margin.
    """
    tx, ty = target_pos
    # Time for runner to reach target
    dx = runner_pos[0] - tx
    dy = runner_pos[1] - ty
    dist_runner = math.sqrt(dx * dx + dy * dy)
    time_runner = dist_runner / max(runner_speed, 0.1)

    # Time for ball to reach target
    dx = ball_pos[0] - tx
    dy = ball_pos[1] - ty
    dist_ball = math.sqrt(dx * dx + dy * dy)
    time_ball = dist_ball / max(ball_speed, 0.1)

    # Find fastest defender to same point (exclude goalkeepers via caller filtering)
    time_def = float("inf")
    for i, (ox, oy) in enumerate(opponent_positions):
        dx = ox - tx
        dy = oy - ty
        d = math.sqrt(dx * dx + dy * dy)
        opp_spd = opponent_speeds[i] if i < len(opponent_speeds) else 4.0
        t = d / max(opp_spd, 0.1)
        if t < time_def:
            time_def = t

    # Advantage: positive means runner arrives first
    advantage = time_def - time_runner
    # Sigmoid-like mapping
    scale = config.receive_reachability_scale
    result = 0.5 + advantage * scale
    return max(0.0, min(1.0, result))


def space_creation_value(
    target_pos: Tuple[float, float],
    opponent_positions: List[Tuple[float, float]],
    teammate_positions: List[Tuple[float, float]],
    config: "EngineConfig",
) -> float:
    """Does moving here draw defenders away from teammates?

    Returns a multiplier >= 1.0 (up to 1.3): bonus for drawing pressure.
    """
    radius = config.space_creation_radius
    # Count defenders within radius of target (would be drawn to mark me)
    drawn_defenders = 0
    for ox, oy in opponent_positions:
        d = math.sqrt((ox - target_pos[0]) ** 2 + (oy - target_pos[1]) ** 2)
        if d < radius:
            drawn_defenders += 1

    # Those drawn defenders leave space for teammates
    bonus = 1.0 + drawn_defenders * 0.1  # slight bonus for drawing pressure
    return min(1.3, bonus)


def position_value_batch(
    candidates: List[Tuple[float, float]],
    pitch: "Pitch",
    attacking_right: bool,
    opponent_positions: List[Tuple[float, float]],
    teammate_positions: List[Tuple[float, float]],
    config: "EngineConfig",
    runner_formation_pos: Tuple[float, float] = None,
) -> List[float]:
    """Compute position_value for multiple positions (batch helper)."""
    return [
        position_value(
            x, y, pitch, attacking_right, opponent_positions, teammate_positions,
            config, runner_formation_pos=runner_formation_pos,
        )
        for x, y in candidates
    ]


def protection_value(
    pos: Tuple[float, float],
    ball_pos: Tuple[float, float],
    own_goal_x: float,
    pitch: "Pitch",
) -> float:
    """Value of a defensive position: high when between ball and own goal.

    Returns a float in [0.2, 1.0] representing how good this position is
    for covering the path from ball to the team's own goal.

    Args:
        pos: The candidate defensive position (x, y).
        ball_pos: Current ball position (x, y).
        own_goal_x: The x-coordinate of own goal (0.0 or pitch.length).
        pitch: Pitch object for dimensions.
    """
    ball_to_goal_x = own_goal_x - ball_pos[0]
    pos_to_goal_x = own_goal_x - pos[0]

    # Edge case: ball very close to goal line
    if abs(ball_to_goal_x) < 1.0:
        return 0.5

    # coverage: 0 = at ball position, 1 = at goal line
    coverage = pos_to_goal_x / ball_to_goal_x

    if coverage < 0 or coverage > 1:
        # Behind the ball (wrong side) or behind the goal
        return 0.2

    # Best around 0.3-0.6 (between ball and goal but not too close to either)
    return 0.4 + 0.6 * (1.0 - abs(coverage - 0.4) * 2.0)


def defensive_position_value(
    pos: Tuple[float, float],
    ball_pos: Tuple[float, float],
    own_goal_x: float,
    pitch: "Pitch",
    attackers: List[Tuple[float, float]],
    teammates: List[Tuple[float, float]],
    formation_pos: Tuple[float, float],
) -> float:
    """Evaluate a defensive position without forcing one global shape.

    High value means the position protects goal access, keeps a useful shape,
    covers attackers in the player's area, and avoids redundant crowding.
    """
    px, py = pos
    value = protection_value(pos, ball_pos, own_goal_x, pitch)
    ball_goal_dist = math.sqrt((ball_pos[0] - own_goal_x) ** 2 + (ball_pos[1] - pitch.width / 2.0) ** 2)
    box_danger = 1.0 - _smoothstep(20.0, 42.0, ball_goal_dist)
    pos_goal_dist = math.sqrt((px - own_goal_x) ** 2 + (py - pitch.width / 2.0) ** 2)
    centrality = 1.0 - min(1.0, abs(py - pitch.width / 2.0) / (pitch.width / 2.0))
    box_cover = (1.0 - _smoothstep(10.0, 28.0, pos_goal_dist)) * (0.45 + 0.55 * centrality)
    value *= 1.0 + box_danger * box_cover * 0.65

    # Closing the shot lane is a spatial value, not a separate rule. When the
    # ball is central and close enough to goal, positions on the line from ball
    # to goal should compete strongly with static shape and marking positions.
    goal_y = pitch.width / 2.0
    shot_dx = own_goal_x - ball_pos[0]
    shot_dy = goal_y - ball_pos[1]
    shot_len = math.sqrt(shot_dx * shot_dx + shot_dy * shot_dy)
    if shot_len > 1.0:
        nx, ny = shot_dx / shot_len, shot_dy / shot_len
        relx, rely = px - ball_pos[0], py - ball_pos[1]
        proj = relx * nx + rely * ny
        if 1.0 < proj < shot_len - 1.0:
            perp = abs(relx * ny - rely * nx)
            lane_value = 1.0 - _smoothstep(2.4, 9.0, perp)
            lane_depth = 1.0 - min(1.0, abs((proj / shot_len) - 0.38) / 0.46)
            ball_centrality = 1.0 - min(1.0, abs(ball_pos[1] - goal_y) / (pitch.width / 2.0))
            shot_lane_threat = (
                (1.0 - _smoothstep(24.0, 54.0, ball_goal_dist))
                * (0.45 + 0.55 * ball_centrality)
            )
            value *= 1.0 + shot_lane_threat * lane_value * (0.42 + 0.58 * lane_depth) * 0.86

    # Soft pull to the player's dynamic line/slot.
    form_dist = math.sqrt((px - formation_pos[0]) ** 2 + (py - formation_pos[1]) ** 2)
    shape_factor = max(0.25, 1.0 - form_dist / 28.0)
    value *= 0.55 + 0.45 * shape_factor

    # Reward being close enough to the most relevant attacker in this zone, but
    # avoid following him all the way into a team-mate's lane.
    if attackers:
        nearest_att = min(attackers, key=lambda a: math.sqrt((px - a[0]) ** 2 + (py - a[1]) ** 2))
        att_dist = math.sqrt((px - nearest_att[0]) ** 2 + (py - nearest_att[1]) ** 2)
        mark_factor = max(0.35, 1.0 - abs(att_dist - 4.0) / 18.0)
        value *= 0.70 + 0.30 * mark_factor

        # Lane denial: being near the segment from ball to attacker is useful.
        bx, by = ball_pos
        ax, ay = nearest_att
        dx = ax - bx
        dy = ay - by
        seg_len = math.sqrt(dx * dx + dy * dy)
        if seg_len > 1.0:
            nx, ny = dx / seg_len, dy / seg_len
            relx, rely = px - bx, py - by
            proj = relx * nx + rely * ny
            if 1.0 < proj < seg_len - 1.0:
                perp = abs(relx * ny - rely * nx)
                lane_factor = max(0.0, 1.0 - perp / 10.0)
                value *= 1.0 + 0.25 * lane_factor

    # Redundant crowding by defenders is bad. This is the main anti-swarm term.
    crowd = 0.0
    for tx, ty in teammates:
        d = math.sqrt((px - tx) ** 2 + (py - ty) ** 2)
        if d < 12.0:
            crowd += (1.0 - d / 12.0)
    value *= 1.0 / (1.0 + crowd * 0.75)

    # Extreme ball chasing can still be valuable for the responsible presser;
    # redundant crowding is already penalized above.
    ball_dist = math.sqrt((px - ball_pos[0]) ** 2 + (py - ball_pos[1]) ** 2)
    if ball_dist < 6.0:
        value *= 0.94

    return max(0.01, min(1.2, value))
