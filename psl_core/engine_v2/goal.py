"""Short-term goal continuity primitives for engine v2.

This module is intentionally pure for now. Match integration can use these
helpers later without changing the value model contract.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

from .decision import iq_decision_noise


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
    goal_noise_scale: float = 0.0
    rng: Any = None


@dataclass(frozen=True)
class GoalSelection:
    """Result of comparing the current goal to the best candidate."""

    goal: PlayerGoal
    switched: bool
    switch_cost: float
    value_advantage: float
    reason: str
    switch_noise: float = 0.0
    noisy_value_advantage: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "goal": self.goal.to_dict(),
            "switched": self.switched,
            "switch_cost": self.switch_cost,
            "value_advantage": self.value_advantage,
            "switch_noise": self.switch_noise,
            "noisy_value_advantage": (
                self.value_advantage
                if self.noisy_value_advantage is None
                else self.noisy_value_advantage
            ),
            "reason": self.reason,
        }


def goal_switch_cost(context: GoalSwitchContext) -> float:
    """Compute continuous switch cost. Pressure can lower the cost to interrupt."""
    iq_adjustment = 0.78 + iq_decision_noise(context.iq) * 0.38
    pressure_factor = max(0.15, 1.0 - max(0.0, min(1.0, context.pressure_interrupt)))
    return max(
        0.0,
        context.base
        * max(0.0, context.context_stability)
        * max(0.0, context.role_discipline)
        * pressure_factor
        * iq_adjustment,
    )


@dataclass(frozen=True)
class GoalCandidateChoice:
    """Best candidate after tiny goal-level judgement noise."""

    goal: PlayerGoal
    candidate_noise: float
    noisy_value: float

    def to_dict(self) -> dict:
        return {
            "candidate_noise": self.candidate_noise,
            "noisy_value": self.noisy_value,
        }


def _goal_selection_noise(context: GoalSwitchContext) -> float:
    """Tiny IQ/pressure-linked goal comparison noise.

    Goal noise is absolute and capped so it only matters when the candidate and
    current goal are close after switch cost. It is intentionally much smaller
    than action-level score noise.
    """
    base = max(0.0, float(context.goal_noise_scale))
    if base <= 0.0:
        return 0.0

    iq_instability = iq_decision_noise(context.iq)
    pressure = max(0.0, min(1.0, float(context.pressure_interrupt)))
    scale = base * (0.25 + iq_instability) * (1.0 + 0.35 * pressure)
    cap = base * (0.70 + 1.60 * iq_instability) * (1.0 + 0.50 * pressure)
    rng = context.rng if context.rng is not None else random
    noise = float(rng.gauss(0.0, scale))
    return max(-cap, min(cap, noise))


def select_goal_candidate(
    goal_candidates: Sequence[PlayerGoal],
    context: GoalSwitchContext,
) -> Optional[GoalCandidateChoice]:
    """Pick the best goal candidate with small bounded judgement noise."""
    best: Optional[GoalCandidateChoice] = None
    for goal in goal_candidates:
        noise = _goal_selection_noise(context)
        noisy_value = goal.value + noise
        choice = GoalCandidateChoice(
            goal=goal,
            candidate_noise=noise,
            noisy_value=noisy_value,
        )
        if best is None or choice.noisy_value > best.noisy_value:
            best = choice
    return best


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
            noisy_value_advantage=candidate_goal.value,
            reason="no_current_goal",
        )

    current_phase = current_goal.context.get("phase") if isinstance(current_goal.context, dict) else None
    if current_phase is None and current_goal.goal_type.startswith("defend_"):
        current_phase = "defend"
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
            noisy_value_advantage=candidate_goal.value - current_goal.value,
            reason="current_goal_phase_updated",
        )
    if (
        current_goal.goal_type == candidate_goal.goal_type == "cut_inside_to_shoot"
        and current_phase == candidate_phase == "drive"
    ):
        return GoalSelection(
            goal=candidate_goal,
            switched=False,
            switch_cost=0.0,
            value_advantage=candidate_goal.value - current_goal.value,
            noisy_value_advantage=candidate_goal.value - current_goal.value,
            reason="current_goal_drive_updated",
        )
    if (
        current_goal.goal_type == candidate_goal.goal_type == "hold_for_opportunity"
        and current_phase == candidate_phase == "scan"
    ):
        return GoalSelection(
            goal=candidate_goal,
            switched=False,
            switch_cost=0.0,
            value_advantage=candidate_goal.value - current_goal.value,
            noisy_value_advantage=candidate_goal.value - current_goal.value,
            reason="current_goal_scan_updated",
        )
    if current_phase == candidate_phase == "defend":
        return GoalSelection(
            goal=PlayerGoal(
                goal_type=candidate_goal.goal_type,
                target_pos=candidate_goal.target_pos,
                value=candidate_goal.value,
                confidence=candidate_goal.confidence,
                created_tick=current_goal.created_tick,
                last_updated_tick=candidate_goal.last_updated_tick,
                context=dict(candidate_goal.context),
            ),
            switched=True,
            switch_cost=0.0,
            value_advantage=candidate_goal.value - current_goal.value,
            noisy_value_advantage=candidate_goal.value - current_goal.value,
            reason="current_defensive_goal_updated",
        )
    switch_cost = goal_switch_cost(context)
    advantage = candidate_goal.value - current_goal.value
    switch_noise = _goal_selection_noise(context)
    noisy_advantage = advantage + switch_noise
    if noisy_advantage > switch_cost:
        return GoalSelection(
            goal=candidate_goal,
            switched=True,
            switch_cost=switch_cost,
            value_advantage=advantage,
            switch_noise=switch_noise,
            noisy_value_advantage=noisy_advantage,
            reason="candidate_clears_switch_cost",
        )
    return GoalSelection(
        goal=current_goal,
        switched=False,
        switch_cost=switch_cost,
        value_advantage=advantage,
        switch_noise=switch_noise,
        noisy_value_advantage=noisy_advantage,
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
    best_carry_target: Optional[Tuple[float, float]] = None,
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
        * (0.35 + 0.65 * _smoothstep(0.02, 0.14, carry_to_shoot))
    )
    drive_staleness = max(
        _smoothstep(2.0, 5.0, max(0, consecutive_carries)),
        _smoothstep(4.0, 9.0, max(0, goal_age_ticks)),
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
        carry_plan * (1.0 - 0.72 * already_shootable) * (1.0 - 0.58 * drive_staleness),
        finish_window * 0.55,
        release_window * 0.20,
    )
    if value <= 0.0:
        return None
    phase = "finish" if finish_window > 0.35 else "release" if stalled_drive else "drive"

    if best_carry_target is not None:
        target_x, target_y = best_carry_target
    else:
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
            drive_staleness=drive_staleness,
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


def evaluate_release_to_arriving_support_goal(
    *,
    player_pos: Tuple[float, float],
    support_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    support_value: float,
    receiver_goal_fit: float,
    shot_components: Dict[str, Any],
    consecutive_carries: int = 0,
    attracted_pressure: float = 0.0,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a release goal when a team-mate is arriving into a valued support lane."""
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
    layer_gap = abs(progress - target_progress)
    current_shot = float(shot_components.get("xg", 0.0) or 0.0)
    shot_readiness = max(
        float(shot_components.get("shot_readiness", 0.0) or 0.0),
        float(shot_components.get("open_medium_window", 0.0) or 0.0),
        float(shot_components.get("clean_second_line_shot", 0.0) or 0.0),
    )
    no_clear_shot = (1.0 - _smoothstep(0.080, 0.155, current_shot)) * (
        1.0 - _smoothstep(0.18, 0.56, shot_readiness)
    )
    release_maturity = max(
        _smoothstep(1.0, 3.0, max(0, consecutive_carries)),
        _smoothstep(0.18, 0.62, max(0.0, min(1.0, attracted_pressure))) * 0.72,
    )

    window = (
        _smoothstep(0.62, 0.88, progress)
        * _smoothstep(0.58, 0.84, target_progress)
        * (1.0 - _smoothstep(0.86, 0.96, target_progress))
        * _smoothstep(0.44, 0.86, target_centrality)
        * _smoothstep(5.0, 14.0, pass_distance)
        * (1.0 - _smoothstep(30.0, 44.0, pass_distance))
        * (1.0 - _smoothstep(0.28, 0.44, layer_gap))
        * _smoothstep(0.12, 0.58, receiver_goal_fit)
        * _smoothstep(0.050, 0.220, support_value)
        * no_clear_shot
        * (0.74 + 0.48 * release_maturity)
    )
    value = max(
        0.0,
        window
        * (0.11 + 1.18 * max(0.0, support_value))
        * (0.88 + 0.64 * _clamp01(receiver_goal_fit)),
    )
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="release_to_arriving_support",
        target_pos=support_target,
        value=value,
        confidence=max(value, receiver_goal_fit, support_value),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="release",
            completion="support_pass",
            abort="support_window_closed_or_shot_opens",
            handoff="default_value_model",
            progress=progress,
            target_progress=target_progress,
            target_centrality=target_centrality,
            pass_distance=pass_distance,
            layer_gap=layer_gap,
            support_value=support_value,
            receiver_goal_fit=receiver_goal_fit,
            current_shot=current_shot,
            shot_readiness=shot_readiness,
            consecutive_carries=consecutive_carries,
            attracted_pressure=attracted_pressure,
            release_maturity=release_maturity,
        ),
    )


