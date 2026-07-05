"""Unified state/action value model for engine v2.

The model gives all on-ball actions one currency: expected improvement of the
team's attacking state after accounting for success probability and risk.
"""

from __future__ import annotations

import math
from typing import List, Tuple, TYPE_CHECKING

from .physics import distance
from .position_value import position_value

if TYPE_CHECKING:
    from .config import EngineConfig
    from .pitch import Pitch
    from .player import Player


def goal_center(config: "EngineConfig", attacking_right: bool) -> Tuple[float, float]:
    return (
        config.pitch_length if attacking_right else 0.0,
        config.pitch_width / 2.0,
    )


def shot_quality_at(
    pos: Tuple[float, float],
    player: "Player",
    opponents: List["Player"],
    config: "EngineConfig",
    attacking_right: bool,
) -> float:
    """Approximate xG-like shot value from a position."""
    gx, gy = goal_center(config, attacking_right)
    dist = distance(pos, (gx, gy))
    if dist > config.shot_max_distance:
        return 0.0

    finishing = player.abilities.get("Finishing", 50) / 100.0
    long_shot = player.abilities.get("Long_Shot", 50) / 100.0
    ability = long_shot if dist > 25.0 else (finishing + long_shot) / 2.0 if dist > 18.0 else finishing

    if dist <= config.shot_ideal_distance:
        dist_factor = 1.0
    elif dist <= 30.0:
        dist_factor = max(0.25, 1.0 - (dist - config.shot_ideal_distance) * 0.055)
    else:
        dist_factor = 0.45 * math.exp(-(dist - 30.0) / 14.0)

    dx = abs(gx - pos[0])
    dy = abs(gy - pos[1])
    directness = dx / max(1.0, math.sqrt(dx * dx + dy * dy))
    angle_factor = max(0.15, min(1.0, directness))

    pressure_factor = 1.0
    lane_factor = 1.0
    shot_len = max(1.0, math.sqrt((gx - pos[0]) ** 2 + (gy - pos[1]) ** 2))
    nx = (gx - pos[0]) / shot_len
    ny = (gy - pos[1]) / shot_len
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        d = distance(pos, opp.pos)
        if d < 8.0:
            pressure_factor *= max(0.72, 1.0 - (8.0 - d) * 0.035)
        ox = opp.pos[0] - pos[0]
        oy = opp.pos[1] - pos[1]
        proj = ox * nx + oy * ny
        if 1.0 < proj < shot_len - 1.0:
            perp = abs(ox * ny - oy * nx)
            if perp < 4.5:
                lane_factor *= max(0.65, 1.0 - (4.5 - perp) * 0.05)

    on_target = (
        config.shot_on_target_base
        * (0.4 + 0.6 * ability)
        * dist_factor
        * angle_factor
        * pressure_factor
        * lane_factor
    )
    min_on_target = 0.16 if dist < 25.0 else 0.08
    on_target = max(min_on_target, min(0.78, on_target))

    save_estimate = config.gk_save_base
    save_estimate += (1.0 - angle_factor) * 0.12
    save_estimate += (1.0 - pressure_factor * lane_factor) * 0.10
    save_estimate -= min(0.18, max(0.0, (dist - 16.0) * 0.006))
    if dist < 18.0 and abs(pos[1] - gy) < 12.0:
        save_estimate -= 0.12
    save_estimate = max(0.35, min(0.90, save_estimate))

    xg = on_target * (1.0 - save_estimate)
    return max(0.0, min(0.65, xg))


def state_value(
    pos: Tuple[float, float],
    player: "Player",
    teammates: List["Player"],
    opponents: List["Player"],
    config: "EngineConfig",
    pitch: "Pitch",
    attacking_right: bool,
) -> float:
    """Value of this player controlling the ball at pos."""
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != player.index]
    spatial = position_value(pos[0], pos[1], pitch, attacking_right, opp_positions, tm_positions, config)
    shot = shot_quality_at(pos, player, opponents, config, attacking_right)
    progress = pos[0] / pitch.length if attacking_right else (pitch.length - pos[0]) / pitch.length

    # Passing potential: value of nearby team-mates as next outlets.
    outlet = 0.0
    for tm in teammates:
        if tm.index == player.index or tm.is_goalkeeper:
            continue
        d = distance(pos, tm.pos)
        if d > 45.0:
            continue
        tm_pv = position_value(tm.pos[0], tm.pos[1], pitch, attacking_right, opp_positions, tm_positions, config)
        outlet = max(outlet, tm_pv * max(0.2, 1.0 - d / 55.0))

    # The value of possession should be dominated by spatial threat and chance
    # quality. Outlet availability matters, but it must not make a harmless
    # backline possession state look better than an advanced attacking state.
    return max(0.01, min(1.2, spatial * 0.46 + progress * 0.18 + outlet * 0.10 + shot * 2.05))


