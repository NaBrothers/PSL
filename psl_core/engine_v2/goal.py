"""Short-term goal continuity primitives for engine v2.

This module is intentionally pure for now. Match integration can use these
helpers later without changing the value model contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = _clamp01((value - edge0) / max(1e-6, edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def goal_context(
    *,
    phase: str,
    completion: str,
    abort: str,
    handoff: str,
    **kwargs,
) -> Dict[str, Any]:
    """Build a goal context with shared lifecycle fields."""
    payload = {
        "phase": phase,
        "completion": completion,
        "abort": abort,
        "handoff": handoff,
    }
    payload.update(kwargs)
    return payload


@dataclass(frozen=True)
class PlayerGoal:
    """A traceable short-term player intent."""

    goal_type: str
    target_pos: Tuple[float, float]
    value: float
    confidence: float = 1.0
    created_tick: int = 0
    last_updated_tick: int = 0
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "goal_type": self.goal_type,
            "target_pos": [self.target_pos[0], self.target_pos[1]],
            "value": self.value,
            "confidence": self.confidence,
            "created_tick": self.created_tick,
            "last_updated_tick": self.last_updated_tick,
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class GoalSwitchContext:
    """Continuous switch-cost inputs."""

    base: float = 0.035
    context_stability: float = 1.0
    role_discipline: float = 1.0
    pressure_interrupt: float = 0.0
    iq: float = 75.0


@dataclass(frozen=True)
class GoalSelection:
    """Result of comparing the current goal to the best candidate."""

    goal: PlayerGoal
    switched: bool
    switch_cost: float
    value_advantage: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "goal": self.goal.to_dict(),
            "switched": self.switched,
            "switch_cost": self.switch_cost,
            "value_advantage": self.value_advantage,
            "reason": self.reason,
        }


def goal_switch_cost(context: GoalSwitchContext) -> float:
    """Compute continuous switch cost. Pressure can lower the cost to interrupt."""
    iq = max(1.0, min(99.0, context.iq))
    iq_adjustment = 0.78 + (100.0 - iq) / 100.0 * 0.38
    pressure_factor = max(0.15, 1.0 - max(0.0, min(1.0, context.pressure_interrupt)))
    return max(
        0.0,
        context.base
        * max(0.0, context.context_stability)
        * max(0.0, context.role_discipline)
        * pressure_factor
        * iq_adjustment,
    )


def select_goal(
    current_goal: Optional[PlayerGoal],
    candidate_goal: PlayerGoal,
    context: GoalSwitchContext,
) -> GoalSelection:
    """Keep or switch goals based on value advantage over switch cost."""
    if current_goal is None:
        return GoalSelection(
            goal=candidate_goal,
            switched=True,
            switch_cost=0.0,
            value_advantage=candidate_goal.value,
            reason="no_current_goal",
        )

    current_phase = current_goal.context.get("phase") if isinstance(current_goal.context, dict) else None
    candidate_phase = candidate_goal.context.get("phase") if isinstance(candidate_goal.context, dict) else None
    if (
        current_goal.goal_type == candidate_goal.goal_type
        and candidate_phase in ("finish", "release")
        and candidate_phase != current_phase
    ):
        return GoalSelection(
            goal=candidate_goal,
            switched=False,
            switch_cost=0.0,
            value_advantage=candidate_goal.value - current_goal.value,
            reason="current_goal_phase_updated",
        )

    switch_cost = goal_switch_cost(context)
    advantage = candidate_goal.value - current_goal.value
    if advantage > switch_cost:
        return GoalSelection(
            goal=candidate_goal,
            switched=True,
            switch_cost=switch_cost,
            value_advantage=advantage,
            reason="candidate_clears_switch_cost",
        )
    return GoalSelection(
        goal=current_goal,
        switched=False,
        switch_cost=switch_cost,
        value_advantage=advantage,
        reason="current_goal_within_switch_cost",
    )


def evaluate_cut_inside_to_shoot_goal(
    *,
    player_pos: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    best_carry_components: Dict[str, Any],
    best_shot_components: Dict[str, Any],
    consecutive_carries: int = 0,
    goal_age_ticks: int = 0,
    created_tick: Optional[int] = None,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a cut-inside goal when geometry indicates a multi-tick shot plan."""
    x, y = player_pos
    progress = x / max(1.0, pitch_length) if attacking_right else (pitch_length - x) / max(1.0, pitch_length)
    width = abs(y - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    future_shot_gain = float(best_carry_components.get("future_shot_gain", 0.0) or 0.0)
    carry_to_shoot = float(best_carry_components.get("carry_to_shoot_window", 0.0) or 0.0)
    wide_second_line = float(best_carry_components.get("wide_second_line_carry_window", 0.0) or 0.0)
    current_shot = float(best_shot_components.get("xg", 0.0) or 0.0)
    current_readiness = float(best_shot_components.get("shot_readiness", 0.0) or 0.0)

    carry_plan = (
        _smoothstep(0.62, 0.82, progress)
        * _smoothstep(0.36, 0.82, width)
        * _smoothstep(0.035, 0.12, future_shot_gain)
        * (0.35 + 0.65 * _smoothstep(0.02, 0.14, carry_to_shoot + wide_second_line))
    )
    already_shootable = _smoothstep(0.08, 0.16, current_shot) * _smoothstep(0.20, 0.70, current_readiness)
    finish_window = _smoothstep(0.09, 0.18, current_shot) * (
        0.45 + 0.55 * _smoothstep(0.12, 0.70, current_readiness)
    )
    stalled_drive = (
        (consecutive_carries >= 3 or goal_age_ticks >= 6)
        and width > 0.58
        and current_shot < 0.045
        and finish_window < 0.12
    )
    release_window = (
        max(
            _smoothstep(2.0, 4.0, max(0, consecutive_carries)),
            _smoothstep(4.0, 8.0, max(0, goal_age_ticks)),
        )
        * _smoothstep(0.58, 0.82, width)
        * (1.0 - _smoothstep(0.035, 0.070, current_shot))
    )
    value = max(
        0.0,
        carry_plan * (1.0 - 0.72 * already_shootable),
        finish_window * 0.55,
        release_window * 0.20,
    )
    if value <= 0.0:
        return None
    phase = "finish" if finish_window > 0.35 else "release" if stalled_drive else "drive"

    goal_x = pitch_length if attacking_right else 0.0
    target_x = x + (1.0 if attacking_right else -1.0) * 6.0
    target_y = y + (pitch_width / 2.0 - y) * 0.55
    # Keep the target in front of the carrier and away from the goal line.
    if attacking_right:
        target_x = min(goal_x - 14.0, max(x + 1.0, target_x))
    else:
        target_x = max(goal_x + 14.0, min(x - 1.0, target_x))

    return PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(target_x, target_y),
        value=value,
        confidence=max(carry_to_shoot, wide_second_line, future_shot_gain),
        created_tick=tick if created_tick is None else created_tick,
        last_updated_tick=tick,
        context=goal_context(
            phase=phase,
            completion="finish_window",
            abort="stalled_wide_drive",
            handoff="default_value_model",
            progress=progress,
            width=width,
            future_shot_gain=future_shot_gain,
            carry_to_shoot_window=carry_to_shoot,
            wide_second_line_carry_window=wide_second_line,
            current_shot=current_shot,
            current_readiness=current_readiness,
            finish_window=finish_window,
            consecutive_carries=consecutive_carries,
            goal_age_ticks=goal_age_ticks,
        ),
    )


