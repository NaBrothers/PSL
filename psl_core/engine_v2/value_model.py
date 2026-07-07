"""Unified state/action value model for engine v2.

The model gives all on-ball actions one currency: expected improvement of the
team's attacking state after accounting for success probability and risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, TYPE_CHECKING

from .physics import distance
from .position_value import position_value

if TYPE_CHECKING:
    from .config import EngineConfig
    from .pitch import Pitch
    from .player import Player


def _json_safe(value):
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = _clamp01((value - edge0) / max(1e-6, edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


@dataclass
class ValueResult:
    """Stable score breakdown for a decision candidate."""

    score: float
    success_prob: float = 1.0
    risk_cost: float = 0.0
    current_value: float = 0.0
    after_value: float = 0.0
    components: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        components = dict(self.components)
        components.setdefault("current_value", self.current_value)
        components.setdefault("after_value", self.after_value)
        components.setdefault("delta", self.after_value - self.current_value)
        components.setdefault("success_prob", self.success_prob)
        components.setdefault("risk_cost", self.risk_cost)
        components.setdefault("final_score", self.score)
        return {
            "score": self.score,
            "success_prob": self.success_prob,
            "risk_cost": self.risk_cost,
            "current_value": self.current_value,
            "after_value": self.after_value,
            "components": _json_safe(components),
        }


@dataclass
class ActionCandidate:
    """Traceable action candidate with legacy tuple compatibility."""

    phase: str
    action_type: str
    target: Optional[Tuple[float, float]]
    value: ValueResult
    details: dict = field(default_factory=dict)
    source: str = ""

    @property
    def score(self) -> float:
        return self.value.score

    def as_tuple(self) -> Tuple[float, str, dict]:
        return (self.value.score, self.action_type, self.details)

    def with_score(self, score: float) -> "ActionCandidate":
        return ActionCandidate(
            phase=self.phase,
            action_type=self.action_type,
            target=self.target,
            value=ValueResult(
                score=score,
                success_prob=self.value.success_prob,
                risk_cost=self.value.risk_cost,
                current_value=self.value.current_value,
                after_value=self.value.after_value,
                components=dict(self.value.components),
            ),
            details=self.details,
            source=self.source,
        )

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "action_type": self.action_type,
            "target": _json_safe(self.target),
            "value": self.value.to_dict(),
            "details": _json_safe(self.details),
            "source": self.source,
        }


def goal_center(config: "EngineConfig", attacking_right: bool) -> Tuple[float, float]:
    return (
        config.pitch_length if attacking_right else 0.0,
        config.pitch_width / 2.0,
    )


def _is_outside_penalty_area(
    pos: Tuple[float, float],
    config: "EngineConfig",
    attacking_right: bool,
) -> bool:
    progress = pos[0] / max(1.0, config.pitch_length) if attacking_right else (config.pitch_length - pos[0]) / max(1.0, config.pitch_length)
    return (
        progress <= 1.0 - 16.5 / max(1.0, config.pitch_length)
        or abs(pos[1] - config.pitch_width / 2.0) >= 20.2
    )


def _receiver_goal_arrival_space(
    receiver_goal,
    target: Tuple[float, float],
    *,
    target_progress: float,
    centrality: float,
    pressure: float,
) -> float:
    if receiver_goal is None:
        return 0.0

    goal_type = getattr(receiver_goal, "goal_type", "")
    goal_target = getattr(receiver_goal, "target_pos", target)
    goal_fit = max(0.0, 1.0 - distance(target, goal_target) / 15.0)
    goal_value = max(0.0, min(1.0, float(getattr(receiver_goal, "value", 0.0) or 0.0) * 4.0))
    low_pressure = 1.0 - _smoothstep(0.35, 0.82, pressure)

    if goal_type == "arc_arrival_for_cutback":
        return (
            goal_fit
            * goal_value
            * _smoothstep(0.62, 0.84, target_progress)
            * _smoothstep(0.46, 0.88, centrality)
            * low_pressure
        )

    if goal_type == "attack_far_post":
        return (
            goal_fit
            * goal_value
            * _smoothstep(0.78, 0.94, target_progress)
            * _smoothstep(0.28, 0.76, centrality)
            * low_pressure
        )

    return 0.0


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

    finishing = player.abilities.get("Finishing", 50) / 100.0
    long_shot = player.abilities.get("Long_Shot", 50) / 100.0
    ability = long_shot if dist > 25.0 else (finishing + long_shot) / 2.0 if dist > 18.0 else finishing

    if dist <= config.shot_ideal_distance:
        dist_factor = 1.0
    elif dist <= 30.0:
        dist_factor = max(0.18, 1.0 - (dist - config.shot_ideal_distance) * 0.070)
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
    outside_box = _is_outside_penalty_area(pos, config, attacking_right)
    if outside_box:
        outside_penalty = 0.76 + 0.24 * _smoothstep(21.0, 32.0, dist)
        on_target *= outside_penalty
    min_on_target = 0.13 if dist < 25.0 else 0.055
    on_target = max(min_on_target, min(0.78, on_target))

    save_estimate = config.gk_save_base
    save_estimate += (1.0 - angle_factor) * 0.12
    save_estimate += (1.0 - pressure_factor * lane_factor) * 0.10
    save_estimate -= min(0.12, max(0.0, (dist - 16.0) * 0.0035))
    if not outside_box and dist < 18.0 and abs(pos[1] - gy) < 12.0:
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
    centrality = 1.0 - min(1.0, abs(pos[1] - pitch.width / 2.0) / (pitch.width / 2.0))
    width_value = 1.0 - centrality
    target_width = abs(pos[1] - pitch.width / 2.0) / (pitch.width / 2.0)
    anchor = getattr(receiver, "tactical_anchor", pos)
    base = getattr(receiver, "base_formation_pos", anchor)
    anchor_width = abs(anchor[1] - pitch.width / 2.0) / (pitch.width / 2.0)
    base_progress = base[0] / pitch.length if attacking_right else (pitch.length - base[0]) / pitch.length
    inside_arrival = (
        _smoothstep(0.64, 0.84, progress)
        * _smoothstep(0.38, 0.76, centrality)
        * (1.0 - _smoothstep(0.86, 0.96, progress))
        * _smoothstep(0.12, 0.50, max(0.0, anchor_width - target_width))
        * (1.0 - _smoothstep(0.35, 0.82, pressure))
    )
    second_line_arrival = (
        _smoothstep(0.64, 0.84, progress)
        * _smoothstep(0.42, 0.84, centrality)
        * (1.0 - _smoothstep(0.84, 0.95, progress))
        * _smoothstep(0.04, 0.24, max(0.0, progress - base_progress))
        * (1.0 - _smoothstep(0.35, 0.82, pressure))
    )
    receiver_goal = getattr(receiver, "current_goal", None)
    receiver_goal_arrival = _receiver_goal_arrival_space(
        receiver_goal,
        pos,
        target_progress=progress,
        centrality=centrality,
        pressure=pressure,
    )
    wide_creation = (
        _smoothstep(0.56, 0.78, progress)
        * _smoothstep(0.38, 0.72, width_value)
        * (1.0 - _smoothstep(0.35, 0.78, pressure))
    )
    box_presence = 0.0
    for tm in teammates:
        if tm.index == receiver.index or tm.is_goalkeeper:
            continue
        tm_progress = tm.pos[0] / pitch.length if attacking_right else (pitch.length - tm.pos[0]) / pitch.length
        if tm_progress > 0.74:
            tm_centrality = 1.0 - min(1.0, abs(tm.pos[1] - pitch.width / 2.0) / (pitch.width / 2.0))
            box_presence = max(box_presence, tm_centrality)
    wide_creation *= 0.55 + 0.45 * _smoothstep(0.18, 0.70, box_presence)
    outlet = 0.0
    for tm in teammates:
        if tm.index == receiver.index or tm.is_goalkeeper:
            continue
        d = distance(pos, tm.pos)
        if d > 35.0:
            continue
        outlet_pv = position_value(tm.pos[0], tm.pos[1], pitch, attacking_right, opp_positions, tm_positions, config)
        outlet = max(outlet, outlet_pv * max(0.15, 1.0 - d / 45.0))

    return max(0.01, min(
        1.2,
        spatial * 0.40
        + progress * 0.24
        + outlet * 0.12
        + shot * 2.15
        + wide_creation * 0.095
        + inside_arrival * 0.045
        + second_line_arrival * 0.040
        + receiver_goal_arrival * 0.075
        - pressure * 0.16,
    ))


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
    result = expected_pass_value_result(
        passer, receiver, origin, target,
        teammates, opponents, config, pitch, attacking_right,
        current_value, base_accuracy,
        receiver_arrival=receiver_arrival,
        continuity=continuity,
    )
    return (
        result.score,
        result.success_prob,
        result.components["lane_risk"],
        result.components["turnover_consequence"],
    )


def expected_pass_value_result(
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
) -> ValueResult:
    """Unified pass value with trace-ready components."""
    lane_risk = pass_lane_risk(origin, target, opponents, config)
    pressure = receiver_pressure(target, opponents)
    success_prob = base_accuracy * receiver_arrival * (1.0 - lane_risk * 0.92) * (1.0 - pressure * 0.55)
    success_prob = max(0.02, min(0.95, success_prob))

    after_value = pass_receive_value(target, receiver, teammates, opponents, config, pitch, attacking_right)
    consequence_point = ((origin[0] + target[0]) / 2.0, (origin[1] + target[1]) / 2.0)
    consequence = turnover_consequence(consequence_point, opponents, config, attacking_right)
    forward_dir = 1.0 if attacking_right else -1.0
    progress_gain = (target[0] - origin[0]) * forward_dir / max(1.0, config.pitch_length)
    lateral_change = abs(target[1] - origin[1]) / max(1.0, config.pitch_width)
    target_progress = target[0] / max(1.0, pitch.length) if attacking_right else (pitch.length - target[0]) / max(1.0, pitch.length)
    centrality = 1.0 - min(1.0, abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0))
    width_value = 1.0 - centrality
    target_width = abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0)
    receiver_anchor = getattr(receiver, "tactical_anchor", target)
    receiver_base = getattr(receiver, "base_formation_pos", receiver_anchor)
    anchor_width = abs(receiver_anchor[1] - pitch.width / 2.0) / (pitch.width / 2.0)
    receiver_base_progress = receiver_base[0] / max(1.0, pitch.length) if attacking_right else (pitch.length - receiver_base[0]) / max(1.0, pitch.length)
    origin_progress = origin[0] / max(1.0, pitch.length) if attacking_right else (pitch.length - origin[0]) / max(1.0, pitch.length)
    attracted_pressure = 0.0
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        d = distance(origin, opp.pos)
        if d < 11.0:
            attracted_pressure += 1.0 - d / 11.0
    attracted_pressure = min(1.0, attracted_pressure * 0.42)
    pressured_possession = (
        _smoothstep(0.78, 0.92, origin_progress)
        * _smoothstep(0.18, 0.65, attracted_pressure)
        * _smoothstep(1.0, 3.0, max(0, passer.consecutive_carries))
    )
    stale_possession = (
        _smoothstep(0.62, 0.86, origin_progress)
        * _smoothstep(1.0, 4.0, max(0, passer.consecutive_carries))
        * (0.38 + 0.62 * _smoothstep(0.08, 0.55, attracted_pressure))
    )
    effective_current_value = current_value * (
        1.0 - 0.22 * pressured_possession - 0.18 * stale_possession
    )
    delta = after_value - effective_current_value
    high_threat_space = (
        _smoothstep(0.72, 0.90, target_progress)
        * _smoothstep(0.24, 0.52, centrality)
        * _smoothstep(0.04, 0.18, max(0.0, delta))
        * (1.0 - _smoothstep(0.45, 0.85, pressure))
    )
    final_third_combination = (
        _smoothstep(0.78, 0.92, origin_progress)
        * _smoothstep(0.70, 0.84, target_progress)
        * _smoothstep(0.35, 0.70, centrality)
        * _smoothstep(0.04, 0.18, max(0.0, delta))
        * (1.0 - _smoothstep(0.35, 0.80, pressure))
    )
    cutback_value = final_third_combination * (
        0.035
        + 0.18 * max(0.0, delta)
        + 0.050 * _smoothstep(0.08, 0.38, lateral_change)
    )
    layoff_retention_space = (
        _smoothstep(0.80, 0.92, origin_progress)
        * _smoothstep(0.56, 0.76, target_progress)
        * _smoothstep(0.24, 0.72, centrality)
        * _smoothstep(-0.55, -0.18, delta)
        * (1.0 - _smoothstep(0.42, 0.86, pressure))
    )
    layoff_retention_value = layoff_retention_space * (
        0.035
        + 0.070 * success_prob
        + 0.030 * _smoothstep(0.04, 0.24, lateral_change)
    )
    target_distance = distance(origin, target)
    pressure_release_space = (
        _smoothstep(0.78, 0.92, origin_progress)
        * _smoothstep(0.18, 0.65, attracted_pressure)
        * _smoothstep(1.0, 3.0, max(0, passer.consecutive_carries))
        * _smoothstep(6.0, 14.0, target_distance)
        * (1.0 - _smoothstep(24.0, 34.0, target_distance))
        * (1.0 - _smoothstep(0.40, 0.86, pressure))
    )
    pressure_release_value = pressure_release_space * (
        0.075
        + 0.120 * success_prob
        + 0.055 * _smoothstep(0.06, 0.30, lateral_change)
    )
    stale_release_space = (
        _smoothstep(0.62, 0.86, origin_progress)
        * _smoothstep(1.0, 4.0, max(0, passer.consecutive_carries))
        * _smoothstep(4.0, 12.0, target_distance)
        * (1.0 - _smoothstep(30.0, 44.0, target_distance))
        * (1.0 - _smoothstep(0.45, 0.88, pressure))
        * (0.58 + 0.42 * _smoothstep(0.04, 0.28, lateral_change))
        * (0.62 + 0.38 * _smoothstep(0.0, 0.18, max(0.0, -progress_gain)))
    )
    stale_release_value = stale_release_space * (
        0.085
        + 0.185 * success_prob
        + 0.055 * _smoothstep(0.04, 0.26, lateral_change)
        + 0.040 * _smoothstep(0.0, 0.22, max(0.0, -delta))
    )
    wide_creation_space = (
        _smoothstep(0.56, 0.78, target_progress)
        * _smoothstep(0.32, 0.68, width_value)
        * _smoothstep(0.02, 0.12, max(0.0, delta))
        * (1.0 - _smoothstep(0.42, 0.86, pressure))
    )
    inside_arrival_space = (
        _smoothstep(0.64, 0.84, target_progress)
        * _smoothstep(0.38, 0.76, centrality)
        * (1.0 - _smoothstep(0.86, 0.96, target_progress))
        * _smoothstep(0.12, 0.50, max(0.0, anchor_width - target_width))
        * (1.0 - _smoothstep(0.35, 0.82, pressure))
    )
    second_line_arrival_space = (
        _smoothstep(0.64, 0.84, target_progress)
        * _smoothstep(0.42, 0.84, centrality)
        * (1.0 - _smoothstep(0.84, 0.95, target_progress))
        * _smoothstep(0.04, 0.24, max(0.0, target_progress - receiver_base_progress))
        * (1.0 - _smoothstep(0.35, 0.82, pressure))
    )
    receiver_goal = getattr(receiver, "current_goal", None)
    receiver_goal_arrival_space = _receiver_goal_arrival_space(
        receiver_goal,
        target,
        target_progress=target_progress,
        centrality=centrality,
        pressure=pressure,
    )
    origin_width = abs(origin[1] - pitch.width / 2.0) / (pitch.width / 2.0)
    second_line_cutback_space = (
        _smoothstep(0.62, 0.82, origin_progress)
        * _smoothstep(0.38, 0.74, origin_width)
        * _smoothstep(0.68, 0.82, target_progress)
        * (1.0 - _smoothstep(0.84, 0.94, target_progress))
        * _smoothstep(0.62, 0.92, centrality)
        * _smoothstep(0.06, 0.26, max(0.0, target_progress - receiver_base_progress))
        * (1.0 - _smoothstep(0.32, 0.78, pressure))
    )
    high_central_holder = (
        _smoothstep(0.72, 0.90, origin_progress)
        * _smoothstep(0.54, 0.94, centrality)
    )
    layoff_depth = (origin[0] - target[0]) * (1.0 if attacking_right else -1.0)
    current_shot_for_layoff = shot_quality_at(origin, passer, opponents, config, attacking_right)
    poor_current_shot = 1.0 - _smoothstep(0.075, 0.145, current_shot_for_layoff)
    support_lane_change = _smoothstep(0.05, 0.30, lateral_change)
    layoff_support_space = (
        high_central_holder
        * _smoothstep(0.54, 0.82, target_progress)
        * (1.0 - _smoothstep(0.84, 0.95, target_progress))
        * _smoothstep(2.0, 12.0, layoff_depth)
        * (1.0 - _smoothstep(24.0, 36.0, layoff_depth))
        * _smoothstep(0.28, 0.86, centrality)
        * (0.55 + 0.45 * support_lane_change)
        * (1.0 - _smoothstep(0.36, 0.82, pressure))
        * (0.55 + 0.45 * poor_current_shot)
    )
    short_combination_space = (
        _smoothstep(0.68, 0.90, origin_progress)
        * _smoothstep(5.0, 13.0, target_distance)
        * (1.0 - _smoothstep(24.0, 34.0, target_distance))
        * _smoothstep(0.08, 0.44, lateral_change)
        * (1.0 - _smoothstep(0.42, 0.86, pressure))
        * (0.55 + 0.45 * poor_current_shot)
    )
    wide_creation_value = wide_creation_space * (
        0.030
        + 0.11 * max(0.0, delta)
        + 0.045 * _smoothstep(0.08, 0.32, lateral_change)
        + 0.035 * _smoothstep(0.02, 0.14, max(0.0, progress_gain))
    )
    inside_arrival_value = inside_arrival_space * (
        0.018
        + 0.038 * success_prob
        + 0.020 * _smoothstep(0.02, 0.12, max(0.0, delta))
    )
    second_line_arrival_value = second_line_arrival_space * (
        0.016
        + 0.034 * success_prob
        + 0.018 * _smoothstep(0.02, 0.12, max(0.0, delta))
    )
    receiver_goal_arrival_value = receiver_goal_arrival_space * (
        0.030
        + 0.060 * success_prob
        + 0.030 * _smoothstep(0.0, 0.12, max(0.0, delta))
    )
    second_line_cutback_value = second_line_cutback_space * (
        0.034
        + 0.050 * success_prob
        + 0.020 * _smoothstep(0.04, 0.22, lateral_change)
        + 0.070 * max(0.0, delta)
    )
    layoff_support_value = layoff_support_space * (
        0.052
        + 0.084 * success_prob
        + 0.040 * support_lane_change
        + 0.058 * _smoothstep(0.0, 0.18, max(0.0, -progress_gain))
        + 0.045 * poor_current_shot
    )
    short_combination_value = short_combination_space * (
        0.032
        + 0.064 * success_prob
        + 0.034 * _smoothstep(0.04, 0.22, lateral_change)
        + 0.026 * poor_current_shot
    )
    chance_creation_value = high_threat_space * (
        0.045
        + 0.16 * max(0.0, delta)
        + 0.08 * max(0.0, progress_gain)
    ) + cutback_value + wide_creation_value + inside_arrival_value + second_line_arrival_value + receiver_goal_arrival_value + second_line_cutback_value + layoff_support_value + short_combination_value + layoff_retention_value + pressure_release_value + stale_release_value
    success_quality = _smoothstep(0.10, 0.38, success_prob)
    risk_budget = high_threat_space * (
        0.030
        + 0.070 * _smoothstep(0.05, 0.22, max(0.0, delta))
        + 0.035 * _smoothstep(0.02, 0.12, max(0.0, progress_gain))
    ) + final_third_combination * (
        0.020
        + 0.050 * _smoothstep(0.05, 0.20, max(0.0, delta))
    ) + wide_creation_space * (
        0.018
        + 0.045 * _smoothstep(0.04, 0.16, max(0.0, delta))
    ) + inside_arrival_space * (
        0.012
        + 0.022 * success_prob
    ) + second_line_arrival_space * (
        0.010
        + 0.020 * success_prob
    ) + receiver_goal_arrival_space * (
        0.014
        + 0.026 * success_prob
    ) + second_line_cutback_space * (
        0.022
        + 0.044 * success_prob
    ) + layoff_support_space * (
        0.024
        + 0.048 * success_prob
    ) + short_combination_space * (
        0.014
        + 0.030 * success_prob
    ) + layoff_retention_space * (
        0.025
        + 0.035 * success_prob
    ) + pressure_release_space * (
        0.040
        + 0.075 * success_prob
    ) + stale_release_space * (
        0.045
        + 0.085 * success_prob
    )
    risk_budget *= 0.20 + 0.80 * success_quality
    risk_cost = max(
        0.0,
        (1.0 - success_prob) * (0.07 + 0.24 * consequence) - risk_budget,
    )
    safe_retain_value = success_prob * (1.0 - lane_risk) * (1.0 - pressure)
    negative_delta = max(0.0, -delta)
    effective_delta = delta + negative_delta * safe_retain_value * 0.72
    recycle_value = safe_retain_value * (0.022 + 0.038 * _smoothstep(0.04, 0.26, lateral_change))
    progression_value = safe_retain_value * max(0.0, progress_gain) * 0.18
    rhythm_value = safe_retain_value * 0.018
    continuity *= 0.25 + 0.75 * _smoothstep(-0.08, 0.02, delta)
    continuity += min(0.070, max(0.0, delta) * 0.40)
    safe_receiver_bonus = 1.0 - _smoothstep(0.15, 0.45, pressure)
    safe_lane_bonus = 1.0 - _smoothstep(0.15, 0.45, lane_risk)
    continuity += 0.030 * safe_receiver_bonus * safe_lane_bonus
    continuity += (layoff_support_space + short_combination_space) * safe_retain_value * (
        0.030 + 0.055 * poor_current_shot
    )
    continuity += recycle_value + progression_value + rhythm_value + chance_creation_value
    score = max(0.0, success_prob * (effective_delta + continuity) - risk_cost)
    positive_delta_bonus = 1.0 + 0.45 * _smoothstep(0.04, 0.16, delta)
    score *= positive_delta_bonus
    current_shot = shot_quality_at(origin, passer, opponents, config, attacking_right)
    current_shot_window = (
        _smoothstep(0.065, 0.155, current_shot)
        * _smoothstep(0.68, 0.88, origin_progress)
        * (1.0 - _smoothstep(0.35, 0.78, attracted_pressure))
    )
    pass_can_pay_for_window = max(
        high_threat_space,
        final_third_combination,
        pressure_release_space * 0.70,
        stale_release_space * 0.55,
    ) * success_quality
    shoot_window_release_cost = current_shot_window * (
        0.026
        + 0.20 * current_shot
        + 0.035 * _smoothstep(0.0, 0.10, max(0.0, -progress_gain))
        + 0.025 * _smoothstep(0.0, 0.22, max(0.0, -delta))
    ) * (1.0 - 0.72 * _smoothstep(0.18, 0.75, pass_can_pay_for_window))
    score = max(0.0, score - shoot_window_release_cost)
    return ValueResult(
        score=score,
        success_prob=success_prob,
        risk_cost=risk_cost,
        current_value=current_value,
        after_value=after_value,
        components={
            "current_value": current_value,
            "effective_current_value": effective_current_value,
            "after_value": after_value,
            "delta": after_value - effective_current_value,
            "success_prob": success_prob,
            "risk_cost": risk_cost,
            "opportunity_cost": 0.0,
            "continuity": continuity,
            "final_score": score,
            "base_accuracy": base_accuracy,
            "lane_risk": lane_risk,
            "receiver_pressure": pressure,
            "turnover_consequence": consequence,
            "receiver_arrival": receiver_arrival,
            "positive_delta_bonus": positive_delta_bonus,
            "progress_gain": progress_gain,
            "lateral_change": lateral_change,
            "target_progress": target_progress,
            "origin_progress": origin_progress,
            "centrality": centrality,
            "width_value": width_value,
            "high_threat_space": high_threat_space,
            "final_third_combination": final_third_combination,
            "cutback_value": cutback_value,
            "layoff_retention_space": layoff_retention_space,
            "layoff_retention_value": layoff_retention_value,
            "attracted_pressure": attracted_pressure,
            "pressured_possession": pressured_possession,
            "stale_possession": stale_possession,
            "pressure_release_space": pressure_release_space,
            "pressure_release_value": pressure_release_value,
            "stale_release_space": stale_release_space,
            "stale_release_value": stale_release_value,
            "wide_creation_space": wide_creation_space,
            "wide_creation_value": wide_creation_value,
            "inside_arrival_space": inside_arrival_space,
            "inside_arrival_value": inside_arrival_value,
            "second_line_arrival_space": second_line_arrival_space,
            "second_line_arrival_value": second_line_arrival_value,
            "receiver_goal_arrival_space": receiver_goal_arrival_space,
            "receiver_goal_arrival_value": receiver_goal_arrival_value,
            "second_line_cutback_space": second_line_cutback_space,
            "second_line_cutback_value": second_line_cutback_value,
            "layoff_support_space": layoff_support_space,
            "layoff_support_value": layoff_support_value,
            "short_combination_space": short_combination_space,
            "short_combination_value": short_combination_value,
            "poor_current_shot": poor_current_shot,
            "support_lane_change": support_lane_change,
            "success_quality": success_quality,
            "chance_creation_value": chance_creation_value,
            "risk_budget": risk_budget,
            "effective_delta": effective_delta,
            "recycle_value": recycle_value,
            "progression_value": progression_value,
            "rhythm_value": rhythm_value,
            "current_shot": current_shot,
            "current_shot_window": current_shot_window,
            "pass_can_pay_for_window": pass_can_pay_for_window,
            "shoot_window_release_cost": shoot_window_release_cost,
        },
    )


def evaluate_pass_target(*args, **kwargs) -> ValueResult:
    """Canonical pass evaluator alias used by player candidate generation."""
    return expected_pass_value_result(*args, **kwargs)


def evaluate_carry_target(
    carrier: "Player",
    target: Tuple[float, float],
    target_pv: float,
    current_pv: float,
    current_state_value: float,
    path_feasibility: float,
    teammates: List["Player"],
    opponents: List["Player"],
    config: "EngineConfig",
    pitch: "Pitch",
    attacking_right: bool,
) -> ValueResult:
    """Evaluate a carry target using the existing carry formula."""
    after_value = state_value(
        target, carrier, teammates, opponents, config, pitch, attacking_right
    )
    current_shot = shot_quality_at(carrier.pos, carrier, opponents, config, attacking_right)
    target_shot = shot_quality_at(target, carrier, opponents, config, attacking_right)
    shot_quality_gain = max(0.0, target_shot - current_shot)
    risk_cost = (1.0 - path_feasibility) * 0.10
    pv_gain = target_pv - current_pv

    goal_x = config.pitch_length if attacking_right else 0.0
    goal_y = config.pitch_width / 2.0
    forward_dir = 1.0 if attacking_right else -1.0
    old_goal_dist = distance(carrier.pos, (goal_x, goal_y))
    new_goal_dist = distance(target, (goal_x, goal_y))
    old_angle_width = abs(carrier.pos[1] - goal_y)
    new_angle_width = abs(target[1] - goal_y)
    width_base = max(1.0, config.pitch_width / 2.0)
    lane_gain = max(0.0, old_angle_width - new_angle_width) / width_base
    progress_gain = max(0.0, (target[0] - carrier.pos[0]) * forward_dir) / max(1.0, config.pitch_length)
    # One-step lookahead for continuous carries. A cut-in often needs the first
    # touch to enter a better shooting lane and the next touch to create the
    # actual shot; evaluating only the immediate target makes that first touch
    # look artificially weak.
    step = max(3.0, min(7.5, config.carrier_speed * 1.75))
    future_points = []
    to_goal_x = goal_x - target[0]
    to_goal_y = goal_y - target[1]
    to_goal_len = max(1.0, math.sqrt(to_goal_x * to_goal_x + to_goal_y * to_goal_y))
    future_points.append((
        target[0] + to_goal_x / to_goal_len * step,
        target[1] + to_goal_y / to_goal_len * step,
    ))
    future_points.append((
        target[0] + forward_dir * step * 0.70,
        target[1] + (goal_y - target[1]) * 0.55,
    ))
    future_points.append((
        target[0] + forward_dir * step * 0.45,
        target[1] + (goal_y - target[1]) * 0.85,
    ))
    future_shot = target_shot
    for fx, fy in future_points:
        fpos = pitch.clamp(fx, fy)
        future_shot = max(
            future_shot,
            shot_quality_at(fpos, carrier, opponents, config, attacking_right),
        )
    future_shot_gain = max(0.0, future_shot - current_shot)
    old_progress = carrier.pos[0] / max(1.0, pitch.length) if attacking_right else (pitch.length - carrier.pos[0]) / max(1.0, pitch.length)
    old_width_ratio = old_angle_width / max(1.0, config.pitch_width / 2.0)
    new_width_ratio = new_angle_width / max(1.0, config.pitch_width / 2.0)
    target_progress = target[0] / max(1.0, pitch.length) if attacking_right else (pitch.length - target[0]) / max(1.0, pitch.length)
    target_centrality = 1.0 - min(1.0, abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0))
    half_space_entry = (
        _smoothstep(0.58, 0.78, old_progress)
        * (1.0 - _smoothstep(0.84, 0.92, old_progress))
        * _smoothstep(0.20, 0.50, old_width_ratio)
        * _smoothstep(0.025, 0.18, old_width_ratio - new_width_ratio)
        * (0.35 + 0.65 * _smoothstep(0.006, 0.050, future_shot_gain))
    )
    carry_to_shoot_window = future_shot_gain * (
        0.24
        + 0.62 * _smoothstep(0.02, 0.22, lane_gain)
        + 0.26 * _smoothstep(0.00, 0.08, progress_gain)
        + 0.42 * half_space_entry
    )
    wide_cut_in_window = (
        _smoothstep(0.50, 0.86, old_width_ratio)
        * _smoothstep(0.62, 0.84, old_progress)
        * _smoothstep(0.03, 0.14, future_shot_gain)
    )
    carry_to_shoot_window *= 1.0 + 0.55 * wide_cut_in_window + 0.75 * half_space_entry
    effective_gain = max(pv_gain, shot_quality_gain * 0.90, carry_to_shoot_window * 1.55)
    wide_second_line_carry_window = (
        _smoothstep(0.62, 0.80, old_progress)
        * _smoothstep(0.46, 0.82, old_width_ratio)
        * _smoothstep(0.18, 0.58, new_width_ratio)
        * _smoothstep(0.04, 0.13, future_shot_gain)
        * (1.0 - _smoothstep(1.0, 3.0, max(0, carrier.consecutive_carries)))
    )
    byline_carry_window = (
        _smoothstep(0.58, 0.80, old_progress)
        * _smoothstep(0.48, 0.86, old_width_ratio)
        * _smoothstep(0.72, 0.92, target_progress)
        * _smoothstep(0.50, 0.90, new_width_ratio)
        * _smoothstep(0.010, 0.085, progress_gain)
        * _smoothstep(0.42, 0.86, path_feasibility)
        * (1.0 - _smoothstep(0.88, 0.98, old_progress))
    )

    continuity = current_pv * (0.012 + 0.055 * _smoothstep(0.00, 0.12, pv_gain))
    continuity += shot_quality_gain * (0.55 + 0.70 * _smoothstep(0.02, 0.14, shot_quality_gain))
    continuity += carry_to_shoot_window * (
        0.95 + 0.60 * _smoothstep(0.03, 0.15, future_shot_gain)
    )
    continuity += wide_second_line_carry_window * (
        0.010 + 0.14 * future_shot_gain + 0.014 * _smoothstep(0.02, 0.12, lane_gain)
    )
    continuity += half_space_entry * (
        0.030
        + 0.095 * _smoothstep(0.025, 0.18, lane_gain)
        + 0.22 * future_shot_gain
        + 0.030 * _smoothstep(0.00, 0.08, progress_gain)
    )
    continuity += byline_carry_window * (
        0.045
        + 0.090 * _smoothstep(0.02, 0.12, progress_gain)
        + 0.040 * _smoothstep(0.45, 0.90, old_width_ratio)
    )
    score = action_delta_score(
        current_state_value, after_value, path_feasibility, risk_cost, continuity
    )

    near_goal_pressure = 1.0 - _smoothstep(16.0, 26.0, old_goal_dist)
    angle_worsening = max(0.0, new_angle_width - old_angle_width)
    distance_worsening = max(0.0, new_goal_dist - old_goal_dist)
    wide_penalty = 1.0 - near_goal_pressure * 0.45 * _smoothstep(0.0, 8.0, angle_worsening)
    too_close_penalty = 1.0 - near_goal_pressure * 0.55 * (1.0 - _smoothstep(3.0, 8.0, new_goal_dist))
    backwards_penalty = 1.0 - near_goal_pressure * 0.35 * _smoothstep(0.0, 6.0, distance_worsening)
    low_gain_penalty = 1.0 - near_goal_pressure * 0.35 * (1.0 - _smoothstep(0.02, 0.10, effective_gain))
    near_goal_multiplier = max(
        0.08,
        wide_penalty * too_close_penalty * backwards_penalty * low_gain_penalty,
    )
    score *= near_goal_multiplier

    # When the carrier has already opened a credible shooting lane, one more
    # touch should carry an opportunity cost unless it materially improves the
    # shot. This keeps cut-ins from becoming endless close-control loops while
    # still allowing a valuable final touch when the next window is much better.
    extra_touch_gain = max(shot_quality_gain, future_shot_gain)
    shot_window = (
        _smoothstep(0.07, 0.14, current_shot)
        * (1.0 - _smoothstep(18.0, 28.0, old_goal_dist))
        * (1.0 - _smoothstep(7.0, 18.0, old_angle_width))
    )
    extra_touch_improvement = _smoothstep(0.03, 0.09, extra_touch_gain)
    shooting_window_multiplier = 1.0 - 0.50 * shot_window * (1.0 - extra_touch_improvement)
    shooting_window_multiplier = max(0.45, shooting_window_multiplier)
    score *= shooting_window_multiplier

    stale_ticks = max(0, carrier.possession_ticks - 2)
    low_gain_pressure = 1.0 - _smoothstep(0.03, 0.12, effective_gain)
    possession_multiplier = 1.0 / (1.0 + stale_ticks * 0.20 * low_gain_pressure)
    low_gain_multiplier = 0.65 + 0.35 * _smoothstep(0.0, 0.06, effective_gain)
    final_third_carry = _smoothstep(0.72, 0.88, target_progress) * _smoothstep(0.35, 0.75, target_centrality)
    support_nearby = 0.0
    for tm in teammates:
        if tm.index == carrier.index or tm.is_goalkeeper:
            continue
        d = distance(tm.pos, carrier.pos)
        if 6.0 < d < 26.0:
            base = getattr(tm, "base_formation_pos", getattr(tm, "tactical_anchor", tm.pos))
            base_progress = base[0] / max(1.0, pitch.length) if attacking_right else (pitch.length - base[0]) / max(1.0, pitch.length)
            carrier_support_depth = 1.0 - _smoothstep(0.86, 0.98, base_progress)
            support_nearby = max(
                support_nearby,
                (1.0 - abs(d - 18.0) / 12.0) * (0.42 + 0.58 * carrier_support_depth),
            )
    support_release_cost = 1.0 + 0.55 * support_nearby
    repeated_carry_load = _smoothstep(2.0, 5.0, max(0, carrier.consecutive_carries))
    release_pressure = (
        final_third_carry
        * repeated_carry_load
        * support_release_cost
        * (0.62 + 0.38 * (1.0 - _smoothstep(0.12, 0.28, effective_gain)))
    )
    origin_width = abs(carrier.pos[1] - pitch.width / 2.0) / (pitch.width / 2.0)
    lateral_shift = abs(target[1] - carrier.pos[1]) / max(1.0, pitch.width / 2.0)
    pressure_draw = (
        _smoothstep(0.54, 0.86, old_progress)
        * _smoothstep(0.18, 0.72, max(origin_width, old_width_ratio))
        * _smoothstep(0.04, 0.30, lateral_shift)
        * (0.45 + 0.55 * _smoothstep(0.02, 0.14, max(lane_gain, future_shot_gain)))
    )
    space_manipulation = max(
        pressure_draw,
        half_space_entry * 0.85,
        wide_second_line_carry_window * 0.72,
        _smoothstep(0.04, 0.18, lane_gain) * _smoothstep(0.58, 0.86, old_progress),
    )
    final_third_stale_multiplier = 1.0 / (
        1.0 + max(0, carrier.consecutive_carries - 1) * 0.56 * release_pressure
    )
    score *= possession_multiplier * low_gain_multiplier * final_third_stale_multiplier

    return ValueResult(
        score=score,
        success_prob=path_feasibility,
        risk_cost=risk_cost,
        current_value=current_state_value,
        after_value=after_value,
        components={
            "current_value": current_state_value,
            "after_value": after_value,
            "delta": after_value - current_state_value,
            "success_prob": path_feasibility,
            "risk_cost": risk_cost,
            "opportunity_cost": 0.0,
            "continuity": continuity,
            "final_score": score,
            "path_feasibility": path_feasibility,
            "pv_gain": pv_gain,
            "target_pv": target_pv,
            "current_pv": current_pv,
            "current_shot": current_shot,
            "target_shot": target_shot,
            "shot_quality_gain": shot_quality_gain,
            "future_shot": future_shot,
            "future_shot_gain": future_shot_gain,
            "carry_to_shoot_window": carry_to_shoot_window,
            "wide_cut_in_window": wide_cut_in_window,
            "wide_second_line_carry_window": wide_second_line_carry_window,
            "byline_carry_window": byline_carry_window,
            "half_space_entry": half_space_entry,
            "lane_gain": lane_gain,
            "progress_gain": progress_gain,
            "effective_gain": effective_gain,
            "near_goal_multiplier": near_goal_multiplier,
            "extra_touch_gain": extra_touch_gain,
            "shot_window": shot_window,
            "shooting_window_multiplier": shooting_window_multiplier,
            "possession_ticks_multiplier": possession_multiplier,
            "final_third_stale_multiplier": final_third_stale_multiplier,
            "repeated_carry_load": repeated_carry_load,
            "release_pressure": release_pressure,
            "support_nearby": support_nearby,
            "support_release_cost": support_release_cost,
            "pressure_draw": pressure_draw,
            "space_manipulation": space_manipulation,
        },
    )


def evaluate_shot(
    shooter: "Player",
    goal_pos: Tuple[float, float],
    config: "EngineConfig",
    opponents: List["Player"],
    dist_to_goal: float,
    angle_factor: float,
    pressure_factor: float,
    lane_factor: float,
    dist_factor: float,
    current_state_value: float = 0.0,
    teammates: Optional[List["Player"]] = None,
    pitch: Optional["Pitch"] = None,
    attacking_right: Optional[bool] = None,
) -> ValueResult:
    """Evaluate a shot using the existing xG-based shot formula."""
    finishing = shooter.abilities.get("Finishing", 50) / 100.0
    long_shot = shooter.abilities.get("Long_Shot", 50) / 100.0
    if dist_to_goal > 25.0:
        ability = long_shot
    elif dist_to_goal > 18.0:
        ability = (finishing + long_shot) / 2.0
    else:
        ability = finishing

    on_target_prob = (
        config.shot_on_target_base
        * (0.4 + 0.6 * ability)
        * dist_factor
        * angle_factor
        * pressure_factor
        * lane_factor
    )
    attacking_right = goal_pos[0] > shooter.pos[0] if attacking_right is None else attacking_right
    outside_box = _is_outside_penalty_area(shooter.pos, config, attacking_right)
    if outside_box:
        outside_penalty = 0.76 + 0.24 * _smoothstep(21.0, 32.0, dist_to_goal)
        on_target_prob *= outside_penalty
    min_on_target = 0.13 if dist_to_goal < 25.0 else 0.055
    on_target_prob = max(min_on_target, min(0.78, on_target_prob))

    base_save = config.gk_save_base
    distance_save_relief = min(0.12, max(0.0, (dist_to_goal - 16.0) * 0.0035))
    angle_save_bonus = (1.0 - angle_factor) * 0.12
    pressure_save_bonus = (1.0 - pressure_factor * lane_factor) * 0.10
    central_bonus = 0.0
    if not outside_box and dist_to_goal < 18.0 and abs(shooter.pos[1] - config.pitch_width / 2.0) < 12.0:
        central_bonus = 0.12
    save_estimate = max(
        0.35,
        min(0.90, base_save + angle_save_bonus + pressure_save_bonus - distance_save_relief - central_bonus),
    )

    xg = shot_quality_at(shooter.pos, shooter, opponents, config, attacking_right)
    score = xg * config.goal_reward_constant
    low_quality_multiplier = 0.30 + 0.70 * _smoothstep(0.035, 0.13, xg)
    first_time_window = (
        (1.0 - _smoothstep(2.0, 5.0, max(0, shooter.possession_ticks)))
        * (1.0 - _smoothstep(1.0, 3.0, max(0, shooter.consecutive_carries)))
    )
    receive_origin = getattr(shooter, "last_receive_origin", shooter.pos)
    receive_origin_progress = receive_origin[0] / max(1.0, config.pitch_length) if attacking_right else (config.pitch_length - receive_origin[0]) / max(1.0, config.pitch_length)
    shooter_progress = shooter.pos[0] / max(1.0, config.pitch_length) if attacking_right else (config.pitch_length - shooter.pos[0]) / max(1.0, config.pitch_length)
    receive_drop = max(0.0, receive_origin_progress - shooter_progress)
    shooter_centrality = 1.0 - min(1.0, abs(shooter.pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
    layoff_second_line_window = (
        first_time_window
        * _smoothstep(0.035, 0.095, xg)
        * _smoothstep(0.035, 0.14, receive_drop)
        * _smoothstep(0.55, 0.90, shooter_centrality)
        * _smoothstep(0.70, 0.98, pressure_factor * lane_factor)
        * (1.0 - _smoothstep(30.0, 42.0, dist_to_goal))
    )
    open_medium_window = (
        first_time_window
        * _smoothstep(0.030, 0.095, xg)
        * _smoothstep(0.56, 0.86, angle_factor)
        * _smoothstep(0.70, 0.98, pressure_factor * lane_factor)
        * (1.0 - _smoothstep(30.0, 42.0, dist_to_goal))
    )
    low_quality_multiplier = max(
        low_quality_multiplier,
        0.38 + 0.34 * max(open_medium_window, layoff_second_line_window),
    )
    score *= low_quality_multiplier
    second_line_window = (
        _smoothstep(0.038, 0.090, xg)
        * (1.0 - _smoothstep(24.0, 36.0, dist_to_goal))
        * _smoothstep(0.58, 0.88, angle_factor)
        * _smoothstep(0.78, 0.98, pressure_factor * lane_factor)
    )
    clean_second_line_shot = (
        first_time_window
        * second_line_window
        * _smoothstep(0.55, 0.88, angle_factor)
        * _smoothstep(0.72, 0.98, pressure_factor * lane_factor)
    )
    second_line_bonus = 1.0 + 0.72 * first_time_window * second_line_window
    score *= second_line_bonus
    close_bonus = (
        (1.0 - _smoothstep(14.0, 22.0, dist_to_goal))
        * _smoothstep(0.55, 0.85, angle_factor)
        * _smoothstep(0.08, 0.16, xg)
    )
    medium_bonus = (
        (1.0 - _smoothstep(20.0, 30.0, dist_to_goal))
        * _smoothstep(0.45, 0.75, angle_factor)
        * _smoothstep(0.06, 0.13, xg)
    )
    shot_quality_bonus = 1.0 + 0.60 * close_bonus + 0.42 * medium_bonus
    shot_quality_bonus += 0.30 * open_medium_window
    shot_quality_bonus += 0.26 * layoff_second_line_window
    score *= shot_quality_bonus
    shot_readiness = max(
        _smoothstep(0.045, 0.16, xg),
        open_medium_window * 0.48,
        layoff_second_line_window * 0.58,
    )
    distance_cost = _smoothstep(24.0, 44.0, dist_to_goal)
    possession_value_cost = max(0.0, current_state_value - xg) * (1.0 - shot_readiness) * 0.18
    possession_value_cost *= (1.0 - 0.55 * clean_second_line_shot - 0.34 * open_medium_window - 0.40 * layoff_second_line_window)
    attracted_pressure = 0.0
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        d = distance(shooter.pos, opp.pos)
        if d < 11.0:
            attracted_pressure += 1.0 - d / 11.0
    attracted_pressure = min(1.0, attracted_pressure * 0.42)
    support_nearby = 0.0
    developing_support = 0.0
    second_line_support = 0.0
    layoff_support = 0.0
    if teammates and pitch is not None:
        shooter_progress = (
            shooter.pos[0] / max(1.0, pitch.length)
            if attacking_right
            else (pitch.length - shooter.pos[0]) / max(1.0, pitch.length)
        )
        shooter_width = abs(shooter.pos[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0)
        forward_dir = 1.0 if attacking_right else -1.0
        for tm in teammates:
            if tm.index == shooter.index or tm.is_goalkeeper:
                continue
            tm_progress = (
                tm.pos[0] / max(1.0, pitch.length)
                if attacking_right
                else (pitch.length - tm.pos[0]) / max(1.0, pitch.length)
            )
            target = getattr(tm, "target_pos", tm.pos)
            target_progress = (
                target[0] / max(1.0, pitch.length)
                if attacking_right
                else (pitch.length - target[0]) / max(1.0, pitch.length)
            )
            tm_centrality = 1.0 - min(1.0, abs(tm.pos[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0))
            target_centrality = 1.0 - min(1.0, abs(target[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0))
            target_width = abs(target[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0)
            d = distance(shooter.pos, tm.pos)
            target_d = distance(shooter.pos, target)
            support_nearby = max(
                support_nearby,
                _smoothstep(6.0, 13.0, d) * (1.0 - _smoothstep(24.0, 34.0, d)),
            )
            move_progress = (target[0] - tm.pos[0]) * forward_dir
            moving_into_window = (
                _smoothstep(0.0, 5.0, max(0.0, move_progress))
                * _smoothstep(0.58, 0.76, target_progress)
                * (1.0 - _smoothstep(0.86, 0.95, target_progress))
                * _smoothstep(0.38, 0.82, target_centrality)
                * (1.0 - _smoothstep(18.0, 32.0, target_d))
            )
            developing_support = max(developing_support, moving_into_window)
            depth_gap = (shooter.pos[0] - target[0]) * forward_dir
            second_line_candidate = (
                _smoothstep(0.66, 0.84, shooter_progress)
                * _smoothstep(0.60, 0.82, target_progress)
                * (1.0 - _smoothstep(0.84, 0.95, target_progress))
                * _smoothstep(4.0, 13.0, depth_gap)
                * (1.0 - _smoothstep(24.0, 36.0, depth_gap))
                * _smoothstep(0.42, 0.88, target_centrality)
                * (1.0 - _smoothstep(20.0, 34.0, target_d))
            )
            second_line_support = max(second_line_support, second_line_candidate)
            lateral_gap = abs(target[1] - shooter.pos[1])
            layoff_candidate = (
                _smoothstep(0.70, 0.90, shooter_progress)
                * _smoothstep(5.0, 14.0, target_d)
                * (1.0 - _smoothstep(24.0, 36.0, target_d))
                * _smoothstep(0.15, 0.58, max(shooter_width, target_width))
                * _smoothstep(0.18, 0.64, lateral_gap / max(1.0, pitch.width / 2.0))
                * _smoothstep(0.35, 0.82, target_centrality)
            )
            layoff_support = max(layoff_support, layoff_candidate)
    repeated_carry_pressure = (
        _smoothstep(1.0, 3.0, max(0, shooter.consecutive_carries))
        * _smoothstep(0.18, 0.65, attracted_pressure)
        * (1.0 - _smoothstep(0.16, 0.28, xg))
    )
    stale_shot_pressure = (
        _smoothstep(2.0, 5.0, max(0, shooter.consecutive_carries))
        * (0.45 + 0.55 * _smoothstep(0.08, 0.55, attracted_pressure))
        * (1.0 - _smoothstep(0.20, 0.34, xg))
    )
    support_release_window = max(
        support_nearby * developing_support,
        second_line_support,
        layoff_support,
    ) * (1.0 - shot_readiness * 0.72) * (1.0 - _smoothstep(0.13, 0.26, xg))
    opportunity_cost = (
        (1.0 - shot_readiness) * 0.18
        + distance_cost * 0.11
        + possession_value_cost
        + repeated_carry_pressure * 0.12
        + stale_shot_pressure * 0.16
        + support_release_window * 0.15
    )
    possession_loss_multiplier = max(0.35, 1.0 - opportunity_cost)
    score *= possession_loss_multiplier

    return ValueResult(
        score=score,
        success_prob=on_target_prob,
        risk_cost=1.0 - possession_loss_multiplier,
        current_value=current_state_value,
        after_value=xg,
        components={
            "current_value": current_state_value,
            "after_value": xg,
            "delta": xg - current_state_value,
            "success_prob": on_target_prob,
            "risk_cost": 1.0 - possession_loss_multiplier,
            "opportunity_cost": opportunity_cost,
            "continuity": 0.0,
            "final_score": score,
            "xg": xg,
            "on_target_prob": on_target_prob,
            "save_estimate": save_estimate,
            "distance": dist_to_goal,
            "angle_factor": angle_factor,
            "pressure_factor": pressure_factor,
            "lane_factor": lane_factor,
            "dist_factor": dist_factor,
            "low_quality_multiplier": low_quality_multiplier,
            "first_time_window": first_time_window,
            "layoff_second_line_window": layoff_second_line_window,
            "receive_drop": receive_drop,
            "second_line_window": second_line_window,
            "clean_second_line_shot": clean_second_line_shot,
            "open_medium_window": open_medium_window,
            "second_line_bonus": second_line_bonus,
            "shot_quality_bonus": shot_quality_bonus,
            "shot_readiness": shot_readiness,
            "distance_cost": distance_cost,
            "attracted_pressure": attracted_pressure,
            "support_nearby": support_nearby,
            "developing_support": developing_support,
            "second_line_support": second_line_support,
            "layoff_support": layoff_support,
            "support_release_window": support_release_window,
            "repeated_carry_pressure": repeated_carry_pressure,
            "stale_shot_pressure": stale_shot_pressure,
            "possession_loss_multiplier": possession_loss_multiplier,
            "possession_value_cost": possession_value_cost,
            "outside_box": outside_box,
        },
    )


def evaluate_hold(
    holder: "Player",
    current_pv: float,
    pressure: int,
    nearest_pressure: float,
    developing_runs: float,
    best_pass_score: float,
    shoot_score: float,
    opportunity_wait_value: float = 0.0,
) -> ValueResult:
    """Evaluate controlled possession while better options develop."""
    iq = holder.iq_value / 100.0
    pressure_factor = 1.0 / (1.0 + pressure * 0.55)
    pressure_factor *= max(0.18, 1.0 - nearest_pressure * 0.82)
    poor_options_bonus = max(0.0, 0.055 - best_pass_score) * 0.24
    low_pressure_wait = 1.0 - _smoothstep(0.10, 0.45, nearest_pressure)
    useful_development = min(1.0, developing_runs / 2.0) * low_pressure_wait
    shot_quality_window = _smoothstep(0.08, 0.18, shoot_score)
    no_clear_release = (
        (1.0 - _smoothstep(0.055, 0.125, shoot_score))
        * (1.0 - _smoothstep(0.070, 0.170, best_pass_score))
        * low_pressure_wait
    )
    opportunity_wait = max(0.0, min(1.0, opportunity_wait_value)) * (1.0 - 0.70 * shot_quality_window)
    settle_value = (
        0.010
        + current_pv * 0.025
        + useful_development * 0.018
        + opportunity_wait * 0.026
        + no_clear_release * 0.024
        + poor_options_bonus
    )

    role_multiplier = 1.0 + 0.06 * float(holder.is_midfielder) + 0.03 * float(holder.is_defender)
    settle_value *= role_multiplier

    score = settle_value * (0.65 + 0.45 * iq) * pressure_factor
    shot_interrupt = shot_quality_window
    score *= 1.0 - 0.55 * shot_interrupt
    opportunity_cost = max(0.0, best_pass_score - 0.075) * 0.38 * (1.0 - 0.55 * no_clear_release)
    hold_multiplier = 1.0 / (
        1.0
        + max(0, holder.hold_ticks) * 0.62
        + max(0, holder.possession_ticks - 2) * 0.38
    )
    score *= hold_multiplier
    score = max(0.0, score - opportunity_cost)

    return ValueResult(
        score=max(0.0, score),
        success_prob=1.0,
        risk_cost=0.0,
        current_value=current_pv,
        after_value=current_pv,
        components={
            "current_value": current_pv,
            "after_value": current_pv,
            "delta": 0.0,
            "success_prob": 1.0,
            "risk_cost": 0.0,
            "opportunity_cost": opportunity_cost,
            "continuity": useful_development * 0.026,
            "final_score": max(0.0, score),
            "pressure_factor": pressure_factor,
            "nearest_pressure": nearest_pressure,
            "developing_runs": developing_runs,
            "useful_development": useful_development,
            "no_clear_release": no_clear_release,
            "opportunity_wait_value": opportunity_wait_value,
            "opportunity_wait": opportunity_wait,
            "poor_options_bonus": poor_options_bonus,
            "hold_multiplier": hold_multiplier,
            "role_multiplier": role_multiplier,
            "shot_interrupt": shot_interrupt,
        },
    )


def evaluate_clear(x_progress: float, pressure: int, config: "EngineConfig") -> ValueResult:
    """Evaluate clearance using the existing clearance formula."""
    danger = max(0.0, 1.0 - x_progress / 0.45)
    pressure_factor = 1.0 - math.exp(-pressure / 2.0)
    score = max(0.0, danger * pressure_factor * config.clear_reward_base)
    return ValueResult(
        score=score,
        success_prob=1.0,
        risk_cost=0.0,
        current_value=0.0,
        after_value=0.0,
        components={
            "current_value": 0.0,
            "after_value": 0.0,
            "delta": 0.0,
            "success_prob": 1.0,
            "risk_cost": 0.0,
            "opportunity_cost": 0.0,
            "continuity": 0.0,
            "final_score": score,
            "danger": danger,
            "pressure_factor": pressure_factor,
        },
    )