def evaluate_through_ball_goal(
    *,
    player_pos: Tuple[float, float],
    pass_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    pass_score: float,
    components: Dict[str, Any],
    tick: int,
) -> Optional[PlayerGoal]:
    """Build a central through-ball goal from an existing pass-to-point value."""
    target_kind = str(components.get("target_kind", ""))
    if target_kind != "space":
        return None
    forward_dir = 1.0 if attacking_right else -1.0
    origin_progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    target_progress = float(
        components.get(
            "target_progress",
            pass_target[0] / max(1.0, pitch_length)
            if attacking_right
            else (pitch_length - pass_target[0]) / max(1.0, pitch_length),
        )
        or 0.0
    )
    centrality = float(
        components.get(
            "centrality",
            1.0 - min(1.0, abs(pass_target[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)),
        )
        or 0.0
    )
    progress_gain = float(
        components.get("progress_gain", (pass_target[0] - player_pos[0]) * forward_dir / max(1.0, pitch_length))
        or 0.0
    )
    high_threat = float(components.get("high_threat_space", 0.0) or 0.0)
    success_prob = float(components.get("success_prob", 0.0) or 0.0)
    receiver_pressure = float(components.get("receiver_pressure", 0.0) or 0.0)
    lane_risk = float(components.get("lane_risk", 0.0) or 0.0)

    window = (
        _smoothstep(0.42, 0.76, origin_progress)
        * _smoothstep(0.66, 0.92, target_progress)
        * _smoothstep(0.34, 0.88, centrality)
        * _smoothstep(0.040, 0.155, progress_gain)
        * _smoothstep(0.08, 0.58, high_threat)
        * _smoothstep(0.16, 0.58, success_prob)
        * (1.0 - _smoothstep(0.46, 0.88, receiver_pressure))
        * (1.0 - _smoothstep(0.34, 0.78, lane_risk))
    )
    value = max(0.0, window * (0.080 + max(0.0, pass_score) * 1.45 + high_threat * 0.060))
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="through_ball_behind",
        target_pos=pass_target,
        value=value,
        confidence=max(value, high_threat, success_prob),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="release",
            completion="through_ball_pass",
            abort="lane_closed_or_receiver_offside",
            handoff="default_value_model",
            origin_progress=origin_progress,
            target_progress=target_progress,
            centrality=centrality,
            progress_gain=progress_gain,
            high_threat_space=high_threat,
            success_prob=success_prob,
            receiver_pressure=receiver_pressure,
            lane_risk=lane_risk,
        ),
    )