def evaluate_arc_arrival_for_cutback_goal(
    *,
    player_pos: Tuple[float, float],
    anchor_pos: Tuple[float, float],
    ball_pos: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    tick: int,
    base_pos: Optional[Tuple[float, float]] = None,
) -> Optional[PlayerGoal]:
    """Build an off-ball arc-arrival goal for wide final-third attacks."""
    ball_progress = (
        ball_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - ball_pos[0]) / max(1.0, pitch_length)
    )
    ball_width = abs(ball_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    anchor_progress = (
        anchor_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - anchor_pos[0]) / max(1.0, pitch_length)
    )
    base = anchor_pos if base_pos is None else base_pos
    base_progress = (
        base[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - base[0]) / max(1.0, pitch_length)
    )
    anchor_width = abs(anchor_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    player_to_anchor = ((player_pos[0] - anchor_pos[0]) ** 2 + (player_pos[1] - anchor_pos[1]) ** 2) ** 0.5

    arc_x = pitch_length * (0.80 if attacking_right else 0.20)
    arc_y = pitch_width / 2.0
    target_x = anchor_pos[0] * 0.45 + arc_x * 0.55
    target_y = anchor_pos[1] * 0.45 + arc_y * 0.55
    target_pos = (target_x, target_y)

    target_dist = ((player_pos[0] - target_x) ** 2 + (player_pos[1] - target_y) ** 2) ** 0.5
    value = (
        _smoothstep(0.70, 0.86, ball_progress)
        * _smoothstep(0.28, 0.64, ball_width)
        * _smoothstep(0.56, 0.78, anchor_progress)
        * (1.0 - 0.92 * _smoothstep(0.70, 0.84, anchor_progress))
        * _smoothstep(0.34, 0.56, base_progress)
        * (1.0 - _smoothstep(0.62, 0.76, base_progress))
        * (1.0 - _smoothstep(0.34, 0.68, anchor_width))
        * (1.0 - _smoothstep(28.0, 46.0, target_dist))
        * (0.65 + 0.35 * (1.0 - _smoothstep(0.0, 28.0, player_to_anchor)))
    )
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=target_pos,
        value=value,
        confidence=value,
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="arrive",
            completion="reach_arc_target",
            abort="wide_window_closed",
            handoff="off_ball_value_model",
            ball_progress=ball_progress,
            ball_width=ball_width,
            anchor_progress=anchor_progress,
            base_progress=base_progress,
            anchor_width=anchor_width,
            target_dist=target_dist,
        ),
    )