def pass_receive_value(
    pos: Tuple[float, float],
    receiver: "Player",
    teammates: List["Player"],
    opponents: List["Player"],
    config: "EngineConfig",
    pitch: "Pitch",
    attacking_right: bool,
) -> float:
    """Value immediately after receiving a pass at pos.

    This is stricter than state_value: a pass should improve immediate attacking
    prospects, not merely move the ball to a safe outlet that has future outlets.
    """
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != receiver.index]
    spatial = position_value(pos[0], pos[1], pitch, attacking_right, opp_positions, tm_positions, config)
    shot = shot_quality_at(pos, receiver, opponents, config, attacking_right)
    progress = pos[0] / pitch.length if attacking_right else (pitch.length - pos[0]) / pitch.length
    pressure = receiver_pressure(pos, opponents)
    outlet = 0.0
    for tm in teammates:
        if tm.index == receiver.index or tm.is_goalkeeper:
            continue
        d = distance(pos, tm.pos)
        if d > 35.0:
            continue
        outlet_pv = position_value(tm.pos[0], tm.pos[1], pitch, attacking_right, opp_positions, tm_positions, config)
        outlet = max(outlet, outlet_pv * max(0.15, 1.0 - d / 45.0))

    return max(0.01, min(1.2, spatial * 0.40 + progress * 0.24 + outlet * 0.12 + shot * 2.15 - pressure * 0.16))


def action_delta_score(
    current_value: float,
    after_value: float,
    success_prob: float,
    risk_cost: float,
    continuity: float = 0.0,
) -> float:
    """Expected action score from current -> after state."""
    delta = after_value - current_value
    return max(0.0, success_prob * (delta + continuity) - risk_cost)


def pass_lane_risk(
    origin: Tuple[float, float],
    target: Tuple[float, float],
    opponents: List["Player"],
    config: "EngineConfig",
) -> float:
    """Risk that defenders can affect the ball along the pass lane."""
    ox, oy = origin
    tx, ty = target
    dx = tx - ox
    dy = ty - oy
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1.0:
        return 1.0

    nx, ny = dx / length, dy / length
    risk = 0.0
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        rel_x = opp.pos[0] - ox
        rel_y = opp.pos[1] - oy
        proj = rel_x * nx + rel_y * ny
        if proj <= 1.5 or proj >= length - 1.5:
            continue
        perp = abs(rel_x * ny - rel_y * nx)
        reach = config.interception_reach * 1.8
        if perp < reach:
            lane_share = 1.0 - perp / reach
            centrality = 1.0 - abs(proj / length - 0.5) * 0.45
            risk += lane_share * centrality
    length_factor = min(1.4, length / 35.0)
    return max(0.0, min(1.0, risk * 0.28 * length_factor))


def receiver_pressure(
    target: Tuple[float, float],
    opponents: List["Player"],
) -> float:
    """Pressure around the receiving point."""
    pressure = 0.0
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        d = distance(target, opp.pos)
        if d < 12.0:
            pressure += (1.0 - d / 12.0)
    return max(0.0, min(1.0, pressure * 0.35))


def turnover_consequence(
    loss_pos: Tuple[float, float],
    opponents: List["Player"],
    config: "EngineConfig",
    attacking_right: bool,
) -> float:
    """How costly it is if possession is lost near this pass lane/target."""
    # Consequence is high when the loss is close to our own goal or central.
    own_goal_x = 0.0 if attacking_right else config.pitch_length
    own_goal = (own_goal_x, config.pitch_width / 2.0)
    d_goal = distance(loss_pos, own_goal)
    goal_danger = max(0.0, 1.0 - d_goal / 60.0)
    central = 1.0 - min(1.0, abs(loss_pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))

    nearby_opps = 0.0
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        d = distance(loss_pos, opp.pos)
        if d < 18.0:
            nearby_opps += 1.0 - d / 18.0

    return max(0.05, min(1.0, goal_danger * 0.55 + central * 0.20 + min(1.0, nearby_opps * 0.25)))


def expected_pass_value(
    passer: "Player",
    receiver: "Player",
    origin: Tuple[float, float],
    target: Tuple[float, float],
    teammates: List["Player"],
    opponents: List["Player"],
    config: "EngineConfig",
    pitch: "Pitch",
    attacking_right: bool,
    current_value: float,
    base_accuracy: float,
    receiver_arrival: float = 1.0,
    continuity: float = 0.03,
) -> Tuple[float, float, float, float]:
    """Unified pass score and risk components.

    Returns (score, success_prob, lane_risk, consequence).
    """
    lane_risk = pass_lane_risk(origin, target, opponents, config)
    pressure = receiver_pressure(target, opponents)
    success_prob = base_accuracy * receiver_arrival * (1.0 - lane_risk * 0.92) * (1.0 - pressure * 0.55)
    success_prob = max(0.02, min(0.95, success_prob))

    after_value = pass_receive_value(target, receiver, teammates, opponents, config, pitch, attacking_right)
    consequence_point = ((origin[0] + target[0]) / 2.0, (origin[1] + target[1]) / 2.0)
    consequence = turnover_consequence(consequence_point, opponents, config, attacking_right)
    risk_cost = (1.0 - success_prob) * (0.07 + 0.24 * consequence)
    delta = after_value - current_value
    if delta < -0.08:
        continuity *= 0.25
    score = action_delta_score(current_value, after_value, success_prob, risk_cost, continuity)
    return score, success_prob, lane_risk, consequence