def evaluate_byline_delivery_goal(
    *,
    player_pos: Tuple[float, float],
    delivery_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    pass_score: float,
    components: Dict[str, Any],
    tick: int,
) -> Optional[PlayerGoal]:
    """Build the release phase of a wide byline attack goal."""
    origin_progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    origin_width = abs(player_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    target_progress = float(
        components.get(
            "target_progress",
            delivery_target[0] / max(1.0, pitch_length)
            if attacking_right
            else (pitch_length - delivery_target[0]) / max(1.0, pitch_length),
        )
        or 0.0
    )
    centrality = float(
        components.get(
            "centrality",
            1.0 - min(1.0, abs(delivery_target[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)),
        )
        or 0.0
    )
    high_threat = float(components.get("high_threat_space", 0.0) or 0.0)
    final_third_combination = float(components.get("final_third_combination", 0.0) or 0.0)
    success_prob = float(components.get("success_prob", 0.0) or 0.0)
    receiver_pressure = float(components.get("receiver_pressure", 0.0) or 0.0)
    lane_risk = float(components.get("lane_risk", 0.0) or 0.0)

    window = (
        _smoothstep(0.78, 0.94, origin_progress)
        * _smoothstep(0.44, 0.82, origin_width)
        * _smoothstep(0.78, 0.96, target_progress)
        * _smoothstep(0.30, 0.88, centrality)
        * max(_smoothstep(0.22, 0.72, high_threat), _smoothstep(0.22, 0.72, final_third_combination))
        * _smoothstep(0.10, 0.46, success_prob)
        * (1.0 - _smoothstep(0.52, 0.92, receiver_pressure))
        * (1.0 - _smoothstep(0.46, 0.90, lane_risk))
    )
    value = max(
        0.0,
        window * (0.090 + max(0.0, pass_score) * 1.45 + max(high_threat, final_third_combination) * 0.070),
    )
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="wide_byline_attack",
        target_pos=delivery_target,
        value=value,
        confidence=max(value, high_threat, final_third_combination, success_prob),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="release",
            completion="box_delivery",
            abort="delivery_lane_closed_or_better_shot",
            handoff="default_value_model",
            origin_progress=origin_progress,
            origin_width=origin_width,
            target_progress=target_progress,
            centrality=centrality,
            high_threat_space=high_threat,
            final_third_combination=final_third_combination,
            success_prob=success_prob,
            receiver_pressure=receiver_pressure,
            lane_risk=lane_risk,
        ),
    )