def evaluate_wide_hold_for_overlap_goal(
    *,
    player_pos: Tuple[float, float],
    overlap_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    overlap_value: float,
    immediate_best_score: float,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a wide-hold goal when a nearby overlap is developing."""
    progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    width = abs(player_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    target_progress = (
        overlap_target[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - overlap_target[0]) / max(1.0, pitch_length)
    )
    target_width = abs(overlap_target[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    forward_gap = (overlap_target[0] - player_pos[0]) * (1.0 if attacking_right else -1.0)
    lateral_gap = abs(overlap_target[1] - player_pos[1])
    same_lane = 1.0 - min(1.0, lateral_gap / max(1.0, pitch_width * 0.28))

    window = (
        _smoothstep(0.62, 0.84, progress)
        * _smoothstep(0.42, 0.82, width)
        * _smoothstep(0.00, 0.12, target_progress - progress)
        * (1.0 - _smoothstep(0.24, 0.52, forward_gap / max(1.0, pitch_length)))
        * _smoothstep(0.42, 0.86, target_width)
        * (0.35 + 0.65 * same_lane)
        * _smoothstep(0.04, 0.20, overlap_value)
    )
    # A clearly superior immediate action should interrupt the waiting goal.
    interrupt = _smoothstep(0.12, 0.30, immediate_best_score)
    value = max(0.0, window * (1.0 - interrupt))
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="wide_hold_for_overlap",
        target_pos=player_pos,
        value=value,
        confidence=max(value, overlap_value),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="wait",
            completion="overlap_pass_or_space_opens",
            abort="immediate_action_clears_window",
            handoff="default_value_model",
            progress=progress,
            width=width,
            overlap_value=overlap_value,
            immediate_best_score=immediate_best_score,
            target_progress=target_progress,
            target_width=target_width,
            forward_gap=forward_gap,
            same_lane=same_lane,
        ),
    )


def evaluate_release_pressure_with_layoff_goal(
    *,
    player_pos: Tuple[float, float],
    layoff_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    attracted_pressure: float,
    layoff_value: float,
    immediate_best_score: float,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a layoff goal when the carrier has attracted pressure high upfield."""
    progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    target_progress = (
        layoff_target[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - layoff_target[0]) / max(1.0, pitch_length)
    )
    target_centrality = 1.0 - min(1.0, abs(layoff_target[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0))
    pass_distance = ((player_pos[0] - layoff_target[0]) ** 2 + (player_pos[1] - layoff_target[1]) ** 2) ** 0.5
    backward_depth = (player_pos[0] - layoff_target[0]) * (1.0 if attacking_right else -1.0)

    window = (
        _smoothstep(0.66, 0.88, progress)
        * _smoothstep(0.18, 0.70, attracted_pressure)
        * _smoothstep(4.0, 14.0, pass_distance)
        * (1.0 - _smoothstep(24.0, 36.0, pass_distance))
        * _smoothstep(-3.0, 9.0, backward_depth)
        * (1.0 - _smoothstep(0.24, 0.48, abs(progress - target_progress)))
        * _smoothstep(0.32, 0.82, target_centrality)
        * _smoothstep(0.035, 0.16, layoff_value)
    )
    interrupt = _smoothstep(0.16, 0.34, immediate_best_score)
    value = max(0.0, window * (1.0 - interrupt))
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="release_pressure_with_layoff",
        target_pos=layoff_target,
        value=value,
        confidence=max(value, layoff_value, attracted_pressure),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="release",
            completion="layoff_pass",
            abort="pressure_released_or_better_action",
            handoff="default_value_model",
            progress=progress,
            target_progress=target_progress,
            target_centrality=target_centrality,
            attracted_pressure=attracted_pressure,
            layoff_value=layoff_value,
            immediate_best_score=immediate_best_score,
            pass_distance=pass_distance,
            backward_depth=backward_depth,
        ),
    )


def evaluate_hold_for_opportunity_goal(
    *,
    player_pos: Tuple[float, float],
    support_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    support_value: float,
    hold_value: float,
    shot_components: Dict[str, Any],
    immediate_best_score: float,
    goal_age_ticks: int = 0,
    created_tick: Optional[int] = None,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a short control goal while better attacking options develop."""
    progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    target_progress = (
        support_target[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - support_target[0]) / max(1.0, pitch_length)
    )
    target_centrality = 1.0 - min(
        1.0,
        abs(support_target[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0),
    )
    pass_distance = (
        (player_pos[0] - support_target[0]) ** 2
        + (player_pos[1] - support_target[1]) ** 2
    ) ** 0.5
    lateral_gap = abs(player_pos[1] - support_target[1]) / max(1.0, pitch_width / 2.0)
    opportunity_window = max(0.0, support_value, hold_value)
    current_shot = float(shot_components.get("xg", 0.0) or 0.0)
    shot_readiness = max(
        float(shot_components.get("shot_readiness", 0.0) or 0.0),
        float(shot_components.get("open_medium_window", 0.0) or 0.0),
        float(shot_components.get("clean_second_line_shot", 0.0) or 0.0),
    )
    no_clear_shot = (1.0 - _smoothstep(0.075, 0.145, current_shot)) * (
        1.0 - _smoothstep(0.14, 0.52, shot_readiness)
    )

    support_window = (
        _smoothstep(0.42, 0.88, progress)
        * _smoothstep(5.0, 14.0, pass_distance)
        * (1.0 - _smoothstep(26.0, 38.0, pass_distance))
        * _smoothstep(0.42, 0.84, target_progress)
        * (1.0 - _smoothstep(0.86, 0.96, target_progress))
        * _smoothstep(0.28, 0.86, target_centrality)
        * _smoothstep(0.06, 0.44, lateral_gap)
        * _smoothstep(0.030, 0.120, opportunity_window)
        * no_clear_shot
    )
    retain_window = (
        _smoothstep(0.42, 0.88, progress)
        * (1.0 - _smoothstep(0.0, 3.0, pass_distance))
        * _smoothstep(0.08, 0.55, hold_value)
        * no_clear_shot
    )
    window = max(support_window, retain_window)
    interrupt = _smoothstep(0.14, 0.32, immediate_best_score)
    stale = _smoothstep(5.0, 9.0, max(0, goal_age_ticks))
    value = max(0.0, window * (1.0 - interrupt) * (1.0 - 0.55 * stale))
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="hold_for_opportunity",
        target_pos=support_target,
        value=value,
        confidence=max(value, opportunity_window),
        created_tick=tick if created_tick is None else created_tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="scan",
            completion="better_option_opens",
            abort="opportunity_window_closed_or_shot_opens",
            handoff="default_value_model",
            progress=progress,
            target_progress=target_progress,
            target_centrality=target_centrality,
            pass_distance=pass_distance,
            lateral_gap=lateral_gap,
            support_value=support_value,
            hold_value=hold_value,
            opportunity_window=opportunity_window,
            current_shot=current_shot,
            shot_readiness=shot_readiness,
            immediate_best_score=immediate_best_score,
            goal_age_ticks=goal_age_ticks,
        ),
    )


def evaluate_attack_far_post_goal(
    *,
    player_pos: Tuple[float, float],
    anchor_pos: Tuple[float, float],
    ball_pos: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a far-post arrival goal during deep wide attacks."""
    ball_progress = (
        ball_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - ball_pos[0]) / max(1.0, pitch_length)
    )
    ball_side = (ball_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    ball_width = abs(ball_side)
    player_progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    anchor_progress = (
        anchor_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - anchor_pos[0]) / max(1.0, pitch_length)
    )
    player_side = (player_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    weak_side = _clamp01(-player_side * ball_side)

    goal_x = pitch_length if attacking_right else 0.0
    far_post_x = goal_x - (1.0 if attacking_right else -1.0) * 8.5
    far_post_y = pitch_width / 2.0 - (1.0 if ball_side >= 0.0 else -1.0) * pitch_width * 0.11
    target_pos = (far_post_x, far_post_y)
    target_dist = ((player_pos[0] - far_post_x) ** 2 + (player_pos[1] - far_post_y) ** 2) ** 0.5

    value = (
        _smoothstep(0.72, 0.90, ball_progress)
        * _smoothstep(0.34, 0.72, ball_width)
        * _smoothstep(0.52, 0.82, max(player_progress, anchor_progress))
        * (0.45 + 0.85 * weak_side)
        * (1.0 - _smoothstep(18.0, 46.0, target_dist))
    )
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="attack_far_post",
        target_pos=target_pos,
        value=value,
        confidence=value,
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="arrive",
            completion="reach_far_post",
            abort="wide_delivery_window_closed",
            handoff="off_ball_value_model",
            ball_progress=ball_progress,
            ball_width=ball_width,
            weak_side=weak_side,
            player_progress=player_progress,
            anchor_progress=anchor_progress,
            target_dist=target_dist,
        ),
    )