def evaluate_drive_byline_goal(
    *,
    player_pos: Tuple[float, float],
    carry_target: Tuple[float, float],
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    carry_score: float,
    components: Dict[str, Any],
    delivery_support: float = 0.0,
    tick: int,
) -> Optional[PlayerGoal]:
    """Build the drive phase of a wide byline attack goal."""
    origin_progress = (
        player_pos[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - player_pos[0]) / max(1.0, pitch_length)
    )
    origin_width = abs(player_pos[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    target_progress = (
        carry_target[0] / max(1.0, pitch_length)
        if attacking_right
        else (pitch_length - carry_target[0]) / max(1.0, pitch_length)
    )
    target_width = abs(carry_target[1] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
    progress_gain = float(
        components.get("progress_gain", (target_progress - origin_progress))
        or 0.0
    )
    byline_window = float(components.get("byline_carry_window", 0.0) or 0.0)
    path_feasibility = float(components.get("path_feasibility", components.get("success_prob", 0.0)) or 0.0)
    manipulation = float(components.get("space_manipulation", 0.0) or 0.0)
    delivery_support = _clamp01(delivery_support)

    window = (
        _smoothstep(0.58, 0.82, origin_progress)
        * _smoothstep(0.44, 0.84, origin_width)
        * _smoothstep(0.72, 0.92, target_progress)
        * _smoothstep(0.50, 0.90, target_width)
        * _smoothstep(0.012, 0.090, progress_gain)
        * _smoothstep(0.020, 0.260, byline_window)
        * _smoothstep(0.34, 0.82, path_feasibility)
        * (0.72 + 0.52 * delivery_support)
    )
    value = max(
        0.0,
        window * (
            0.120
            + max(0.0, carry_score) * 1.40
            + manipulation * 0.050
            + byline_window * 0.300
            + delivery_support * 1.450
        ),
    )
    if value <= 0.0:
        return None

    return PlayerGoal(
        goal_type="wide_byline_attack",
        target_pos=carry_target,
        value=value,
        confidence=max(value, byline_window, path_feasibility),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="drive",
            completion="reach_byline_delivery_zone",
            abort="lane_closed_or_better_release",
            handoff="default_value_model",
            origin_progress=origin_progress,
            origin_width=origin_width,
            target_progress=target_progress,
            target_width=target_width,
            progress_gain=progress_gain,
            byline_carry_window=byline_window,
            path_feasibility=path_feasibility,
            space_manipulation=manipulation,
            delivery_support=delivery_support,
        ),
    )


def build_defensive_goal(
    *,
    action_type: str,
    target_pos: Tuple[float, float],
    value: float,
    tick: int,
    pressure: float = 0.0,
    threat: float = 0.0,
) -> PlayerGoal:
    """Build a traceable defensive goal from a spatial defensive choice."""
    goal_type_by_action = {
        "approach": "defend_press",
        "tackle": "defend_press",
        "mark_runner": "defend_mark_runner",
        "block_lane": "defend_cover_lane",
        "hold_position": "defend_recover_shape",
    }
    goal_type = goal_type_by_action.get(action_type, "defend_recover_shape")
    if action_type in ("block_lane", "hold_position") and threat > 0.58:
        goal_type = "defend_protect_box"
    return PlayerGoal(
        goal_type=goal_type,
        target_pos=target_pos,
        value=max(0.0, value),
        confidence=max(0.0, min(1.0, value)),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="defend",
            completion="deny_space_or_recover_shape",
            abort="possession_or_threat_changed",
            handoff="defensive_space_value",
            action=action_type,
            pressure=pressure,
            threat=threat,
        ),
    )


def build_off_ball_attack_goal(
    *,
    target_pos: Tuple[float, float],
    value: float,
    tick: int,
    components: Dict[str, Any],
) -> PlayerGoal:
    """Build a traceable off-ball attacking goal from a chosen support space."""
    second_line = float(components.get("second_line_support", 0.0) or 0.0)
    inside = float(components.get("inside_support", 0.0) or 0.0)
    support_angle = float(components.get("support_angle_value", 0.0) or 0.0)
    layoff = float(components.get("layoff_window", 0.0) or 0.0)
    candidate_progress = float(components.get("candidate_progress", 0.0) or 0.0)
    candidate_width = float(components.get("candidate_width", 0.0) or 0.0)
    box_arrival = (
        _smoothstep(0.76, 0.92, candidate_progress)
        * _smoothstep(0.18, 0.70, 1.0 - candidate_width)
        * (0.55 + 0.45 * max(second_line, inside, support_angle))
    )

    if box_arrival > 0.18:
        goal_type = "attack_box"
    elif second_line > 0.12:
        goal_type = "support_second_line"
    elif inside > 0.16:
        goal_type = "drop_between_lines"
    elif support_angle > 0.18 or layoff > 0.10:
        goal_type = "support_carrier"
    elif candidate_progress > 0.76:
        goal_type = "run_behind"
    elif candidate_width > 0.62 and candidate_progress > 0.58:
        goal_type = "hold_width"
    else:
        goal_type = "recycle_support"

    return PlayerGoal(
        goal_type=goal_type,
        target_pos=target_pos,
        value=max(0.0, value),
        confidence=max(0.0, min(1.0, value)),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="support",
            completion="receive_or_open_lane",
            abort="possession_or_shape_changed",
            handoff="off_ball_space_value",
            second_line_support=second_line,
            inside_support=inside,
            support_angle_value=support_angle,
            layoff_window=layoff,
            candidate_progress=candidate_progress,
            candidate_width=candidate_width,
            box_arrival=box_arrival,
        ),
    )


def build_on_ball_action_goal(
    *,
    action_type: str,
    target_pos: Tuple[float, float],
    value: float,
    tick: int,
    components: Dict[str, Any],
) -> PlayerGoal:
    """Build a traceable on-ball goal from the chosen action value."""
    progress_gain = float(components.get("progress_gain", 0.0) or 0.0)
    xg = float(components.get("xg", 0.0) or 0.0)
    pressure = float(components.get("nearest_pressure", 0.0) or components.get("receiver_pressure", 0.0) or 0.0)
    target_kind = str(components.get("target_kind", ""))

    if action_type == "shoot":
        goal_type = "create_shot"
    elif action_type == "carry":
        goal_type = "progress_carry" if progress_gain > 0.015 else "protect_ball"
    elif action_type == "pass":
        if progress_gain < -0.015:
            goal_type = "recycle"
        elif target_kind == "space":
            goal_type = "through_ball"
        else:
            goal_type = "switch_play" if abs(float(components.get("lateral_change", 0.0) or 0.0)) > 0.28 else "recycle"
    elif action_type == "hold":
        goal_type = "protect_ball"
    elif action_type == "clear":
        goal_type = "clear_danger"
    else:
        goal_type = "protect_ball"

    return PlayerGoal(
        goal_type=goal_type,
        target_pos=target_pos,
        value=max(0.0, value),
        confidence=max(0.0, min(1.0, value)),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="execute",
            completion="action_resolved",
            abort="possession_or_value_changed",
            handoff="on_ball_value_model",
            action=action_type,
            progress_gain=progress_gain,
            xg=xg,
            pressure=pressure,
            target_kind=target_kind,
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
    goal_width: float,
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
    weak_post_y = (
        (pitch_width - goal_width) / 2.0
        if ball_side >= 0.0
        else (pitch_width + goal_width) / 2.0
    )
    # Arrive just inside the weak-side post instead of drifting into a wide
    # channel. This keeps far-post runs useful for crosses and cutbacks.
    far_post_y = weak_post_y + (pitch_width / 2.0 - weak_post_y) * 0.12
    target_pos = (far_post_x, far_post_y)
    target_dist = ((player_pos[0] - far_post_x) ** 2 + (player_pos[1] - far_post_y) ** 2) ** 0.5

    value = (
        _smoothstep(0.72, 0.90, ball_progress)
        * _smoothstep(0.34, 0.72, ball_width)
        * _smoothstep(0.52, 0.82, max(player_progress, anchor_progress))
        * _smoothstep(0.08, 0.30, weak_side)
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
