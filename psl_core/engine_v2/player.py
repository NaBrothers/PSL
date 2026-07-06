"""Player model with pure reward-driven decision making.

Every player, every tick, chooses from candidates by score comparison.
NO hard rules -- all behavior emerges from reward/score comparisons.

On-ball candidates:
    carry_to(pos) -- score = position_value(target) * path_feasibility
    pass_to(tm)   -- score = pass_success_rate * position_value(tm.pos)
    pass_to_space -- score = PV(future_pos) * arrival_prob * pass_accuracy
    shoot         -- score = on_target_prob * (1-save_estimate) * goal_reward
    hold          -- score = observation value while team-mates improve positions
    clear         -- score = danger_reduction (high when pressured in own half)

Off-ball attacking:
    move_to(X) -- score = position_value(X) * reachability * pass_feasibility * space_creation
    stay        -- score = position_value(current_pos)

Off-ball defending:
    approach       -- safe, moderate score
    tackle         -- score = success_rate * ball_value - (1-success_rate) * stun_penalty
    block_lane     -- score = lane_threat_value
    mark_runner    -- score = attacker_threat (zone-based)
    hold_position  -- score = 0.35 (baseline safe choice)

IQ effect: noise applied to all scores + temperature-based softmax selection.
"""

from __future__ import annotations

import random
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .physics import distance, move_toward, player_speed, angle_between_points

if TYPE_CHECKING:
    from .config import EngineConfig
    from .pitch import Pitch
    from .ball import Ball
    from .goal import PlayerGoal


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


class PlayerState(Enum):
    OFF_BALL = "off_ball"
    ON_BALL = "on_ball"
    PRESSING = "pressing"
    CONTEST = "contest"
    STUNNED = "stunned"  # after failed tackle


@dataclass
class Player:
    """A player in the match simulation."""

    # Identity
    index: int  # 0-10 within team
    name: str
    position: str  # tactical position (GK, LB, etc.)
    color: str  # card color
    player_id: str = ""
    team_side: str = ""  # "home" or "away"

    # Abilities (13 keys)
    abilities: Dict[str, int] = field(default_factory=dict)
    overall: int = 50

    # State
    state: PlayerState = PlayerState.OFF_BALL
    pos: Tuple[float, float] = (0.0, 0.0)  # current position on pitch
    formation_pos: Tuple[float, float] = (0.0, 0.0)  # static base formation slot
    base_formation_pos: Tuple[float, float] = (0.0, 0.0)  # immutable half-specific slot
    tactical_anchor: Tuple[float, float] = (0.0, 0.0)  # dynamic role reference from ball context
    target_pos: Tuple[float, float] = (0.0, 0.0)  # where player is moving to
    movement_intent: str = "support"
    velocity: Tuple[float, float] = (0.0, 0.0)
    last_def_target: Tuple[float, float] = (0.0, 0.0)
    last_def_action: str = ""
    last_pressure_tick: int = -9999

    # Facing direction (degrees, 0=right)
    facing_direction: float = 0.0

    # Stun state (after failed tackle)
    stun_ticks_remaining: int = 0
    hold_ticks: int = 0
    possession_ticks: int = 0
    consecutive_carries: int = 0
    last_receive_origin: Tuple[float, float] = (0.0, 0.0)
    current_goal: Optional["PlayerGoal"] = None

    # Match stats
    goals: int = 0
    assists: int = 0
    shots: int = 0
    shots_on_target: int = 0
    passes_attempted: int = 0
    passes_completed: int = 0
    tackles_attempted: int = 0
    tackles_won: int = 0
    dribbles_attempted: int = 0
    dribbles_completed: int = 0
    interceptions: int = 0
    saves: int = 0
    distance_covered: float = 0.0
    clearances: int = 0
    unforced_errors: int = 0

    # Carry stats
    carries_attempted: int = 0
    carries_completed: int = 0
    crosses_attempted: int = 0
    crosses_completed: int = 0
    headers_attempted: int = 0
    headers_won: int = 0

    # Advanced stats for frontend
    xg: float = 0.0
    key_passes: int = 0
    progressive_passes: int = 0
    passes_into_final_third: int = 0
    passes_into_box: int = 0
    long_passes: int = 0
    completed_long_passes: int = 0
    progressive_carries: int = 0
    carries_into_final_third: int = 0
    carries_into_box: int = 0
    blocks: int = 0
    pressures: int = 0
    successful_pressures: int = 0
    turnovers: int = 0
    dispossessed: int = 0
    offsides: int = 0
    goals_conceded: int = 0
    psxg_faced: float = 0.0
    shot_log: List = field(default_factory=list)
    position_samples: List = field(default_factory=list)

    @property
    def position_xy(self) -> Tuple[float, float]:
        return self.pos

    @position_xy.setter
    def position_xy(self, value: Tuple[float, float]):
        self.pos = value

    @property
    def is_goalkeeper(self) -> bool:
        return self.position == "GK"

    @property
    def speed_value(self) -> int:
        return self.abilities.get("Speed", 50)

    @property
    def iq_value(self) -> int:
        return self.abilities.get("IQ", 50)

    @property
    def is_attacker(self) -> bool:
        return self.position in ("ST", "CF", "LW", "RW", "LF", "RF", "LS", "RS")

    @property
    def is_midfielder(self) -> bool:
        return self.position in (
            "CM", "LCM", "RCM", "CDM", "LDM", "RDM", "CAM", "RAM", "LAM",
            "LM", "RM", "AM",
        )

    @property
    def is_defender(self) -> bool:
        return self.position in (
            "CB", "LCB", "RCB", "LB", "RB", "LWB", "RWB",
        )

    @property
    def is_wide(self) -> bool:
        return self.position in (
            "LW", "RW", "LM", "RM", "LB", "RB", "LWB", "RWB",
        )

    # =========================================================================
    # IQ Noise
    # =========================================================================

    def _apply_iq_noise(self, score: float, config: "EngineConfig") -> float:
        """Apply IQ-based noise to a score value.

        Lower IQ = more noise = worse decisions.
        """
        noise_scale = (100 - max(1, min(99, self.iq_value))) / 100.0 * config.iq_noise_scale
        return score * (1.0 + random.gauss(0, noise_scale))

    # =========================================================================
    # Movement
    # =========================================================================

    def get_move_speed(self, config: "EngineConfig") -> float:
        """Get adaptive off-ball speed from ability, intent, and urgency."""
        max_speed = player_speed(self.speed_value, config.player_max_speed, config.player_min_speed)
        dist_to_target = distance(self.pos, self.target_pos)
        urgency = 1.0 - math.exp(-dist_to_target / 14.0)

        intent_base = {
            "idle": 0.08,
            "support": 0.36,
            "attack_run": 0.56,
            "recover_shape": 0.42,
            "defend_shape": 0.30,
            "press": 0.58,
            "contest": 0.78,
            "mark": 0.32,
            "block_lane": 0.30,
        }.get(self.movement_intent, 0.36)

        if self.state == PlayerState.PRESSING:
            intent_base = max(intent_base, 0.58)

        speed = max_speed * (intent_base + (0.28 * urgency))
        if dist_to_target < 1.0:
            speed *= 0.20
        return max(0.2, min(max_speed * 0.92, speed))

    def set_movement_target(self, target: Tuple[float, float], intent: str = None):
        """Set movement target with inertia so target points form a continuous field."""
        if intent is not None:
            self.movement_intent = intent

        if self.target_pos == (0.0, 0.0):
            self.target_pos = target
            return

        jump = distance(self.target_pos, target)
        if jump < 4.0:
            blend = 0.75
        elif jump < 14.0:
            blend = 0.45
        else:
            blend = 0.22

        if self.movement_intent == "attack_run":
            blend = min(0.92, blend + 0.54)
        elif self.movement_intent in ("press", "contest"):
            blend = min(0.78, blend + 0.30)
        elif self.movement_intent in ("defend_shape", "mark", "block_lane"):
            blend *= 0.85

        self.target_pos = (
            self.target_pos[0] * (1.0 - blend) + target[0] * blend,
            self.target_pos[1] * (1.0 - blend) + target[1] * blend,
        )

    def move_tick(self, config: "EngineConfig", pitch: "Pitch"):
        """Move player toward their target position for one tick."""
        if self.state == PlayerState.ON_BALL:
            return
        if self.state == PlayerState.STUNNED:
            return

        desired_speed = self.get_move_speed(config)
        old_pos = self.pos
        dx = self.target_pos[0] - self.pos[0]
        dy = self.target_pos[1] - self.pos[1]
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.05:
            desired_vx, desired_vy = 0.0, 0.0
        else:
            desired_vx = dx / dist * desired_speed
            desired_vy = dy / dist * desired_speed

        # Movement inertia: velocity can only change by limited acceleration.
        # This prevents instant 180-degree turns when a target point changes.
        vx, vy = self.velocity
        accel = player_speed(self.speed_value, config.player_max_speed, config.player_min_speed) * 0.42
        if self.movement_intent in ("press", "contest", "attack_run"):
            accel *= 1.18
        dvx = desired_vx - vx
        dvy = desired_vy - vy
        dv_len = math.sqrt(dvx * dvx + dvy * dvy)
        if dv_len > accel:
            dvx = dvx / dv_len * accel
            dvy = dvy / dv_len * accel
        vx += dvx
        vy += dvy

        max_speed = player_speed(self.speed_value, config.player_max_speed, config.player_min_speed) * 0.95
        v_len = math.sqrt(vx * vx + vy * vy)
        if v_len > max_speed:
            vx = vx / v_len * max_speed
            vy = vy / v_len * max_speed
        self.velocity = (vx, vy)

        new_pos = (self.pos[0] + vx, self.pos[1] + vy)
        new_pos = pitch.clamp(new_pos[0], new_pos[1])
        if new_pos != (self.pos[0] + vx, self.pos[1] + vy):
            self.velocity = (0.0, 0.0)
        self.pos = new_pos

        self.distance_covered += distance(old_pos, new_pos)

        if distance(old_pos, new_pos) > 0.1:
            self.facing_direction = angle_between_points(old_pos, new_pos)

    def tick_stun(self, config: "EngineConfig"):
        """Tick stun timer. Call every tick for stunned players."""
        if self.stun_ticks_remaining > 0:
            self.stun_ticks_remaining -= 1
            if self.stun_ticks_remaining <= 0:
                self.state = PlayerState.OFF_BALL

    def apply_stun(self, config: "EngineConfig"):
        """Apply stun penalty (after failed tackle)."""
        self.state = PlayerState.STUNNED
        stun_ticks = max(1, math.ceil(config.tackle_fail_stun_seconds / config.tick_duration))
        self.stun_ticks_remaining = stun_ticks

    # =========================================================================
    # On-Ball Decision: Pure Reward-Driven
    # =========================================================================

    def choose_on_ball(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        tick: int = 0,
        team_side: str = "",
        trace=None,
    ) -> Tuple[str, dict]:
        """Choose on-ball action via score comparison. Returns (action_type, details).

        action_type is one of: "carry", "pass", "pass_to_space", "shoot", "hold", "clear"
        details contains target info needed by the match loop.
        """
        # GK always distributes quickly
        if self.is_goalkeeper:
            return self._gk_choose(teammates, opponents, config, pitch, attacking_right)

        # Collect opponent/teammate positions for position_value
        opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
        tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != self.index]

        # Goal position
        if attacking_right:
            goal_center = (config.pitch_length, config.pitch_width / 2.0)
        else:
            goal_center = (0.0, config.pitch_width / 2.0)

        dist_to_goal = distance(self.pos, goal_center)

        # X progress (0 = own goal, 1 = opp goal)
        if attacking_right:
            x_progress = self.pos[0] / config.pitch_length
        else:
            x_progress = 1.0 - self.pos[0] / config.pitch_length

        # Pressure from nearby opponents
        nearby_opps = [o for o in opponents if not o.is_goalkeeper and distance(self.pos, o.pos) < 8.0]
        pressure = len(nearby_opps)

        candidates = []

        # ------- CARRY candidates -------
        current_state_value = self._current_state_value(
            teammates, opponents, config, pitch, attacking_right
        )

        carry_candidates = self._score_carry_options(
            config, pitch, attacking_right, opponents, opp_positions, tm_positions,
            teammates, current_state_value
        )
        candidates.extend(self._wrap_candidates(carry_candidates, "carry"))

        # ------- PASS candidates (unified pass-to-point model) -------
        pass_candidates = self._score_pass_point_options(
            teammates, opponents, config, pitch, attacking_right,
            opp_positions, tm_positions, current_state_value
        )
        candidates.extend(self._wrap_candidates(pass_candidates, "pass"))

        # ------- SHOOT candidate -------
        shoot_score = 0.0
        shoot_score, shoot_details = self._score_shoot(
            goal_center,
            config,
            pitch,
            opponents,
            dist_to_goal,
            current_state_value,
            teammates=teammates,
            attacking_right=attacking_right,
        )
        if shoot_score > 0:
            candidates.append(self._make_candidate("shoot", shoot_score, shoot_details, "shot"))

        # ------- HOLD / OBSERVE candidate -------
        release_candidates = carry_candidates + pass_candidates
        if shoot_score > 0:
            release_candidates.append((shoot_score, "shoot", shoot_details))
        if clear_score := self._score_clear(x_progress, pressure, config):
            release_candidates.append((clear_score, "clear", {}))
        hold_score = self._score_hold(
            teammates, opponents, config, pitch, attacking_right,
            pressure, shoot_score, release_candidates, [],
        )
        if hold_score > 0:
            hold_value = self._score_hold_value(
                teammates, opponents, config, pitch, attacking_right,
                pressure, shoot_score, release_candidates, [],
            )
            candidates.append(self._make_candidate(
                "hold", hold_value.score,
                {
                    "target": self.pos,
                    "success_prob": hold_value.success_prob,
                    "risk_cost": hold_value.risk_cost,
                    "current_value": hold_value.current_value,
                    "after_value": hold_value.after_value,
                    "components": hold_value.components,
                },
                "hold",
            ))

        # ------- CLEAR candidate -------
        clear_score = self._score_clear(x_progress, pressure, config)
        if clear_score > 0:
            # Clear target: away from own goal
            if attacking_right:
                clear_target = pitch.clamp(
                    self.pos[0] + random.uniform(15, 30),
                    self.pos[1] + random.uniform(-20, 20)
                )
            else:
                clear_target = pitch.clamp(
                    self.pos[0] - random.uniform(15, 30),
                    self.pos[1] + random.uniform(-20, 20)
                )
            clear_value = self._score_clear_value(x_progress, pressure, config)
            candidates.append(self._make_candidate(
                "clear", clear_value.score,
                {
                    "target": clear_target,
                    "success_prob": clear_value.success_prob,
                    "risk_cost": clear_value.risk_cost,
                    "current_value": clear_value.current_value,
                    "after_value": clear_value.after_value,
                    "components": clear_value.components,
                },
                "clear",
            ))

        # If no candidates (shouldn't happen), default to carry forward
        if not candidates:
            if attacking_right:
                target = pitch.clamp(self.pos[0] + 5.0, self.pos[1])
            else:
                target = pitch.clamp(self.pos[0] - 5.0, self.pos[1])
            return ("carry", {"target": target})

        goal_trace = None
        if getattr(config, "goal_continuity_enabled", False):
            candidates, goal_trace = self._apply_on_ball_goal_bias(
                candidates,
                carry_candidates,
                pass_candidates,
                opponents,
                shoot_details if shoot_score > 0 else {},
                max([candidate.score for candidate in candidates], default=0.0),
                config,
                pitch,
                attacking_right,
                tick,
            )

        current_goal_type = (
            self.current_goal.goal_type
            if self.current_goal is not None
            else ""
        )
        candidates = self._apply_release_confidence(candidates, current_goal_type)

        # Apply IQ noise to all candidate scores
        noisy_candidates = [
            candidate.with_score(self._apply_iq_noise(candidate.score, config))
            for candidate in candidates
        ]

        # Selection via softmax with IQ-based temperature
        chosen = self._softmax_select(noisy_candidates, config)
        if trace is not None and config.trace.should_trace(tick, self.index, "on_ball"):
            alternatives = self._decision_alternatives(noisy_candidates, chosen, config)
            trace.log_decision(
                tick=tick,
                team=team_side,
                player_idx=self.index,
                player_name=self.name,
                phase="on_ball",
                chosen=chosen,
                alternatives=alternatives,
                pos=self.pos,
                goal=goal_trace,
            )
        return (chosen.action_type, chosen.details)

    def _apply_release_confidence(self, candidates, current_goal_type: str = ""):
        """Favor controlled possession when no release action clearly wins."""
        hold_candidates = [candidate for candidate in candidates if candidate.action_type == "hold"]
        if not hold_candidates:
            return candidates
        hold_score = max(candidate.score for candidate in hold_candidates)
        if hold_score <= 0.0:
            return candidates

        adjusted = []
        for candidate in candidates:
            if candidate.action_type in ("hold", "clear"):
                adjusted.append(candidate)
                continue
            advantage = candidate.score - hold_score
            confidence = _smoothstep(0.006, 0.060, advantage)
            action_floor = 0.76 if candidate.action_type == "shoot" else 0.82
            multiplier = action_floor + (1.0 - action_floor) * confidence
            if current_goal_type == "hold_for_opportunity" and candidate.action_type == "pass_to_space":
                success_prob = float(candidate.value.success_prob or 0.0)
                components = candidate.value.components or {}
                receiver_pressure = float(components.get("receiver_pressure", 0.0) or 0.0)
                release_safety = success_prob * (1.0 - min(1.0, receiver_pressure))
                high_threat = float(components.get("high_threat_space", 0.0) or 0.0)
                unsafe_high_threat = _smoothstep(0.55, 0.90, high_threat) * (
                    1.0 - _smoothstep(0.28, 0.48, release_safety)
                )
                multiplier *= 1.0 - 0.22 * unsafe_high_threat
            adjusted.append(candidate.with_score(candidate.score * multiplier))
        return adjusted

    def _apply_on_ball_goal_bias(
        self,
        candidates,
        carry_candidates,
        pass_candidates,
        opponents,
        shoot_details: dict,
        immediate_best_score: float,
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        tick: int,
    ):
        from .goal import (
            GoalSwitchContext,
            evaluate_cut_inside_to_shoot_goal,
            evaluate_hold_for_opportunity_goal,
            evaluate_release_pressure_with_layoff_goal,
            evaluate_wide_hold_for_overlap_goal,
            select_goal,
        )

        best_carry = None
        for score, action_type, details in carry_candidates:
            if action_type != "carry":
                continue
            if best_carry is None or score > best_carry[0]:
                best_carry = (score, details)
        if best_carry is None:
            return candidates, None

        goal_candidates = []
        current_cut_goal = self.current_goal if self.current_goal and self.current_goal.goal_type == "cut_inside_to_shoot" else None
        cut_inside_goal = evaluate_cut_inside_to_shoot_goal(
            player_pos=self.pos,
            attacking_right=attacking_right,
            pitch_length=pitch.length,
            pitch_width=pitch.width,
            best_carry_components=best_carry[1].get("components", {}),
            best_shot_components=shoot_details.get("components", {}),
            consecutive_carries=self.consecutive_carries,
            goal_age_ticks=max(0, tick - current_cut_goal.created_tick) if current_cut_goal else 0,
            created_tick=current_cut_goal.created_tick if current_cut_goal else None,
            tick=tick,
        )
        if cut_inside_goal is not None:
            goal_candidates.append(cut_inside_goal)

        best_overlap = None
        for score, action_type, details in pass_candidates:
            if action_type not in ("pass", "pass_to_space"):
                continue
            target = details.get("target")
            components = details.get("components", {})
            if not target:
                continue
            target_progress = (
                target[0] / pitch.length
                if attacking_right
                else (pitch.length - target[0]) / pitch.length
            )
            target_width = abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0)
            carrier_width = abs(self.pos[1] - pitch.width / 2.0) / (pitch.width / 2.0)
            forward_gap = (target[0] - self.pos[0]) * (1.0 if attacking_right else -1.0)
            overlap_value = (
                max(0.0, score)
                * max(0.0, min(1.0, forward_gap / 14.0))
                * max(0.0, min(1.0, (target_width - carrier_width + 0.25) / 0.45))
                * (1.0 - min(1.0, float(components.get("receiver_pressure", 0.0) or 0.0)))
                * max(0.0, min(1.0, (target_progress - 0.62) / 0.22))
            )
            if best_overlap is None or overlap_value > best_overlap[0]:
                best_overlap = (overlap_value, target)
        if best_overlap is not None:
            wide_hold_goal = evaluate_wide_hold_for_overlap_goal(
                player_pos=self.pos,
                overlap_target=best_overlap[1],
                attacking_right=attacking_right,
                pitch_length=pitch.length,
                pitch_width=pitch.width,
                overlap_value=best_overlap[0],
                immediate_best_score=immediate_best_score,
                tick=tick,
            )
            if wide_hold_goal is not None:
                goal_candidates.append(wide_hold_goal)

        attracted_pressure = 0.0
        for opp in opponents:
            if opp.is_goalkeeper:
                continue
            d = distance(self.pos, opp.pos)
            if d < 11.0:
                attracted_pressure += 1.0 - d / 11.0
        attracted_pressure = min(1.0, attracted_pressure * 0.42)
        best_layoff = None
        for score, action_type, details in pass_candidates:
            if action_type not in ("pass", "pass_to_space"):
                continue
            target = details.get("target")
            if not target:
                continue
            pass_distance = distance(self.pos, target)
            components = details.get("components", {})
            target_progress = (
                target[0] / pitch.length
                if attacking_right
                else (pitch.length - target[0]) / pitch.length
            )
            target_centrality = 1.0 - min(1.0, abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0))
            backward_depth = (self.pos[0] - target[0]) * (1.0 if attacking_right else -1.0)
            layoff_value = (
                max(0.0, score)
                * max(0.0, min(1.0, (18.0 - abs(pass_distance - 12.0)) / 18.0))
                * max(0.0, min(1.0, (target_centrality - 0.20) / 0.65))
                * max(0.0, min(1.0, (0.28 - abs(target_progress - (self.pos[0] / pitch.length if attacking_right else (pitch.length - self.pos[0]) / pitch.length))) / 0.28))
                * (1.0 - min(1.0, float(components.get("receiver_pressure", 0.0) or 0.0)))
                * max(0.0, min(1.0, (backward_depth + 4.0) / 16.0))
            )
            if best_layoff is None or layoff_value > best_layoff[0]:
                best_layoff = (layoff_value, target)
        if best_layoff is not None:
            layoff_goal = evaluate_release_pressure_with_layoff_goal(
                player_pos=self.pos,
                layoff_target=best_layoff[1],
                attacking_right=attacking_right,
                pitch_length=pitch.length,
                pitch_width=pitch.width,
                attracted_pressure=attracted_pressure,
                layoff_value=best_layoff[0],
                immediate_best_score=immediate_best_score,
                tick=tick,
            )
            if layoff_goal is not None:
                goal_candidates.append(layoff_goal)

        best_support = None
        for score, action_type, details in pass_candidates:
            if action_type not in ("pass", "pass_to_space"):
                continue
            target = details.get("target")
            if not target:
                continue
            components = details.get("components", {})
            support_value = max(
                float(components.get("layoff_support_value", 0.0) or 0.0),
                float(components.get("short_combination_value", 0.0) or 0.0),
                float(components.get("second_line_cutback_value", 0.0) or 0.0),
                float(components.get("layoff_retention_value", 0.0) or 0.0),
                max(0.0, score) * 0.45,
            )
            pass_distance = distance(self.pos, target)
            target_progress = (
                target[0] / pitch.length
                if attacking_right
                else (pitch.length - target[0]) / pitch.length
            )
            target_centrality = 1.0 - min(1.0, abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0))
            fit = (
                support_value
                * max(0.0, min(1.0, (18.0 - abs(pass_distance - 12.0)) / 18.0))
                * max(0.0, min(1.0, (target_centrality - 0.18) / 0.70))
                * max(0.0, min(1.0, (0.90 - target_progress) / 0.26))
            )
            if best_support is None or fit > best_support[0]:
                best_support = (fit, target, support_value)
        hold_support = 0.0
        no_clear_release = 0.0
        for candidate in candidates:
            if candidate.action_type != "hold":
                continue
            hold_support = max(
                hold_support,
                float((candidate.value.components or {}).get("opportunity_wait", 0.0) or 0.0),
                float((candidate.value.components or {}).get("opportunity_wait_value", 0.0) or 0.0),
            )
            no_clear_release = max(
                no_clear_release,
                float((candidate.value.components or {}).get("no_clear_release", 0.0) or 0.0),
            )
        if best_support is None and (hold_support > 0.0 or no_clear_release > 0.0):
            target = self.pos
            best_support = (max(hold_support, no_clear_release) * 0.065, target, max(hold_support, no_clear_release) * 0.10)
        if best_support is not None:
            clear_carry_plan = 0.0
            for _, action_type, details in carry_candidates:
                if action_type != "carry":
                    continue
                components = details.get("components", {})
                clear_carry_plan = max(
                    clear_carry_plan,
                    float(components.get("carry_to_shoot_window", 0.0) or 0.0),
                    float(components.get("wide_second_line_carry_window", 0.0) or 0.0),
                    float(components.get("future_shot_gain", 0.0) or 0.0),
                )
            current_opportunity_goal = (
                self.current_goal
                if self.current_goal and self.current_goal.goal_type == "hold_for_opportunity"
                else None
            )
            if clear_carry_plan < 0.105 or current_opportunity_goal is not None:
                opportunity_goal = evaluate_hold_for_opportunity_goal(
                    player_pos=self.pos,
                    support_target=best_support[1],
                    attacking_right=attacking_right,
                    pitch_length=pitch.length,
                    pitch_width=pitch.width,
                    support_value=best_support[2],
                    hold_value=hold_support,
                    shot_components=shoot_details.get("components", {}),
                    immediate_best_score=immediate_best_score,
                    goal_age_ticks=max(0, tick - current_opportunity_goal.created_tick) if current_opportunity_goal else 0,
                    created_tick=current_opportunity_goal.created_tick if current_opportunity_goal else None,
                    tick=tick,
                )
                if opportunity_goal is not None:
                    goal_candidates.append(opportunity_goal)

        candidate_goal = max(goal_candidates, key=lambda goal: goal.value) if goal_candidates else None
        if candidate_goal is None and self.current_goal is None:
            return candidates, None

        if candidate_goal is None:
            # Re-evaluate existing goals conservatively when the current window disappears.
            if self.current_goal and self.current_goal.goal_type not in (
                "cut_inside_to_shoot",
                "wide_hold_for_overlap",
                "release_pressure_with_layoff",
                "hold_for_opportunity",
            ):
                self.current_goal = None
                return candidates, None
            candidate_goal = self.current_goal

        context = GoalSwitchContext(
            base=0.035,
            context_stability=1.0,
            role_discipline=1.0,
            pressure_interrupt=0.0,
            iq=self.iq_value,
        )
        selection = select_goal(self.current_goal, candidate_goal, context)
        self.current_goal = selection.goal
        goal_trace = selection.to_dict()
        selected_phase = selection.goal.context.get("phase", "") if selection.goal and selection.goal.context else ""
        if selection.goal.goal_type == "cut_inside_to_shoot" and selected_phase == "release":
            self.current_goal = None
            return candidates, goal_trace

        if selection.goal.goal_type != "cut_inside_to_shoot":
            if selection.goal.goal_type not in (
                "wide_hold_for_overlap",
                "release_pressure_with_layoff",
                "hold_for_opportunity",
            ):
                return candidates, goal_trace

        biased = []
        bias = max(0.0, float(getattr(config, "goal_cut_inside_bias", 0.0)))
        goal_phase = selected_phase
        for candidate in candidates:
            if selection.goal.goal_type == "cut_inside_to_shoot" and candidate.action_type == "carry":
                components = candidate.value.components or {}
                window = max(
                    float(components.get("carry_to_shoot_window", 0.0) or 0.0),
                    float(components.get("wide_second_line_carry_window", 0.0) or 0.0),
                )
                if window > 0.0 and goal_phase == "drive":
                    candidate = candidate.with_score(candidate.score + bias * window)
            elif selection.goal.goal_type == "cut_inside_to_shoot" and candidate.action_type == "shoot":
                components = candidate.value.components or {}
                xg_window = _smoothstep(0.08, 0.18, float(components.get("xg", 0.0) or 0.0))
                second_touch_window = _smoothstep(1.0, 3.0, max(0, self.consecutive_carries))
                finish_window = xg_window * second_touch_window
                readiness = max(
                    float(components.get("shot_readiness", 0.0) or 0.0),
                    float(components.get("open_medium_window", 0.0) or 0.0),
                    float(components.get("clean_second_line_shot", 0.0) or 0.0),
                    finish_window,
                )
                if readiness > 0.0:
                    goal_bonus = max(
                        bias * readiness * (1.0 + second_touch_window),
                        (0.10 if goal_phase == "finish" else 0.035) * finish_window,
                    )
                    candidate = candidate.with_score(candidate.score + goal_bonus)
            elif selection.goal.goal_type == "wide_hold_for_overlap":
                if candidate.action_type == "hold":
                    candidate = candidate.with_score(candidate.score + bias * selection.goal.value)
                elif candidate.action_type in ("pass", "pass_to_space") and candidate.target:
                    d = distance(candidate.target, selection.goal.target_pos)
                    overlap_fit = max(0.0, 1.0 - d / 16.0)
                    if overlap_fit > 0.0:
                        candidate = candidate.with_score(candidate.score + bias * overlap_fit * selection.goal.value)
            elif selection.goal.goal_type == "release_pressure_with_layoff":
                if candidate.action_type == "hold":
                    candidate = candidate.with_score(candidate.score + bias * selection.goal.value * 0.35)
                elif candidate.action_type in ("pass", "pass_to_space") and candidate.target:
                    d = distance(candidate.target, selection.goal.target_pos)
                    layoff_fit = max(0.0, 1.0 - d / 12.0)
                    if layoff_fit > 0.0:
                        candidate = candidate.with_score(candidate.score + bias * layoff_fit * selection.goal.value)
            elif selection.goal.goal_type == "hold_for_opportunity":
                if candidate.action_type == "hold":
                    details = dict(candidate.details or {})
                    details["opportunity_target"] = selection.goal.target_pos
                    details["opportunity_goal"] = selection.goal.to_dict()
                    candidate = candidate.with_score(candidate.score + bias * selection.goal.value * 0.70)
                    candidate = candidate.__class__(
                        phase=candidate.phase,
                        action_type=candidate.action_type,
                        target=candidate.target,
                        value=candidate.value,
                        details=details,
                        source=candidate.source,
                    )
                elif candidate.action_type in ("pass", "pass_to_space") and candidate.target:
                    d = distance(candidate.target, selection.goal.target_pos)
                    support_fit = max(0.0, 1.0 - d / 13.0)
                    if support_fit > 0.0:
                        candidate = candidate.with_score(candidate.score + bias * support_fit * selection.goal.value * 1.15)
            biased.append(candidate)
        return biased, goal_trace

    def _make_candidate(
        self,
        action_type: str,
        score: float,
        details: dict,
        source: str,
        success_prob: float = 1.0,
        risk_cost: float = 0.0,
        current_value: float = 0.0,
        after_value: float = 0.0,
        components: dict = None,
    ):
        from .value_model import ActionCandidate, ValueResult

        target = details.get("target") if details else None
        if details:
            if success_prob == 1.0:
                success_prob = details.get("success_prob", success_prob)
            if risk_cost == 0.0:
                risk_cost = details.get("risk_cost", risk_cost)
            if current_value == 0.0:
                current_value = details.get("current_value", current_value)
            if after_value == 0.0:
                after_value = details.get("after_value", after_value)
            if components is None:
                components = details.get("components", {})
        components = dict(components or {})
        components.setdefault("consecutive_carries", self.consecutive_carries)
        components.setdefault("possession_ticks", self.possession_ticks)
        value = ValueResult(
            score=score,
            success_prob=success_prob,
            risk_cost=risk_cost,
            current_value=current_value,
            after_value=after_value,
            components=components,
        )
        return ActionCandidate(
            phase="on_ball",
            action_type=action_type,
            target=target,
            value=value,
            details=details,
            source=source,
        )

    def _wrap_candidates(self, candidates, source: str):
        return [
            self._make_candidate(
                action_type=action_type,
                score=score,
                details=details,
                source=source,
                success_prob=details.get("success_prob", 1.0) if details else 1.0,
                risk_cost=details.get("risk_cost", 0.0) if details else 0.0,
                current_value=details.get("current_value", 0.0) if details else 0.0,
                after_value=details.get("after_value", 0.0) if details else 0.0,
                components=details.get("components", {}) if details else {},
            )
            for score, action_type, details in candidates
        ]

    def _decision_alternatives(self, candidates, chosen, config: "EngineConfig"):
        detail = config.trace.detail
        if detail == "chosen":
            return []
        ranked = sorted(candidates, key=self._candidate_score, reverse=True)
        alternatives = [candidate for candidate in ranked if candidate is not chosen]
        if detail == "top_candidates":
            return alternatives[:max(0, int(config.trace.top_k))]
        if detail == "full":
            return alternatives
        return []

    def _score_carry_options(
        self,
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opponents: List["Player"],
        opp_positions: List[Tuple[float, float]],
        tm_positions: List[Tuple[float, float]],
        teammates: List["Player"],
        current_state_value: float,
    ) -> List[Tuple[float, str, dict]]:
        """Generate and score carry candidates.

        score = position_value(target) * path_feasibility
        path_feasibility = 1.0 if no opp within 4m of path, decays with proximity
        """
        from .position_value import position_value

        results = []
        forward_dir = 1.0 if attacking_right else -1.0
        current_pv = position_value(
            self.pos[0], self.pos[1], pitch, attacking_right,
            opp_positions, tm_positions, config
        )

        # Sample reachable space around the carrier. Direction is not the
        # action; it is just candidate generation for the value model.
        dribbling = self.abilities.get("Dribbling", 50) / 100.0
        max_speed = player_speed(self.speed_value, config.player_max_speed, config.player_min_speed)
        base_dist = max(config.carrier_speed, max_speed * (0.42 + 0.18 * dribbling))
        candidate_offsets = [
            (forward_dir * base_dist, 0.0),
            (forward_dir * base_dist * 0.75, base_dist * 0.75),
            (forward_dir * base_dist * 0.75, -base_dist * 0.75),
            (0.0, base_dist),
            (0.0, -base_dist),
        ]
        # Angle-improving carry: from wide areas, moving diagonally toward the
        # goal center can create a better shot or passing lane. This is derived
        # from geometry, not a winger-specific instruction.
        goal_center_y = config.pitch_width / 2.0
        center_pull = max(-base_dist, min(base_dist, goal_center_y - self.pos[1]))
        if abs(center_pull) > 0.25:
            candidate_offsets.append((forward_dir * base_dist * 0.70, center_pull * 0.85))
            candidate_offsets.append((forward_dir * base_dist * 0.35, center_pull))

        # Shot-window carries: sample the continuous geometry between the
        # current lane, the goal center, and the central shooting lane. This lets
        # wide carriers discover inside touches when the value model says the
        # next state opens a better shot, without assigning that behavior to
        # specific winger/fullback positions.
        goal_x = config.pitch_length if attacking_right else 0.0
        goal_dx = goal_x - self.pos[0]
        goal_dy = goal_center_y - self.pos[1]
        goal_dist = max(1.0, math.sqrt(goal_dx * goal_dx + goal_dy * goal_dy))
        goal_vec = (goal_dx / goal_dist, goal_dy / goal_dist)
        forward_vec = (forward_dir, 0.0)
        inside_vec = (forward_dir * 0.45, 1.0 if goal_center_y > self.pos[1] else -1.0)
        inside_len = max(1.0, math.sqrt(inside_vec[0] * inside_vec[0] + inside_vec[1] * inside_vec[1]))
        inside_vec = (inside_vec[0] / inside_len, inside_vec[1] / inside_len)
        width_t = min(1.0, abs(self.pos[1] - goal_center_y) / (config.pitch_width / 2.0))
        progress_t = self.pos[0] / config.pitch_length if attacking_right else (config.pitch_length - self.pos[0]) / config.pitch_length
        shot_window_t = max(0.0, min(1.0, (progress_t - 0.45) / 0.38))
        for blend in (0.35, 0.65, 0.90):
            vx = forward_vec[0] * (1.0 - blend) + goal_vec[0] * blend
            vy = forward_vec[1] * (1.0 - blend) + goal_vec[1] * blend
            vlen = max(1.0, math.sqrt(vx * vx + vy * vy))
            candidate_offsets.append((vx / vlen * base_dist * (1.0 + 0.25 * shot_window_t), vy / vlen * base_dist * (1.0 + 0.25 * width_t)))
        for scale in (0.85, 1.20):
            candidate_offsets.append((
                inside_vec[0] * base_dist * scale * (0.75 + 0.35 * shot_window_t),
                inside_vec[1] * base_dist * scale * (0.55 + 0.55 * width_t),
            ))
        carry_horizon = base_dist * (1.55 + 0.45 * shot_window_t)
        for blend in (0.45, 0.75):
            vx = inside_vec[0] * (1.0 - blend) + goal_vec[0] * blend
            vy = inside_vec[1] * (1.0 - blend) + goal_vec[1] * blend
            vlen = max(1.0, math.sqrt(vx * vx + vy * vy))
            candidate_offsets.append((
                vx / vlen * carry_horizon,
                vy / vlen * carry_horizon * (0.85 + 0.35 * width_t),
            ))
        if progress_t > 0.68 and width_t > 0.28:
            side_sign = 1.0 if self.pos[1] > goal_center_y else -1.0
            half_space_y = goal_center_y + side_sign * config.pitch_width * 0.14
            inner_channel_y = goal_center_y + side_sign * config.pitch_width * 0.08
            dx_to_half_space = forward_dir * base_dist * (1.82 + 0.58 * shot_window_t)
            dy_to_half_space = half_space_y - self.pos[1]
            dy_to_inner = inner_channel_y - self.pos[1]
            dy_to_half_space = max(-base_dist * 2.8, min(base_dist * 2.8, dy_to_half_space))
            dy_to_inner = max(-base_dist * 3.2, min(base_dist * 3.2, dy_to_inner))
            candidate_offsets.append((dx_to_half_space, dy_to_half_space))
            candidate_offsets.append((dx_to_half_space * 0.72, dy_to_half_space * 0.82))
            if progress_t > 0.72:
                candidate_offsets.append((dx_to_half_space * 1.06, dy_to_inner))
                candidate_offsets.append((dx_to_half_space * 0.82, dy_to_inner * 0.74))

        # Under pressure, add smaller shielding touches into adjacent spaces.
        nearest_opp = min(
            [distance(self.pos, o.pos) for o in opponents if not o.is_goalkeeper],
            default=99.0,
        )
        if nearest_opp < 7.0:
            candidate_offsets.extend([
                (-forward_dir * base_dist * 0.30, base_dist * 0.45),
                (-forward_dir * base_dist * 0.30, -base_dist * 0.45),
            ])

        seen_targets = set()
        for dx, dy in candidate_offsets:
            target = pitch.clamp(self.pos[0] + dx, self.pos[1] + dy)
            key = (round(target[0], 1), round(target[1], 1))
            if key in seen_targets:
                continue
            seen_targets.add(key)

            # Position value of target
            pv = position_value(
                target[0], target[1], pitch, attacking_right,
                opp_positions, tm_positions, config
            )

            # Path feasibility: can I carry forward before defenders reach me?
            # Pure physics: my time to reach target vs defender time to intercept my path
            feasibility = 1.0
            my_speed = max(config.carrier_speed, 0.1)
            time_i_carry = math.sqrt(dx*dx + dy*dy) / my_speed  # time for me to reach target
            path_min_perp = 99.0
            path_peak_threat = 0.0
            path_peak_proj = 0.0
            path_peak_final_third_control = 0.0
            path_peak_control_factor = 0.0
            
            for opp in opponents:
                if opp.is_goalkeeper:
                    continue
                # How long would this defender take to reach my carry path?
                # Project defender onto my movement direction to find closest intercept point
                opp_dx = opp.pos[0] - self.pos[0]
                opp_dy = opp.pos[1] - self.pos[1]
                move_len = math.sqrt(dx * dx + dy * dy)
                if move_len < 0.1:
                    continue
                
                # Perpendicular distance to my path
                perp_dist = abs(opp_dx * (dy/move_len) - opp_dy * (dx/move_len))
                # Forward projection (is defender ahead of me or behind?)
                proj = (opp_dx * dx + opp_dy * dy) / (move_len * move_len)
                
                if proj < -0.5 or proj > 2.0:
                    continue  # defender is behind me or way ahead — irrelevant
                path_min_perp = min(path_min_perp, perp_dist)
                
                # Time for defender to reach my path
                def_speed = (opp.abilities.get("Speed", 50) / 100.0) * config.player_max_speed
                time_def_reaches = perp_dist / max(def_speed, 0.1)
                intent_factor = 0.62
                speed_factor = 0.82 + 0.36 * (opp.abilities.get("Speed", 50) / 100.0)
                defence_factor = 0.82 + 0.30 * (opp.abilities.get("Defence", 50) / 100.0)
                control_range = config.tackle_range * intent_factor * speed_factor * defence_factor
                duel_control = (
                    max(0.0, 1.0 - perp_dist / max(0.1, control_range))
                    * max(0.0, min(1.0, (proj + 0.10) / 1.10))
                    * max(0.0, min(1.0, (1.10 - proj) / 1.10))
                )
                if duel_control > 0.0:
                    my_drib = self.abilities.get("Dribbling", 50) / 100.0
                    def_tack = opp.abilities.get("Tackling", 50) / 100.0
                    control_factor = def_tack / (my_drib + def_tack + 0.01)
                    feasibility *= max(0.34, 1.0 - duel_control * control_factor * 0.46)
                    path_peak_threat = max(path_peak_threat, duel_control)

                target_progress = target[0] / config.pitch_length if attacking_right else (config.pitch_length - target[0]) / config.pitch_length
                central_lane = 1.0 - min(1.0, abs(target[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
                final_third_control = (
                    max(0.0, min(1.0, (target_progress - 0.72) / 0.18))
                    * central_lane
                    * max(0.0, 1.0 - perp_dist / 5.8)
                    * max(0.0, min(1.0, (proj + 0.15) / 1.15))
                    * max(0.0, min(1.0, (1.15 - proj) / 1.15))
                )
                if final_third_control > 0.0:
                    my_drib = self.abilities.get("Dribbling", 50) / 100.0
                    def_tack = opp.abilities.get("Tackling", 50) / 100.0
                    control_factor = def_tack / (my_drib + def_tack + 0.01)
                    if final_third_control > path_peak_final_third_control:
                        path_peak_final_third_control = final_third_control
                        path_peak_proj = proj
                        path_peak_control_factor = control_factor
                    feasibility *= max(0.48, 1.0 - final_third_control * control_factor * 0.34)
                
                # If defender can reach my path before I pass that point → obstacle
                if time_def_reaches < time_i_carry:
                    # How much of a threat? Depends on timing margin
                    threat = max(0.0, 1.0 - time_def_reaches / time_i_carry)  # 0=barely makes it, 1=already there
                    # Skill contest: my dribbling vs their tackling
                    my_drib = self.abilities.get("Dribbling", 50) / 100.0
                    def_tack = opp.abilities.get("Tackling", 50) / 100.0
                    skill_factor = my_drib / (my_drib + def_tack + 0.01)  # 0.5 = equal
                    # Feasibility reduction: high threat + low skill = big reduction
                    reduction = threat * (1.0 - skill_factor)  # 0..0.5 for equal players
                    if threat > path_peak_threat:
                        path_peak_threat = threat
                        path_peak_proj = proj
                    feasibility *= max(0.2, 1.0 - reduction)

            # Carry should be rewarded for improving the situation, not for
            # repeatedly re-claiming the absolute value of an already good
            # shooting position. This prevents one-more-touch loops near goal.
            pv_gain = pv - current_pv
            retain_value = current_pv * 0.18
            from .value_model import evaluate_carry_target
            value = evaluate_carry_target(
                self, target, pv, current_pv, current_state_value,
                feasibility, teammates, opponents, config, pitch, attacking_right,
            )
            components = dict(value.components)
            conflict_load = max(path_peak_threat, path_peak_final_third_control)
            repeated_load = _smoothstep(0.0, 3.0, max(0, self.consecutive_carries))
            feasibility_loss = _smoothstep(0.0, 0.55, 1.0 - feasibility)
            conflict_cost = (conflict_load ** 1.35) * (
                0.020
                + 0.115 * repeated_load
                + 0.075 * feasibility_loss
                + 0.105 * repeated_load * feasibility_loss
            )
            score = max(0.0, value.score - conflict_cost)
            components.update({
                "path_min_perp": path_min_perp if path_min_perp < 99.0 else 0.0,
                "path_peak_threat": path_peak_threat,
                "path_peak_proj": path_peak_proj,
                "path_peak_final_third_control": path_peak_final_third_control,
                "path_peak_control_factor": path_peak_control_factor,
                "path_conflict_cost": conflict_cost,
            })
            results.append((score, "carry", {
                "target": target,
                "success_prob": feasibility,
                "risk_cost": value.risk_cost,
                "current_value": current_state_value,
                "after_value": value.after_value,
                "components": components,
            }))

        return results

    def _score_hold(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        pressure: int,
        shoot_score: float,
        pass_candidates: List[Tuple[float, str, dict]],
        space_pass_candidates: List[Tuple[float, str, dict]],
    ) -> float:
        return self._score_hold_value(
            teammates, opponents, config, pitch, attacking_right,
            pressure, shoot_score, pass_candidates, space_pass_candidates,
        ).score

    def _score_hold_value(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        pressure: int,
        shoot_score: float,
        pass_candidates: List[Tuple[float, str, dict]],
        space_pass_candidates: List[Tuple[float, str, dict]],
    ):
        """Score pausing on the ball to scan, settle, and let runs develop."""
        opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
        tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != self.index]
        from .position_value import position_value

        current_pv = position_value(
            self.pos[0], self.pos[1], pitch, attacking_right,
            opp_positions, tm_positions, config
        )
        best_pass = max([c[0] for c in pass_candidates + space_pass_candidates], default=0.0)

        # Team-mates moving into better spaces make waiting valuable.
        forward_dir = 1.0 if attacking_right else -1.0
        developing_runs = 0.0
        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue
            move_progress = (tm.target_pos[0] - tm.pos[0]) * forward_dir
            if move_progress > 1.0:
                developing_runs += min(1.0, move_progress / 8.0)
        developing_runs = min(2.0, developing_runs)

        nearest_pressure = 0.0
        for opp in opponents:
            if opp.is_goalkeeper:
                continue
            d = distance(self.pos, opp.pos)
            if d < 5.0:
                nearest_pressure = max(nearest_pressure, 1.0 - d / 5.0)
        opportunity_wait_value = self._opportunity_wait_value(
            teammates, config, pitch, attacking_right, shoot_score
        )
        from .value_model import evaluate_hold
        return evaluate_hold(
            self, current_pv, pressure, nearest_pressure,
            developing_runs, best_pass, shoot_score,
            opportunity_wait_value=opportunity_wait_value,
        )

    def _opportunity_wait_value(
        self,
        teammates: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        shoot_score: float,
    ) -> float:
        """Value of controlling the ball while better options develop."""
        forward_dir = 1.0 if attacking_right else -1.0
        holder_progress = (
            self.pos[0] / max(1.0, pitch.length)
            if attacking_right
            else (pitch.length - self.pos[0]) / max(1.0, pitch.length)
        )
        holder_width = abs(self.pos[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0)
        value = 0.0
        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue
            target = getattr(tm, "target_pos", tm.pos)
            target_progress = (
                target[0] / max(1.0, pitch.length)
                if attacking_right
                else (pitch.length - target[0]) / max(1.0, pitch.length)
            )
            target_centrality = 1.0 - min(1.0, abs(target[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0))
            target_width = abs(target[1] - pitch.width / 2.0) / max(1.0, pitch.width / 2.0)
            target_dist = distance(self.pos, target)
            move_progress = (target[0] - tm.pos[0]) * forward_dir
            depth_gap = (self.pos[0] - target[0]) * forward_dir
            lateral_gap = abs(target[1] - self.pos[1]) / max(1.0, pitch.width / 2.0)

            short_angle = (
                _smoothstep(0.66, 0.88, holder_progress)
                * _smoothstep(5.0, 13.0, target_dist)
                * (1.0 - _smoothstep(25.0, 36.0, target_dist))
                * _smoothstep(0.10, 0.48, lateral_gap)
                * _smoothstep(0.30, 0.82, target_centrality)
            )
            second_line = (
                _smoothstep(0.68, 0.88, holder_progress)
                * _smoothstep(0.58, 0.82, target_progress)
                * (1.0 - _smoothstep(0.84, 0.95, target_progress))
                * _smoothstep(4.0, 14.0, depth_gap)
                * (1.0 - _smoothstep(24.0, 36.0, depth_gap))
                * _smoothstep(0.42, 0.88, target_centrality)
            )
            developing = (
                _smoothstep(0.0, 5.0, max(0.0, move_progress))
                * _smoothstep(0.58, 0.84, target_progress)
                * (1.0 - _smoothstep(0.88, 0.97, target_progress))
                * (1.0 - _smoothstep(18.0, 32.0, target_dist))
            )
            width_release = (
                _smoothstep(0.18, 0.58, max(holder_width, target_width))
                * _smoothstep(0.08, 0.40, lateral_gap)
                * (1.0 - _smoothstep(22.0, 34.0, target_dist))
            )
            value = max(
                value,
                max(short_angle, second_line) * (0.70 + 0.30 * developing)
                + width_release * 0.28,
            )

        return max(0.0, min(1.0, value)) * (1.0 - 0.55 * _smoothstep(0.08, 0.18, shoot_score))

    def _score_pass_point_options(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opp_positions: List[Tuple[float, float]],
        tm_positions: List[Tuple[float, float]],
        current_state_value: float,
    ) -> List[Tuple[float, str, dict]]:
        """Generate and score all pass-to-point candidates with one model."""
        from .value_model import evaluate_pass_target
        from .position_value import position_value

        results = []
        forward_dir = 1.0 if attacking_right else -1.0
        offside_line = self._get_offside_line(opponents, attacking_right, config)
        front_anchors = []
        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue
            anchor_progress = tm.tactical_anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
            if anchor_progress > 0.58:
                front_anchors.append(tm.tactical_anchor)
        front_center = None
        if front_anchors:
            front_center = (
                sum(p[0] for p in front_anchors) / len(front_anchors),
                sum(p[1] for p in front_anchors) / len(front_anchors),
            )

        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue

            raw_targets = [(tm.pos, 1.0)]

            # Half-tick predicted position.
            future_x = tm.pos[0] + (tm.target_pos[0] - tm.pos[0]) * 0.5
            future_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.5
            raw_targets.append((pitch.clamp(future_x, future_y), 0.92))

            # Safe recycle/support points are part of the same pass-to-point
            # value field. They let low-quality long shots lose naturally to
            # retaining possession when the attack has no good forward option.
            support_x = tm.pos[0] * 0.65 + self.pos[0] * 0.35
            support_y = tm.pos[1] * 0.70 + self.pos[1] * 0.30
            raw_targets.append((pitch.clamp(support_x, support_y), 0.88))

            switch_y = tm.pos[1] * 0.45 + (config.pitch_width - self.pos[1]) * 0.55
            raw_targets.append((pitch.clamp(support_x, switch_y), 0.76))

            tm_width_ratio = min(1.0, abs(tm.tactical_anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
            tm_progress_hint = tm.tactical_anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
            if tm_width_ratio > 0.50 and tm_progress_hint > 0.56:
                wide_lane_y = tm.tactical_anchor[1] * 0.72 + tm.pos[1] * 0.28
                wide_lane_x = max(tm.pos[0], tm.tactical_anchor[0]) if attacking_right else min(tm.pos[0], tm.tactical_anchor[0])
                raw_targets.append((
                    pitch.clamp(wide_lane_x + forward_dir * 4.0, wide_lane_y),
                    0.78,
                ))

            # A small leading pass if the team-mate is moving forward.
            move_progress = (tm.target_pos[0] - tm.pos[0]) * forward_dir
            if move_progress > 1.0:
                lead_x = tm.pos[0] + forward_dir * min(12.0, 4.0 + move_progress)
                lead_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.35
                raw_targets.append((pitch.clamp(lead_x, lead_y), 0.82))

            carrier_progress = self.pos[0] / config.pitch_length if attacking_right else (config.pitch_length - self.pos[0]) / config.pitch_length
            if (
                self.consecutive_carries >= 3
                and carrier_progress > 0.62
                and not tm.is_defender
            ):
                outlet_dist = distance(tm.pos, self.pos)
                if 4.0 < outlet_dist < 34.0:
                    stale_release = min(1.0, (self.consecutive_carries - 2) / 4.0)
                    support_weight = 1.0 if tm.is_midfielder or tm.is_wide else 0.72
                    outlet_x = tm.pos[0] + (tm.target_pos[0] - tm.pos[0]) * 0.35
                    outlet_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.35
                    raw_targets.append((pitch.clamp(outlet_x, outlet_y), 0.86 * support_weight))
                    raw_targets.append((tm.pos, 0.90 * support_weight))

                    lateral_sign = 1.0 if tm.pos[1] >= self.pos[1] else -1.0
                    release_depth = 4.0 + 6.0 * stale_release
                    release_width = min(12.0, max(4.0, abs(tm.pos[1] - self.pos[1]) * 0.50 + 4.0))
                    release_x = self.pos[0] - forward_dir * release_depth
                    release_y = self.pos[1] + lateral_sign * release_width
                    if distance((release_x, release_y), tm.pos) < 28.0:
                        raw_targets.append((pitch.clamp(release_x, release_y), 0.80 * support_weight))

                    anchor_x = tm.tactical_anchor[0] * 0.55 + tm.pos[0] * 0.45
                    anchor_y = tm.tactical_anchor[1] * 0.70 + tm.pos[1] * 0.30
                    if distance((anchor_x, anchor_y), self.pos) < 34.0:
                        raw_targets.append((pitch.clamp(anchor_x, anchor_y), 0.78 * support_weight))

            if carrier_progress > 0.80 and not tm.is_defender:
                side_sign = 1.0 if tm.tactical_anchor[1] >= config.pitch_width / 2.0 else -1.0
                layoff_targets = (
                    (self.pos[0] - forward_dir * 5.0, config.pitch_width / 2.0, 0.76),
                    (self.pos[0] - forward_dir * 7.0, self.pos[1] + side_sign * 5.0, 0.70),
                    (self.pos[0] - forward_dir * 9.0, tm.tactical_anchor[1] * 0.45 + config.pitch_width / 2.0 * 0.55, 0.66),
                )
                for lx, ly, arrival in layoff_targets:
                    target = pitch.clamp(lx, ly)
                    if distance(target, tm.pos) < 34.0:
                        raw_targets.append((target, arrival))

            tm_base = getattr(tm, "base_formation_pos", tm.tactical_anchor)
            tm_base_progress = tm_base[0] / config.pitch_length if attacking_right else (config.pitch_length - tm_base[0]) / config.pitch_length
            second_line_role = (
                0.42 <= tm_base_progress <= 0.68
                and not tm.is_defender
                and tm_progress_hint > 0.60
            )
            if carrier_progress > 0.68 and second_line_role:
                goal_side_x = config.pitch_length if attacking_right else 0.0
                arc_x = goal_side_x - forward_dir * 24.0
                support_x = (
                    tm.tactical_anchor[0] * 0.42
                    + tm.target_pos[0] * 0.26
                    + arc_x * 0.32
                )
                support_y = (
                    tm.tactical_anchor[1] * 0.40
                    + tm.target_pos[1] * 0.20
                    + config.pitch_width / 2.0 * 0.40
                )
                support_target = pitch.clamp(support_x, support_y)
                if distance(support_target, tm.pos) < 30.0:
                    raw_targets.append((support_target, 0.72))

            carrier_width = abs(self.pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
            if carrier_progress > 0.68 and carrier_width > 0.34 and not tm.is_defender:
                target_role_progress = tm.tactical_anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
                if target_role_progress > 0.54:
                    goal_side_x = config.pitch_length if attacking_right else 0.0
                    box_edge_x = goal_side_x - forward_dir * 15.5
                    cutback_x = min(box_edge_x, self.pos[0] + forward_dir * 7.0) if attacking_right else max(box_edge_x, self.pos[0] + forward_dir * 7.0)
                    near_box_x = goal_side_x - forward_dir * 12.0
                    center_y = config.pitch_width / 2.0
                    carrier_side = 1.0 if self.pos[1] >= center_y else -1.0
                    delivery_targets = (
                        (cutback_x, center_y, 0.66),
                        (cutback_x, center_y + carrier_side * config.pitch_width * 0.10, 0.62),
                        (near_box_x, center_y, 0.54),
                        (near_box_x, center_y + carrier_side * config.pitch_width * 0.12, 0.50),
                    )
                    for tx, ty, arrival in delivery_targets:
                        target = pitch.clamp(tx, ty)
                        if distance(target, tm.pos) < 32.0:
                            raw_targets.append((target, arrival))
                    runner_x = tm.pos[0] + (tm.target_pos[0] - tm.pos[0]) * 0.65
                    runner_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.65
                    runner_target = pitch.clamp(
                        runner_x,
                        runner_y + (center_y - runner_y) * 0.35,
                    )
                    if distance(runner_target, tm.pos) < 18.0:
                        raw_targets.append((runner_target, 0.74))

            # Delivery-space candidates. These are still generated from the
            # receiver's live movement/anchor and scored by the value model; the
            # sampler simply lets a wide/half-space passer see nearby receiving
            # lanes around an advanced runner instead of only the runner's feet.
            receiver_forward = max(
                0.0,
                (tm.tactical_anchor[0] - tm.pos[0]) * forward_dir,
                (tm.target_pos[0] - tm.pos[0]) * forward_dir,
            )
            carrier_progress = self.pos[0] / config.pitch_length if attacking_right else (config.pitch_length - self.pos[0]) / config.pitch_length
            target_progress_hint = tm.tactical_anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
            delivery_pressure = max(carrier_progress, target_progress_hint)
            central_pull = config.pitch_width / 2.0 - tm.pos[1]
            if delivery_pressure > 0.70 and (receiver_forward > 0.5 or target_progress_hint > 0.76):
                for depth_scale, center_scale, arrival_base in (
                    (0.45, 0.35, 0.74),
                    (0.75, 0.55, 0.66),
                    (1.05, 0.72, 0.58),
                ):
                    run_depth = 3.0 + min(12.0, receiver_forward + 6.0) * depth_scale
                    raw_targets.append((
                        pitch.clamp(
                            tm.pos[0] + forward_dir * run_depth,
                            tm.pos[1] + central_pull * center_scale,
                        ),
                        arrival_base,
                    ))
                if carrier_progress > 0.82 and abs(self.pos[1] - config.pitch_width / 2.0) > config.pitch_width * 0.14:
                    for depth_scale, center_scale, arrival_base in (
                        (0.20, 0.58, 0.70),
                        (-0.15, 0.70, 0.64),
                    ):
                        support_depth = min(9.0, receiver_forward + 4.0) * depth_scale
                        target_x = tm.pos[0] + forward_dir * support_depth
                        target_x = min(target_x, self.pos[0] - 0.5) if attacking_right else max(target_x, self.pos[0] + 0.5)
                        raw_targets.append((
                            pitch.clamp(
                                target_x,
                                tm.pos[1] + central_pull * center_scale,
                            ),
                            arrival_base,
                        ))

            # Sample pass targets from the local attacking value field around
            # the receiver instead of hard-coded tactical spots. The fixed
            # offsets are only a generic radial sampler; position_value decides
            # which spaces are useful.
            spatial_candidates = []
            tm_anchor_progress = tm.tactical_anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
            tm_anchor_progress = max(0.0, min(1.0, tm_anchor_progress))
            tm_width_factor = min(1.0, abs(tm.tactical_anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
            search_radius = 6.0 + 10.0 * tm_anchor_progress + 3.0 * tm_width_factor
            sample_angles = (-150, -105, -60, -25, 0, 25, 60, 105, 150)
            sample_radii = (search_radius * 0.55, search_radius)
            for center in (tm.pos, tm.target_pos, tm.tactical_anchor):
                for radius in sample_radii:
                    for angle_deg in sample_angles:
                        angle = math.radians(angle_deg)
                        ax = math.cos(angle) * radius * forward_dir
                        ay = math.sin(angle) * radius
                        pos = pitch.clamp(center[0] + ax, center[1] + ay)
                        if self._is_offside_position(pos, attacking_right, offside_line, config, ball_x=self.pos[0]):
                            continue
                        d_from_receiver = distance(pos, tm.pos)
                        if d_from_receiver > search_radius * 1.50:
                            continue
                        pv = position_value(
                            pos[0], pos[1], pitch, attacking_right,
                            opp_positions, tm_positions, config,
                            runner_formation_pos=tm.tactical_anchor,
                        )
                        receiver_arrival = max(0.25, 1.0 - d_from_receiver / (search_radius * 1.65))
                        spatial_candidates.append((pv * receiver_arrival, pos, receiver_arrival))

            # Team-front value-field samples: when the dynamic anchors form an
            # advanced line, sample around that line so passes into the box can
            # emerge from team shape rather than fixed tactical coordinates.
            if front_center is not None and tm_anchor_progress > 0.50:
                for angle_deg in (-60, -25, 0, 25, 60):
                    angle = math.radians(angle_deg)
                    radius = search_radius * 0.85
                    pos = pitch.clamp(
                        front_center[0] + math.cos(angle) * radius * forward_dir,
                        front_center[1] + math.sin(angle) * radius,
                    )
                    if self._is_offside_position(pos, attacking_right, offside_line, config, ball_x=self.pos[0]):
                        continue
                    d_from_receiver = distance(pos, tm.pos)
                    pv = position_value(
                        pos[0], pos[1], pitch, attacking_right,
                        opp_positions, tm_positions, config,
                        runner_formation_pos=tm.tactical_anchor,
                    )
                    receiver_arrival = max(0.22, 1.0 - d_from_receiver / (search_radius * 1.90))
                    spatial_candidates.append((pv * receiver_arrival, pos, receiver_arrival))

            spatial_candidates.sort(key=lambda item: item[0], reverse=True)
            for _, pos, receiver_arrival in spatial_candidates[:3]:
                raw_targets.append((pos, receiver_arrival))

            for target, receiver_arrival in raw_targets:
                d = distance(self.pos, target)
                if d < 3.0 or d > 55.0:
                    continue

                if self._is_offside_position(target, attacking_right, offside_line, config, ball_x=self.pos[0]):
                    receiver_arrival *= 0.25
                tm_speed = player_speed(tm.speed_value, config.player_max_speed, config.player_min_speed)
                receiver_time = distance(tm.pos, target) / max(0.1, tm_speed)
                defender_time = float("inf")
                for opp in opponents:
                    opp_speed = player_speed(opp.speed_value, config.player_max_speed, config.player_min_speed)
                    if opp.is_goalkeeper:
                        # Keepers cover near-goal space aggressively but should
                        # not dominate ordinary outfield passing lanes.
                        goal_x = config.pitch_length if attacking_right else 0.0
                        goal_dist = abs(target[0] - goal_x)
                        if goal_dist > 24.0:
                            continue
                        opp_speed *= 1.18
                    defender_time = min(defender_time, distance(opp.pos, target) / max(0.1, opp_speed))
                arrival_margin = defender_time - receiver_time
                if arrival_margin < 0.0:
                    receiver_arrival *= max(0.10, 1.0 + arrival_margin / 3.5)
                else:
                    receiver_arrival *= 0.78 + 0.22 * min(1.0, arrival_margin / 4.0)
                target_progress_for_risk = (
                    target[0] / max(1.0, pitch.length)
                    if attacking_right
                    else (pitch.length - target[0]) / max(1.0, pitch.length)
                )
                target_centrality_for_risk = 1.0 - min(
                    1.0,
                    abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0),
                )
                box_space_pressure = (
                    _smoothstep(0.78, 0.90, target_progress_for_risk)
                    * _smoothstep(0.45, 0.85, target_centrality_for_risk)
                    * _smoothstep(4.0, 16.0, distance(tm.pos, target))
                )
                if box_space_pressure > 0.0:
                    required_margin = 0.8 + 1.8 * box_space_pressure
                    margin_factor = max(0.24, min(1.0, (arrival_margin + 1.2) / required_margin))
                    receiver_arrival *= 1.0 - box_space_pressure * (1.0 - margin_factor)

                is_long = d > 30.0
                passing = self.abilities.get("Long_Passing" if is_long else "Short_Passing", 50) / 100.0
                base = config.long_pass_base_success if is_long else config.short_pass_base_success
                dist_factor = max(0.35, 1.0 - max(0.0, d - 10.0) / 65.0)
                base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor

                continuity = 0.075 if distance(target, tm.pos) <= 4.0 else 0.045
                value = evaluate_pass_target(
                    self, tm, self.pos, target,
                    teammates, opponents, config, pitch, attacking_right,
                    current_state_value, base_accuracy,
                    receiver_arrival=receiver_arrival,
                    continuity=continuity,
                )
                score = value.score
                success_prob = value.success_prob
                lane_risk = value.components["lane_risk"]
                consequence = value.components["turnover_consequence"]

                if score <= 0.0:
                    continue

                pass_type = "long_pass" if is_long else "short_pass"
                action_type = "pass_to_space" if distance(target, tm.pos) > 4.0 else "pass"
                details = {
                    "target": target,
                    "success_prob": success_prob,
                    "lane_risk": lane_risk,
                    "turnover_consequence": consequence,
                    "current_value": value.current_value,
                    "after_value": value.after_value,
                    "risk_cost": value.risk_cost,
                    "is_long": is_long,
                    "pass_type": pass_type,
                    "components": {
                        **value.components,
                        "distance": d,
                        "target_kind": "space" if distance(target, tm.pos) > 4.0 else "feet",
                    },
                }
                if second_line_role:
                    target_progress_for_marker = target[0] / config.pitch_length if attacking_right else (config.pitch_length - target[0]) / config.pitch_length
                    target_centrality_for_marker = 1.0 - min(
                        1.0,
                        abs(target[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0),
                    )
                    if (
                        carrier_progress > 0.68
                        and 0.70 <= target_progress_for_marker <= 0.84
                        and target_centrality_for_marker > 0.58
                    ):
                        details["components"]["second_line_arc_candidate"] = (
                            min(1.0, (target_progress_for_marker - 0.70) / 0.14)
                            * target_centrality_for_marker
                        )
                if action_type == "pass_to_space":
                    details["intended_receiver"] = tm.index
                else:
                    details["target_player_idx"] = tm.index

                results.append((score, action_type, details))

        return results

    def _current_state_value(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> float:
        from .value_model import state_value
        return state_value(
            self.pos, self, teammates, opponents, config, pitch, attacking_right
        )

    def _score_pass_options(
        self,
        teammates: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opponents: List["Player"],
        opp_positions: List[Tuple[float, float]],
        tm_positions: List[Tuple[float, float]],
        current_state_value: float,
    ) -> List[Tuple[float, str, dict]]:
        """Score pass candidates: pass_success_prob * position_value(target).

        pass_success = f(Passing ability, distance, lane clarity)
        """
        from .position_value import position_value

        results = []
        passing_ability = self.abilities.get("Short_Passing", 50)
        long_passing = self.abilities.get("Long_Passing", 50)

        # Compute offside line for pass evaluation
        offside_line = self._get_offside_line(opponents, attacking_right, config)

        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue

            d = distance(self.pos, tm.pos)
            if d < 3.0 or d > 55.0:
                continue

            # Pass success rate = f(Passing, distance, lane clarity)
            is_long = d > 30.0
            if is_long:
                ability = long_passing / 100.0
                base_success = config.long_pass_base_success
            else:
                ability = passing_ability / 100.0
                base_success = config.short_pass_base_success

            # Distance factor
            dist_factor = max(0.4, 1.0 - (d - 10.0) / 60.0)

            # Lane clarity: check if opponents are on the pass path
            lane_clarity = 1.0
            dx = tm.pos[0] - self.pos[0]
            dy = tm.pos[1] - self.pos[1]
            pass_len = math.sqrt(dx * dx + dy * dy)
            if pass_len > 1.0:
                nx, ny = dx / pass_len, dy / pass_len
                for opp in opponents:
                    if opp.is_goalkeeper:
                        continue
                    px = opp.pos[0] - self.pos[0]
                    py = opp.pos[1] - self.pos[1]
                    proj = px * nx + py * ny
                    if 2.0 < proj < pass_len - 2.0:
                        perp = abs(px * ny - py * nx)
                        if perp < config.interception_reach * 1.5:
                            lane_clarity *= 0.6

            success_rate = base_success * (0.4 + 0.6 * ability) * dist_factor * lane_clarity
            success_rate = max(0.1, min(0.95, success_rate))

            from .value_model import expected_pass_value
            forward_dir = 1.0 if attacking_right else -1.0
            pass_progress = (tm.pos[0] - self.pos[0]) * forward_dir
            continuity = 0.04 if pass_progress >= 0 else 0.015
            score, success_rate, lane_risk, consequence = expected_pass_value(
                self, tm, self.pos, tm.pos,
                teammates, opponents, config, pitch, attacking_right,
                current_state_value, success_rate, receiver_arrival=1.0,
                continuity=continuity,
            )

            # Opportunity cost near goal: not a pattern rule, but a stronger
            # penalty when the pass gives up a high-value shooting state.
            goal_x = config.pitch_length if attacking_right else 0.0
            dist_to_goal = distance(self.pos, (goal_x, config.pitch_width / 2.0))
            if dist_to_goal < 28.0:
                if pass_progress < -2.0:
                    score *= 0.22
                elif pass_progress < 3.0:
                    score *= 0.42
                if abs(self.pos[1] - config.pitch_width / 2.0) < 12.0 and tm.shots == 0:
                    score *= 0.75

            # Offside risk: passing to offside teammate will likely be called back
            # IQ determines how well passer perceives the offside situation
            if self._is_offside_position(tm.pos, attacking_right, offside_line, config, ball_x=self.pos[0]):
                iq_factor = self.iq_value / 100.0
                # IQ 100 -> score * 0.02, IQ 50 -> score * 0.08, IQ 0 -> score * 0.14
                score *= 0.14 - 0.12 * iq_factor

            pass_type = "long_pass" if is_long else "short_pass"
            results.append((score, "pass", {
                "target": tm.pos,
                "target_player_idx": tm.index,
                "success_prob": success_rate,
                "lane_risk": lane_risk,
                "turnover_consequence": consequence,
                "is_long": is_long,
                "pass_type": pass_type,
            }))

        return results

    def _score_pass_to_space_options(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opp_positions: List[Tuple[float, float]],
        tm_positions: List[Tuple[float, float]],
        current_state_value: float,
    ) -> List[Tuple[float, str, dict]]:
        """Generate pass-to-space candidates.

        For each teammate moving forward, project where they'll be in ~1 tick
        and score: PV(future_pos) * arrival_prob * pass_accuracy
        Avoids offside positions by checking against the 2nd-last defender.
        """
        from .position_value import position_value, receive_reachability

        results = []
        forward_dir = 1.0 if attacking_right else -1.0

        # Compute offside line
        offside_line = self._get_offside_line(opponents, attacking_right, config)

        # Opponent speeds for reachability calculation
        opp_speeds = [
            player_speed(o.speed_value, config.player_max_speed, config.player_min_speed)
            for o in opponents if not o.is_goalkeeper
        ]
        opp_pos_no_gk = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]

        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue

            # Check if teammate is moving forward (target_pos ahead of current pos)
            dx_movement = tm.target_pos[0] - tm.pos[0]
            is_moving_forward = (dx_movement * forward_dir) > 1.0

            if not is_moving_forward:
                continue

            # Project where they'll be in ~0.5 ticks (compromise between current and target)
            future_pos_x = tm.pos[0] + (tm.target_pos[0] - tm.pos[0]) * 0.5
            future_pos_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.5
            future_pos = pitch.clamp(future_pos_x, future_pos_y)

            # Skip if future position would be offside
            if self._is_offside_position(future_pos, attacking_right, offside_line, config, ball_x=self.pos[0]):
                continue

            # Arrival probability: can teammate reach before defenders?
            tm_speed = player_speed(tm.speed_value, config.player_max_speed, config.player_min_speed)
            arrival_prob = receive_reachability(
                future_pos, tm.pos, tm_speed,
                opp_pos_no_gk, opp_speeds,
                self.pos, config.pass_to_space_ball_speed, config
            )

            # Pass accuracy based on distance and Long_Passing ability
            d = distance(self.pos, future_pos)
            if d < 3.0 or d > 55.0:
                continue

            long_passing = self.abilities.get("Long_Passing", 50) / 100.0
            pass_acc = max(0.3, min(0.9, 0.5 + 0.4 * long_passing - d / 100.0))

            # Pass feasibility: check lane clarity to future_pos
            lane_clarity = 1.0
            dx = future_pos[0] - self.pos[0]
            dy = future_pos[1] - self.pos[1]
            pass_len = math.sqrt(dx * dx + dy * dy)
            if pass_len > 1.0:
                nx, ny = dx / pass_len, dy / pass_len
                for opp in opponents:
                    if opp.is_goalkeeper:
                        continue
                    px = opp.pos[0] - self.pos[0]
                    py = opp.pos[1] - self.pos[1]
                    proj = px * nx + py * ny
                    if 2.0 < proj < pass_len - 2.0:
                        perp = abs(px * ny - py * nx)
                        if perp < config.interception_reach * 2.0:
                            lane_clarity *= 0.5

            from .value_model import expected_pass_value
            score, success_prob, lane_risk, consequence = expected_pass_value(
                self, tm, self.pos, future_pos,
                teammates, opponents, config, pitch, attacking_right,
                current_state_value, pass_acc * lane_clarity,
                receiver_arrival=arrival_prob,
                continuity=0.03,
            )

            is_long = d > 30.0
            results.append((score, "pass_to_space", {
                "target": future_pos,
                "intended_receiver": tm.index,
                "success_prob": success_prob,
                "lane_risk": lane_risk,
                "turnover_consequence": consequence,
                "is_long": is_long,
                "pass_type": "long_pass" if is_long else "short_pass",
            }))

        return results

    def _get_offside_line(
        self, opponents: List["Player"], attacking_right: bool, config: "EngineConfig"
    ) -> float:
        """Get the offside line (2nd-last defender position).

        For attacking right: offside line = 2nd-highest x among opponent outfield.
        For attacking left: offside line = 2nd-lowest x among opponent outfield.
        """
        if attacking_right:
            # Opponent defends near x=pitch_length. 2nd-highest x = 2nd-last defender.
            def_xs = sorted(
                [p.pos[0] for p in opponents if not p.is_goalkeeper],
                reverse=True  # descending: highest x first
            )
            return def_xs[1] if len(def_xs) >= 2 else def_xs[0] if def_xs else config.pitch_length
        else:
            # Opponent defends near x=0. 2nd-lowest x = 2nd-last defender.
            def_xs = sorted(
                [p.pos[0] for p in opponents if not p.is_goalkeeper],
                reverse=False  # ascending: lowest x first
            )
            return def_xs[1] if len(def_xs) >= 2 else def_xs[0] if def_xs else 0.0

    def _is_offside_position(
        self, pos: Tuple[float, float], attacking_right: bool,
        offside_line: float, config: "EngineConfig", ball_x: float = None
    ) -> bool:
        """Check if a position would be offside (used for pass-to-space filtering)."""
        if attacking_right:
            # Must be in opponent half AND ahead of offside line AND ahead of ball
            if pos[0] <= config.pitch_length / 2.0:
                return False
            if ball_x is not None and pos[0] <= ball_x:
                return False
            return pos[0] > offside_line
        else:
            if pos[0] >= config.pitch_length / 2.0:
                return False
            if ball_x is not None and pos[0] >= ball_x:
                return False
            return pos[0] < offside_line

    def _score_shoot(
        self,
        goal_center: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        opponents: List["Player"],
        dist_to_goal: float,
        current_state_value: float = 0.0,
        teammates: List["Player"] = None,
        attacking_right: bool = None,
    ) -> Tuple[float, dict]:
        """Score shoot candidate.

        score = on_target_prob * (1 - gk_save_estimate) * goal_reward_constant
        """
        from .physics import angle_to_goal

        finishing = self.abilities.get("Finishing", 50) / 100.0
        long_shot = self.abilities.get("Long_Shot", 50) / 100.0

        if dist_to_goal > 25.0:
            ability = long_shot
        elif dist_to_goal > 18.0:
            ability = (finishing + long_shot) / 2.0
        else:
            ability = finishing

        # Distance factor. Medium/long-range shots can still be chosen, but
        # their expected-goal value must decay more like real football.
        if dist_to_goal <= config.shot_ideal_distance:
            dist_factor = 1.0
        elif dist_to_goal <= 30.0:
            excess = dist_to_goal - config.shot_ideal_distance
            dist_factor = max(0.18, 1.0 - excess * 0.070)
        else:
            dist_factor = 0.45 * math.exp(-(dist_to_goal - 30.0) / 14.0)

        # Angle factor
        angle = angle_to_goal(self.pos, goal_center, config.goal_width)
        angle_factor = min(1.0, angle / 0.2)  # easier threshold for angle

        # Defensive pressure: nearby defenders and defenders in the shooting
        # lane reduce shot quality. This lets good defensive positioning matter
        # without requiring every defensive action to become a tackle.
        pressure_factor = 1.0
        lane_factor = 1.0
        sx, sy = self.pos
        gx, gy = goal_center
        shot_dx = gx - sx
        shot_dy = gy - sy
        shot_len = math.sqrt(shot_dx * shot_dx + shot_dy * shot_dy)
        if shot_len > 1.0:
            nx, ny = shot_dx / shot_len, shot_dy / shot_len
            for opp in opponents:
                if opp.is_goalkeeper:
                    continue
                d = distance(self.pos, opp.pos)
                if d < 8.0:
                    pressure_factor *= max(0.72, 1.0 - (8.0 - d) * 0.035)

                ox = opp.pos[0] - sx
                oy = opp.pos[1] - sy
                proj = ox * nx + oy * ny
                if 1.0 < proj < shot_len - 1.0:
                    perp = abs(ox * ny - oy * nx)
                    if perp < 4.5:
                        lane_factor *= max(0.65, 1.0 - (4.5 - perp) * 0.05)

        from .value_model import evaluate_shot
        value = evaluate_shot(
            self, goal_center, config, opponents, dist_to_goal,
            angle_factor, pressure_factor, lane_factor, dist_factor,
            current_state_value,
            teammates=teammates,
            pitch=pitch,
            attacking_right=attacking_right,
        )

        return (value.score, {
            "target": goal_center,
            "success_prob": value.success_prob,
            "on_target_prob": value.success_prob,
            "xg": value.after_value,
            "after_value": value.after_value,
            "risk_cost": value.risk_cost,
            "components": value.components,
        })

    def _score_clear(self, x_progress: float, pressure: int, config: "EngineConfig") -> float:
        """Score clearance from danger and pressure as an opportunity tradeoff."""
        return self._score_clear_value(x_progress, pressure, config).score

    def _score_clear_value(self, x_progress: float, pressure: int, config: "EngineConfig"):
        from .value_model import evaluate_clear
        return evaluate_clear(x_progress, pressure, config)

    def _gk_choose(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[str, dict]:
        """Goalkeeper distribution uses the same pass-to-point model."""
        current_state_value = self._current_state_value(
            teammates, opponents, config, pitch, attacking_right
        )
        candidates = self._score_pass_point_options(
            teammates, opponents, config, pitch, attacking_right,
            [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper],
            [(t.pos[0], t.pos[1]) for t in teammates if t.index != self.index],
            current_state_value,
        )
        if candidates:
            chosen = self._softmax_select(candidates, config)
            return (chosen[1], chosen[2])

        from .value_model import evaluate_pass_target
        fallback = []
        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue
            target = tm.pos
            d = distance(self.pos, target)
            if d < 4.0 or d > 70.0:
                continue
            is_long = d > 32.0
            passing = self.abilities.get("Long_Passing" if is_long else "Short_Passing", 50) / 100.0
            base = config.long_pass_base_success if is_long else config.short_pass_base_success
            dist_factor = max(0.30, 1.0 - max(0.0, d - 10.0) / 72.0)
            base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor
            value = evaluate_pass_target(
                self,
                tm,
                self.pos,
                target,
                teammates,
                opponents,
                config,
                pitch,
                attacking_right,
                current_state_value,
                base_accuracy,
                receiver_arrival=1.0,
                continuity=0.055,
            )
            components = dict(value.components)
            safety = value.success_prob * (1.0 - components.get("receiver_pressure", 0.0)) * (1.0 - components.get("lane_risk", 0.0))
            rank = value.score + value.after_value * 0.12 + safety * 0.040 - value.risk_cost * 0.20
            fallback.append((rank, value, tm, target, is_long))
        if fallback:
            _, value, tm, target, is_long = max(fallback, key=lambda item: item[0])
            return ("pass", {
                "target": target,
                "target_player_idx": tm.index,
                "success_prob": value.success_prob,
                "lane_risk": value.components.get("lane_risk", 0.0),
                "turnover_consequence": value.components.get("turnover_consequence", 0.0),
                "current_value": value.current_value,
                "after_value": value.after_value,
                "risk_cost": value.risk_cost,
                "is_long": is_long,
                "pass_type": "long_pass" if is_long else "short_pass",
                "components": {**value.components, "target_kind": "feet", "gk_fallback": True},
            })

        forward_x = config.pitch_length * (0.55 if attacking_right else 0.45)
        target = pitch.clamp(forward_x, config.pitch_width / 2)
        return ("pass", {"target": target, "target_player_idx": -1, "success_prob": 0.35, "is_long": True, "pass_type": "long_pass"})

    # =========================================================================
    # Off-Ball Attacking Decision: Pure Reward
    # =========================================================================

    def choose_off_ball_attack(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        ball_carrier: Optional["Player"] = None,
        opponents: Optional[List["Player"]] = None,
        teammates: Optional[List["Player"]] = None,
        tick: int = 0,
        team_side: str = "",
        trace=None,
    ) -> Tuple[float, float]:
        """Choose target position for off-ball attacking movement.

        Samples 6-8 structured candidate positions (3 forward, 2 wide, 1 back, 2 diagonal).
        Each scored: PV(pos) * reachability * pass_feasibility * space_creation
        Also: "stay" option with score = position_value(current_pos)

        Returns the chosen target position.
        """
        from .position_value import position_value, receive_reachability, space_creation_value

        if opponents is None:
            opponents = []
        if teammates is None:
            teammates = []
        anchor = self.tactical_anchor
        if self.current_goal and self.current_goal.goal_type not in (
            "arc_arrival_for_cutback",
            "attack_far_post",
        ):
            self.current_goal = None

        # GK: stay near formation position
        if self.is_goalkeeper:
            self.set_movement_target(anchor, "recover_shape")
            return self.target_pos

        opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
        tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != self.index]

        max_speed = player_speed(self.speed_value, config.player_max_speed, config.player_min_speed)
        forward_dir = 1.0 if attacking_right else -1.0

        # Compute offside line to avoid running into offside
        offside_line = self._get_offside_line(opponents, attacking_right, config)

        # Opponent speeds for reachability
        opp_speeds = [
            player_speed(o.speed_value, config.player_max_speed, config.player_min_speed)
            for o in opponents if not o.is_goalkeeper
        ]

        candidates = []  # (score, position, components)

        # "Stay" is only an inertia option. It should not claim the full value
        # of the current location, otherwise players keep old positions instead
        # of making valuable support runs.
        stay_pv = position_value(
            self.pos[0], self.pos[1], pitch, attacking_right,
            opp_positions, tm_positions, config,
            runner_formation_pos=anchor,
        )
        # Apply offside penalty to stay option (soft, allows offside trap runs)
        if self._is_offside_position(self.pos, attacking_right, offside_line, config, ball_x=ball_pos[0]):
            stay_pv *= 0.15
        stay_score = stay_pv * 0.18
        candidates.append((stay_score, self.pos, {"kind": "stay"}))

        role_progress = anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - anchor[0]) / config.pitch_length
        role_progress = max(0.0, min(1.0, role_progress))
        width_signed = (anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
        width_factor = min(1.0, abs(width_signed))
        search_radius = 10.0 + 16.0 * role_progress
        raw_candidates = []
        off_ball_goal_trace = None

        # Spatial samples around the dynamic role anchor.
        raw_candidates.append((anchor[0], anchor[1], anchor))
        # A forward-biased anchor sample lets the dynamic formation field create
        # runs naturally when the anchor itself moves beyond the ball.
        anchor_progress = (anchor[0] - ball_pos[0]) * forward_dir
        if anchor_progress > 0.0:
            raw_candidates.append((
                anchor[0] + forward_dir * min(10.0, anchor_progress * 0.45),
                anchor[1],
                anchor,
            ))
        for _ in range(8):
            angle = random.random() * math.tau
            radius = random.random() ** 0.65 * search_radius
            raw_candidates.append((
                anchor[0] + math.cos(angle) * radius,
                anchor[1] + math.sin(angle) * radius,
                anchor,
            ))

        # Spatial samples around useful support spaces near the ball carrier.
        if ball_carrier is not None:
            if getattr(config, "goal_continuity_enabled", False):
                from .goal import (
                    GoalSwitchContext,
                    evaluate_arc_arrival_for_cutback_goal,
                    evaluate_attack_far_post_goal,
                    select_goal,
                )

                off_ball_goal_candidates = []
                for goal in (
                    evaluate_arc_arrival_for_cutback_goal(
                        player_pos=self.pos,
                        anchor_pos=anchor,
                        ball_pos=ball_pos,
                        attacking_right=attacking_right,
                        pitch_length=pitch.length,
                        pitch_width=pitch.width,
                        tick=0,
                        base_pos=getattr(self, "base_formation_pos", anchor),
                    ),
                    evaluate_attack_far_post_goal(
                        player_pos=self.pos,
                        anchor_pos=anchor,
                        ball_pos=ball_pos,
                        attacking_right=attacking_right,
                        pitch_length=pitch.length,
                        pitch_width=pitch.width,
                        tick=0,
                    ),
                ):
                    if goal is not None:
                        off_ball_goal_candidates.append(goal)

                if off_ball_goal_candidates:
                    candidate_goal = max(off_ball_goal_candidates, key=lambda goal: goal.value)
                    selection = select_goal(
                        self.current_goal,
                        candidate_goal,
                        GoalSwitchContext(iq=self.iq_value),
                    )
                    self.current_goal = selection.goal
                    off_ball_goal_trace = selection.to_dict()
                    if selection.goal.goal_type in ("arc_arrival_for_cutback", "attack_far_post"):
                        raw_candidates.append((
                            selection.goal.target_pos[0],
                            selection.goal.target_pos[1],
                            selection.goal.target_pos,
                        ))
            # Low-depth roles are the rest-defense layer. They should still
            # support possession, but their candidate field should stay mostly
            # around the tactical anchor instead of being pulled near the ball.
            # This is based on role depth and space, not a position-name rule.
            support_pull = _smoothstep(0.38, 0.64, role_progress)
            support_depth = (role_progress - 0.46) * 34.0
            ball_support_x = ball_pos[0] + forward_dir * support_depth
            ball_support_y = ball_pos[1] * (1.0 - 0.30 * width_factor) + anchor[1] * (0.30 * width_factor)
            support_center = (
                anchor[0] * (1.0 - support_pull) + ball_support_x * support_pull,
                anchor[1] * (1.0 - support_pull) + ball_support_y * support_pull,
            )
            for _ in range(5):
                angle = random.random() * math.tau
                radius = random.random() ** 0.7 * (7.0 + 15.0 * role_progress)
                raw_candidates.append((
                    support_center[0] + math.cos(angle) * radius,
                    support_center[1] + math.sin(angle) * radius,
                    (
                        anchor[0] * 0.35 + support_center[0] * 0.65,
                        anchor[1] * 0.50 + support_center[1] * 0.50,
                    ),
                ))

            ball_progress = ball_pos[0] / config.pitch_length if attacking_right else (config.pitch_length - ball_pos[0]) / config.pitch_length
            if ball_progress > 0.68 and not self.is_defender:
                # When the ball is already high, support value often comes from
                # short angles around the carrier: cut-backs, lay-offs, and
                # half-space outlets. This is spatial support, not a role script.
                side_sign = 1.0 if anchor[1] >= config.pitch_width / 2.0 else -1.0
                width_signed = (anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
                weak_side = max(0.0, min(1.0, -width_signed * ((ball_pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))))
                support_centers = (
                    (
                        support_center[0] * 0.55 + ball_pos[0] * 0.45,
                        support_center[1] * 0.55 + ball_pos[1] * 0.45,
                    ),
                    (
                        anchor[0] * 0.35 + ball_pos[0] * 0.65,
                        anchor[1] * 0.45 + ball_pos[1] * 0.55,
                    ),
                )
                angle_bias = math.atan2(config.pitch_width / 2.0 - ball_pos[1], 10.0)
                support_angles = (
                    angle_bias - 1.65,
                    angle_bias - 0.95,
                    angle_bias - 0.35,
                    angle_bias,
                    angle_bias + 0.35,
                    angle_bias + 0.95,
                    angle_bias + 1.65,
                )
                support_radii = (
                    6.0,
                    10.0 + 3.0 * _smoothstep(0.72, 0.88, ball_progress),
                    15.0 + 5.0 * _smoothstep(0.70, 0.90, ball_progress),
                )
                for center_x, center_y in support_centers:
                    for radius in support_radii:
                        for angle in support_angles:
                            sx = center_x - forward_dir * math.cos(angle) * radius
                            sy = center_y + math.sin(angle) * radius
                            raw_candidates.append((sx, sy, (sx, sy)))
                if width_factor > 0.38 and role_progress > 0.58:
                    arrival_t = max(0.0, min(1.0, (ball_progress - 0.68) / 0.20))
                    arrival_depth = 6.0 + 7.0 * arrival_t
                    center_lane = config.pitch_width / 2.0
                    half_space = center_lane + side_sign * config.pitch_width * (0.06 + 0.06 * (1.0 - weak_side))
                    central_arrival_x = ball_pos[0] - forward_dir * arrival_depth
                    for sy in (half_space, center_lane):
                        raw_candidates.append((
                            central_arrival_x,
                            sy,
                            (central_arrival_x, sy),
                        ))
                    if weak_side > 0.18:
                        far_post_x = ball_pos[0] + forward_dir * (2.0 + 4.0 * arrival_t)
                        far_post_y = center_lane + side_sign * config.pitch_width * 0.08
                        raw_candidates.append((
                            far_post_x,
                            far_post_y,
                            (far_post_x, far_post_y),
                        ))
        for raw_x, raw_y, anchor_pos in raw_candidates:
            pos = pitch.clamp(raw_x, raw_y)

            # Position value (with role_distance_decay applied via runner_formation_pos)
            pv = position_value(
                pos[0], pos[1], pitch, attacking_right,
                opp_positions, tm_positions, config,
                runner_formation_pos=anchor_pos,
            )

            # Movement reachability: off-ball runs are future intentions, not
            # immediate pass targets. Long valuable runs should be possible but
            # discounted by the time needed to arrive.
            move_dist = distance(pos, self.pos)
            candidate_progress = pos[0] / config.pitch_length if attacking_right else (config.pitch_length - pos[0]) / config.pitch_length
            carrier_progress_hint = ball_pos[0] / config.pitch_length if attacking_right else (config.pitch_length - ball_pos[0]) / config.pitch_length
            final_third_support_window = (
                max(0.0, min(1.0, (carrier_progress_hint - 0.68) / 0.22))
                * max(0.0, min(1.0, (candidate_progress - 0.66) / 0.18))
            )
            movement_window = max_speed * (4.0 + 3.0 * role_progress + 4.6 * final_third_support_window)
            movement_reach = 1.0 / (1.0 + (move_dist / max(1.0, movement_window)) ** 1.45)

            # Immediate receive feasibility still matters, but it should not
            # erase a valuable run that can develop over the next few ticks.
            immediate_reach = receive_reachability(
                pos, self.pos, max_speed,
                opp_positions, opp_speeds,
                ball_pos, config.pass_to_space_ball_speed, config
            )
            reach = 0.35 + 0.45 * movement_reach + 0.20 * immediate_reach

            # Pass feasibility: can the ball reach me? (no defenders blocking path from ball)
            pass_feasibility = 1.0
            dx = pos[0] - ball_pos[0]
            dy = pos[1] - ball_pos[1]
            path_len = math.sqrt(dx * dx + dy * dy)
            if path_len > 1.0:
                nx, ny = dx / path_len, dy / path_len
                for opp in opponents:
                    if opp.is_goalkeeper:
                        continue
                    px = opp.pos[0] - ball_pos[0]
                    py = opp.pos[1] - ball_pos[1]
                    proj = px * nx + py * ny
                    if 2.0 < proj < path_len - 2.0:
                        perp = abs(px * ny - py * nx)
                        if perp < 4.0:
                            pass_feasibility *= 0.5

            # Reduce feasibility if too far from ball
            dist_to_ball = distance(pos, ball_pos)
            if dist_to_ball > 25.0:
                pass_feasibility *= max(0.1, 1.0 - (dist_to_ball - 25.0) / 35.0)

            # Space creation bonus
            space_bonus = space_creation_value(pos, opp_positions, tm_positions, config)
            role_dist = distance(pos, anchor)
            role_limit = 14.0 + 22.0 * role_progress
            role_t = min(1.0, role_dist / max(1.0, role_limit * 1.8))
            role_shape_factor = 0.22 + 0.78 * (1.0 - role_t * role_t * (3.0 - 2.0 * role_t))
            inside_support = 0.0
            if width_factor > 0.35:
                anchor_width = abs(anchor[1] - config.pitch_width / 2.0)
                pos_width = abs(pos[1] - config.pitch_width / 2.0)
                inside_support = (
                    max(0.0, min(1.0, (carrier_progress_hint - 0.68) / 0.22))
                    * max(0.0, min(1.0, (candidate_progress - 0.66) / 0.18))
                    * max(0.0, min(1.0, (anchor_width - pos_width) / max(1.0, anchor_width)))
                )
                role_shape_factor = max(role_shape_factor, 0.48 + 0.28 * inside_support)
            ahead_of_ball = (pos[0] - ball_pos[0]) * forward_dir
            ahead_t = max(0.0, min(1.0, ahead_of_ball / 18.0))
            support_run_factor = ahead_t * ahead_t * (3.0 - 2.0 * ahead_t)
            carrier_progress = ball_pos[0] / config.pitch_length if attacking_right else (config.pitch_length - ball_pos[0]) / config.pitch_length
            support_angle_dist = distance(pos, ball_pos)
            support_angle_value = (
                max(0.0, min(1.0, (carrier_progress - 0.68) / 0.22))
                * (1.0 - min(1.0, abs(pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)) * 0.35)
                * max(0.0, 1.0 - abs(support_angle_dist - 16.0) / 18.0)
            )
            cutback_depth = (ball_pos[0] - pos[0]) * forward_dir
            carrier_width = abs(ball_pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
            candidate_width = abs(pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
            second_line_support = (
                max(0.0, min(1.0, (carrier_progress - 0.66) / 0.20))
                * max(0.0, min(1.0, (candidate_progress - 0.60) / 0.14))
                * (1.0 - max(0.0, min(1.0, (candidate_progress - 0.82) / 0.10)))
                * max(0.0, min(1.0, (cutback_depth - 5.0) / 8.0))
                * (1.0 - max(0.0, min(1.0, (cutback_depth - 24.0) / 12.0)))
                * max(0.0, min(1.0, (carrier_width - candidate_width + 0.04) / 0.34))
                * (1.0 - candidate_width * 0.35)
            )
            layoff_window = (
                max(0.0, min(1.0, (carrier_progress - 0.70) / 0.18))
                * max(0.0, 1.0 - abs(support_angle_dist - 14.0) / 10.0)
                * (0.65 + 0.35 * (1.0 - min(1.0, abs(pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))))
            )
            if second_line_support > 0.0:
                role_shape_factor = max(role_shape_factor, 0.58 + 0.24 * second_line_support)

            role_overlap = 0.0
            for teammate in teammates:
                if teammate.index == self.index or teammate.is_goalkeeper:
                    continue
                teammate_anchor = getattr(teammate, "tactical_anchor", teammate.pos)
                anchor_dist = distance(pos, teammate_anchor)
                own_anchor_dist = distance(pos, anchor)
                if anchor_dist < 12.0 and anchor_dist + 2.0 < own_anchor_dist:
                    role_overlap += (1.0 - anchor_dist / 12.0) ** 1.15
                current_dist = distance(pos, teammate.pos)
                if current_dist < 8.0:
                    role_overlap += 0.45 * (1.0 - current_dist / 8.0)
            role_overlap_factor = 1.0 / (1.0 + role_overlap * 0.72)

            target_width_signed = (pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
            cross_lane = max(0.0, -width_signed * target_width_signed)
            lane_factor = max(0.12, 1.0 - 0.88 * width_factor * cross_lane)

            # Offside penalty: soft penalty (allows deliberate offside trap runs)
            offside_penalty = 1.0
            if self._is_offside_position(pos, attacking_right, offside_line, config, ball_x=ball_pos[0]):
                offside_penalty = 0.08
            else:
                # Softly discourage living right on the line; good timed runs
                # can still happen, but the default support shape stays onside.
                if attacking_right and pos[0] > offside_line - 3.0:
                    offside_penalty *= 0.45
                elif (not attacking_right) and pos[0] < offside_line + 3.0:
                    offside_penalty *= 0.45

            score = (
                pv * reach * pass_feasibility * space_bonus * offside_penalty
                * role_shape_factor * lane_factor * role_overlap_factor
                * (
                    1.0
                    + 0.18 * role_progress * support_run_factor
                    + 0.82 * support_angle_value
                    + 1.35 * layoff_window
                    + 0.70 * inside_support
                    + 1.45 * second_line_support
                )
            )
            components = {
                "kind": "space",
                "pv": pv,
                "reach": reach,
                "movement_reach": movement_reach,
                "immediate_reach": immediate_reach,
                "pass_feasibility": pass_feasibility,
                "space_bonus": space_bonus,
                "role_shape_factor": role_shape_factor,
                "role_overlap_factor": role_overlap_factor,
                "role_overlap": role_overlap,
                "lane_factor": lane_factor,
                "offside_penalty": offside_penalty,
                "support_angle_value": support_angle_value,
                "inside_support": inside_support,
                "second_line_support": second_line_support,
                "layoff_window": layoff_window,
                "candidate_progress": candidate_progress,
                "candidate_width": candidate_width,
                "support_angle_dist": support_angle_dist,
                "dist_to_ball": dist_to_ball,
            }
            candidates.append((score, pos, components))

        if not candidates:
            self.target_pos = anchor
            return self.target_pos

        # Apply IQ noise to all candidate scores
        noisy_candidates = [
            (self._apply_iq_noise(score, config), pos, components)
            for score, pos, components in candidates
        ]

        scores = [c[0] for c in noisy_candidates]
        max_score = max(scores)
        if max_score < 0.01:
            self.set_movement_target(anchor, "recover_shape")
            return self.target_pos

        min_score = min(scores)
        iq_noise = (100 - max(1, min(99, self.iq_value))) / 100.0
        score_spread = max(0.0, max_score - min_score)
        temperature = (0.004 + score_spread * 0.22) * (0.35 + iq_noise * 0.95)
        temperature = max(0.003, min(0.05, temperature))

        exp_scores = [math.exp((s - max_score) / temperature) for s in scores]
        total = sum(exp_scores)
        if total < 1e-10:
            chosen_pos = noisy_candidates[0][1]
        else:
            r = random.random() * total
            cumulative = 0.0
            chosen_pos = noisy_candidates[-1][1]
            for i, e in enumerate(exp_scores):
                cumulative += e
                if r <= cumulative:
                    chosen_pos = noisy_candidates[i][1]
                    break

        # Hard roam clamp removed: role_distance_decay in position_value provides
        # the soft pull toward formation area instead of a hard boundary.
        move_progress = (chosen_pos[0] - self.pos[0]) * forward_dir
        anchor_run = (anchor[0] - self.pos[0]) * forward_dir
        if move_progress > 4.0 or anchor_run > 6.0:
            intent = "attack_run"
        elif distance(chosen_pos, anchor) > 10.0:
            intent = "support"
        else:
            intent = "recover_shape"
        self.set_movement_target(chosen_pos, intent)
        if trace is not None and config.trace.should_trace(tick, self.index, "off_ball_attack"):
            ranked = sorted(noisy_candidates, key=lambda item: item[0], reverse=True)
            alternatives = [
                {
                    "phase": "off_ball_attack",
                    "action_type": "move",
                    "target": pos,
                    "value": {"score": score, "components": components},
                }
                for score, pos, components in ranked[1:max(1, int(config.trace.top_k))]
            ]
            chosen_components = next((components for _, pos, components in noisy_candidates if pos == chosen_pos), {})
            trace.log_decision(
                tick=tick,
                team=team_side,
                player_idx=self.index,
                player_name=self.name,
                phase="off_ball_attack",
                chosen={
                    "phase": "off_ball_attack",
                    "action_type": "move",
                    "target": chosen_pos,
                    "value": {"score": max_score, "components": chosen_components},
                },
                alternatives=alternatives,
                pos=self.pos,
                goal=off_ball_goal_trace,
            )
        return self.target_pos

    # =========================================================================
    # Off-Ball Defending Decision: Pure Reward (Zone-Based)
    # =========================================================================

    def choose_off_ball_defend(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        ball_carrier: Optional["Player"] = None,
        opponents: Optional[List["Player"]] = None,
        teammates: Optional[List["Player"]] = None,
    ) -> Tuple[str, dict]:
        """Choose defending action from defensive space-value candidates."""
        if opponents is None:
            opponents = []
        if teammates is None:
            teammates = []
        anchor = self.tactical_anchor

        # GK: position adjustment
        if self.is_goalkeeper:
            self._gk_position_adjust(ball_pos, config, pitch, attacking_right)
            return ("hold_position", {"target": self.target_pos})

        # Stunned players can't do anything
        if self.state == PlayerState.STUNNED:
            return ("hold_position", {"target": self.pos})

        dist_to_ball = distance(self.pos, ball_pos)
        own_goal_x = 0.0 if attacking_right else config.pitch_length
        own_goal = (own_goal_x, config.pitch_width / 2.0)
        ball_goal_dist = distance(ball_pos, own_goal)
        central_threat = 1.0 - min(1.0, abs(ball_pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
        shot_danger = max(0.0, 1.0 - ball_goal_dist / 32.0) * (0.55 + 0.45 * central_threat)
        carrier_stale_threat = 0.0
        if ball_carrier is not None:
            carrier_progress = ball_pos[0] / config.pitch_length if (not attacking_right) else (config.pitch_length - ball_pos[0]) / config.pitch_length
            carrier_stale_threat = (
                max(0.0, min(1.0, (ball_carrier.consecutive_carries - 1) / 3.0))
                * max(0.0, min(1.0, (carrier_progress - 0.62) / 0.24))
                * (0.55 + 0.45 * central_threat)
            )
        attackers = [o for o in opponents if not o.is_goalkeeper]
        teammates_no_gk = [t for t in teammates if t.index != self.index and not t.is_goalkeeper]
        attacker_positions = [(o.pos[0], o.pos[1]) for o in attackers]
        teammate_positions = [(t.pos[0], t.pos[1]) for t in teammates_no_gk]
        defenders_closer_to_ball = sum(
            1 for t in teammates_no_gk
            if distance(t.pos, ball_pos) < dist_to_ball - 1.0
        )
        close_defenders_near_ball = sum(
            1 for t in teammates_no_gk
            if distance(t.pos, ball_pos) < max(config.press_radius * 0.72, config.tackle_range)
        )
        nearest_def_dist = min(
            [distance(t.pos, ball_pos) for t in teammates_no_gk] + [dist_to_ball]
        )
        local_attackers = [
            o for o in attackers
            if distance(o.pos, anchor) < 24.0 or distance(o.pos, self.pos) < 16.0
        ]

        from .position_value import defensive_position_value

        def score_def_pos(pos: Tuple[float, float]) -> float:
            return defensive_position_value(
                pos, ball_pos, own_goal_x, pitch,
                attacker_positions, teammate_positions, anchor,
            )

        candidates = []

        # Defensive movement is now spatial: sample useful points, then classify
        # the chosen point for compatibility with trace/interactions.
        sampled_points = [
            anchor,
            pitch.clamp(
                anchor[0] * 0.85 + ball_pos[0] * 0.15,
                anchor[1] * 0.72 + ball_pos[1] * 0.28,
            ),
        ]

        if local_attackers:
            _, mark_target = self._score_mark_runner_zone(
                ball_pos, local_attackers, config, pitch, attacking_right
            )
            _, lane_target = self._score_block_lane_zone(
                ball_pos, local_attackers, config, pitch, attacking_right
            )
            sampled_points.extend([mark_target, lane_target])

        if ball_carrier:
            lead = config.carrier_speed * 0.45
            carrier_dir_x = 1.0 if attacking_right else -1.0
            sampled_points.append(pitch.clamp(ball_pos[0] + carrier_dir_x * lead, ball_pos[1]))
            # Containment ring around the carrier, biased goal-side.
            goal_side = -1.0 if attacking_right else 1.0
            contain_depth = 2.2 + 1.6 * carrier_stale_threat
            contain_width = 3.0 + 2.0 * carrier_stale_threat
            for oy in (-contain_width, 0.0, contain_width):
                sampled_points.append(pitch.clamp(ball_pos[0] + goal_side * contain_depth, ball_pos[1] + oy))

        # Local spatial samples around dynamic responsibility area.
        for _ in range(3):
            angle = random.random() * math.tau
            radius = random.random() ** 0.7 * (8.0 + shot_danger * 4.0)
            sampled_points.append(pitch.clamp(
                anchor[0] + math.cos(angle) * radius,
                anchor[1] + math.sin(angle) * radius,
            ))
        if self.last_def_action:
            sampled_points.append(self.last_def_target)

        seen = set()
        for point in sampled_points:
            key = (round(point[0], 1), round(point[1], 1))
            if key in seen:
                continue
            seen.add(key)

            base_score = score_def_pos(point)
            dist_point_ball = distance(point, ball_pos)
            press_value = max(0.0, 1.0 - dist_point_ball / max(config.press_radius, 0.1))
            cover_cost = min(0.75, defenders_closer_to_ball * 0.16 + len(local_attackers) * 0.08)
            nearest_gap = max(0.0, dist_to_ball - nearest_def_dist)
            first_presser_share = 1.0 / (1.0 + max(0, defenders_closer_to_ball) ** 1.55)
            swarm_cost = 1.0 / (1.0 + max(0, close_defenders_near_ball) * 0.72)
            distance_responsibility = max(0.08, 1.0 - nearest_gap / 10.0)
            pressure_responsibility = first_presser_share * swarm_cost * distance_responsibility
            distance_responsibility = max(0.25, 1.0 - max(0.0, dist_to_ball - nearest_def_dist) / 18.0)
            carrier_threat = 0.35 + 0.65 * max(shot_danger, carrier_stale_threat)
            press_reward = press_value * pressure_responsibility * distance_responsibility * carrier_threat
            score = base_score * (1.0 + press_reward * 1.75) * (1.0 - cover_cost * 0.28)
            if press_value > 0.35 and pressure_responsibility < 0.22:
                score *= 0.78 + pressure_responsibility

            if ball_carrier and distance(point, ball_carrier.pos) < config.tackle_range:
                score *= 1.0 + carrier_threat * pressure_responsibility * 0.75
            if self.last_def_action:
                stability_dist = distance(point, self.last_def_target)
                stability = max(0.0, 1.0 - stability_dist / 24.0)
                score *= 1.0 + stability * 0.90

            candidates.append((max(0.0, score), "defend_space", {"target": point}))

        if not candidates:
            self.set_movement_target(anchor, "defend_shape")
            return ("hold_position", {"target": anchor})

        # Apply IQ noise to all candidate scores
        noisy_candidates = [
            (self._apply_iq_noise(score, config), action_type, details)
            for score, action_type, details in candidates
        ]

        # Softmax select
        chosen = self._softmax_select(noisy_candidates, config)
        action_type = chosen[1]
        details = chosen[2]

        # Set target position based on choice
        raw_target = details.get("target", anchor)
        # Hard roam clamp removed: role_distance_decay in position_value provides
        # the soft pull toward formation area instead of a hard boundary.
        if self.last_def_action:
            smoothed_target = (
                self.last_def_target[0] * 0.75 + raw_target[0] * 0.25,
                self.last_def_target[1] * 0.75 + raw_target[1] * 0.25,
            )
        else:
            smoothed_target = raw_target

        # Classify chosen defensive point for compatibility.
        chosen_press_responsibility = 1.0 / (
            1.0 + max(0, defenders_closer_to_ball) ** 1.55 + max(0, close_defenders_near_ball) * 0.72
        )
        if (
            ball_carrier
            and dist_to_ball < config.tackle_range * (0.55 + shot_danger * 0.15)
            and distance(raw_target, ball_carrier.pos) < config.tackle_range * (0.75 + shot_danger * 0.15)
            and chosen_press_responsibility > 0.25
        ):
            action_type = "tackle"
        elif (
            ball_carrier
            and distance(raw_target, ball_carrier.pos) < config.press_radius
            and (
                chosen_press_responsibility > 0.18
                or shot_danger > 0.72
            )
        ):
            action_type = "approach"
        elif local_attackers and any(distance(raw_target, o.pos) < 5.0 for o in local_attackers):
            action_type = "mark_runner"
        elif local_attackers:
            action_type = "block_lane"
        else:
            action_type = "hold_position"

        if action_type == "approach":
            self.state = PlayerState.PRESSING
            intent = "press"
        elif action_type == "tackle":
            intent = "press"
        elif action_type == "mark_runner":
            intent = "mark"
        elif action_type == "block_lane":
            intent = "block_lane"
        elif self.state == PlayerState.PRESSING:
            self.state = PlayerState.OFF_BALL
            intent = "defend_shape"
        else:
            intent = "defend_shape"

        self.set_movement_target(smoothed_target, intent)
        self.last_def_target = self.target_pos
        self.last_def_action = action_type
        return (action_type, {"target": self.target_pos})

    def _score_tackle(self, ball_carrier: "Player", dist_to_ball: float, config: "EngineConfig") -> float:
        """Score for attempting a tackle.

        score = success_rate * ball_value - (1-success_rate) * stun_cost
        Only positive when very close + high Tackling.
        """
        tackling = self.abilities.get("Tackling", 50)
        dribbling = ball_carrier.abilities.get("Dribbling", 50)

        # Success rate based on Tackling vs Dribbling and distance.
        # Real tackling requires tight distance; at the edge, pressure is more
        # rational than committing a foot in.
        dist_factor = max(0.0, 1.0 - dist_to_ball / max(config.tackle_range * 0.9, 0.1))
        success_rate = (tackling / (tackling + dribbling + 1.0)) * dist_factor
        success_rate = max(0.0, min(0.75, success_rate))

        # Ball value: how valuable is winning the ball here
        ball_value = 1.8

        # Stun cost: penalty for being stunned
        stun_cost = 0.35

        score = success_rate * ball_value - (1.0 - success_rate) * stun_cost
        return max(0.0, score)

    def _score_mark_runner_zone(
        self,
        ball_pos: Tuple[float, float],
        attackers_in_zone: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[float, Tuple[float, float]]:
        """Score for marking the most threatening attacker in MY zone.

        Threat = based on proximity to ball and to our goal.
        """
        if not attackers_in_zone:
            return (0.0, self.tactical_anchor)

        # Pick the most threatening attacker in zone
        # Threat = proximity to ball * forward position
        best_threat = 0.0
        best_target = None
        for opp in attackers_in_zone:
            dist_to_ball = distance(opp.pos, ball_pos)
            ball_proximity = max(0.2, 1.0 - dist_to_ball / 30.0)

            # How advanced is this attacker (toward our goal)
            if attacking_right:
                # We're defending left goal (x=0). Attackers at low x are dangerous
                advance = 1.0 - opp.pos[0] / config.pitch_length
            else:
                # We're defending right goal. Attackers at high x are dangerous
                advance = opp.pos[0] / config.pitch_length

            threat = ball_proximity * 0.6 + advance * 0.4
            if threat > best_threat:
                best_threat = threat
                best_target = opp

        if best_target is None:
            return (0.0, self.tactical_anchor)

        # Mark position: slightly goalside of the attacker
        offset = 1.5
        if attacking_right:
            # Defending left goal (x=0), so goalside = lower x
            mark_x = best_target.pos[0] - offset
        else:
            # Defending right goal, goalside = higher x
            mark_x = best_target.pos[0] + offset
        mark_target = pitch.clamp(mark_x, best_target.pos[1])

        score = best_threat * 0.6  # marking is important
        return (score, mark_target)

    def _score_block_lane_zone(
        self,
        ball_pos: Tuple[float, float],
        attackers_in_zone: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[float, Tuple[float, float]]:
        """Score for blocking a passing lane to the most threatening attacker in zone.

        Position between ball and attacker in my zone.
        """
        if not attackers_in_zone:
            return (0.0, self.tactical_anchor)

        # Pick the closest attacker in zone to me
        target_opp = min(attackers_in_zone, key=lambda o: distance(self.pos, o.pos))

        # Position between ball and this opponent
        mid_x = (ball_pos[0] + target_opp.pos[0]) / 2.0
        mid_y = (ball_pos[1] + target_opp.pos[1]) / 2.0
        lane_target = pitch.clamp(mid_x, mid_y)

        # Threat level based on proximity of attacker to ball
        dist_opp_to_ball = distance(target_opp.pos, ball_pos)
        if dist_opp_to_ball > 40.0:
            threat = 0.2
        else:
            threat = max(0.2, 1.0 - dist_opp_to_ball / 40.0)

        score = threat * 0.5
        return (score, lane_target)

    def _score_block_lane(
        self,
        ball_pos: Tuple[float, float],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[float, Tuple[float, float]]:
        """Legacy: Score for blocking a passing lane."""
        dangerous = [o for o in opponents if not o.is_goalkeeper and distance(self.pos, o.pos) < 25.0]
        if not dangerous:
            return (0.0, self.tactical_anchor)
        target_opp = min(dangerous, key=lambda o: distance(self.pos, o.pos))
        mid_x = (ball_pos[0] + target_opp.pos[0]) / 2.0
        mid_y = (ball_pos[1] + target_opp.pos[1]) / 2.0
        lane_target = pitch.clamp(mid_x, mid_y)
        dist_opp_to_ball = distance(target_opp.pos, ball_pos)
        if dist_opp_to_ball > 40.0:
            threat = 0.2
        else:
            threat = max(0.2, 1.0 - dist_opp_to_ball / 40.0)
        score = threat * 0.5
        return (score, lane_target)

    def _score_mark_runner(
        self,
        ball_pos: Tuple[float, float],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[float, Tuple[float, float]]:
        """Legacy: Score for man-marking an attacker."""
        nearby_attackers = [
            o for o in opponents
            if not o.is_goalkeeper and distance(self.pos, o.pos) < 25.0
        ]
        if not nearby_attackers:
            return (0.0, self.tactical_anchor)
        target = min(nearby_attackers, key=lambda o: distance(self.pos, o.pos))
        dist_to_ball = distance(target.pos, ball_pos)
        threat = max(0.2, 1.0 - dist_to_ball / 30.0)
        offset = 1.5
        if attacking_right:
            mark_x = target.pos[0] - offset
        else:
            mark_x = target.pos[0] + offset
        mark_target = pitch.clamp(mark_x, target.pos[1])
        score = threat * 0.6
        return (score, mark_target)

    def _gk_position_adjust(
        self, ball_pos: Tuple[float, float], config: "EngineConfig", pitch: "Pitch", attacking_right: bool
    ):
        """Adjust GK position based on ball position."""
        if attacking_right:
            # We attack right, so our goal is at x=0
            goal_x = 5.0
        else:
            goal_x = config.pitch_length - 5.0

        goal_y = config.pitch_width / 2.0

        # Position between ball and center of goal
        shift_y = (ball_pos[1] - goal_y) * 0.3
        self.target_pos = pitch.clamp(goal_x, goal_y + shift_y)

    # =========================================================================
    # Softmax Selection (shared utility)
    # =========================================================================

    def _softmax_select(
        self, candidates: List[Tuple[float, str, dict]], config: "EngineConfig"
    ) -> Tuple[float, str, dict]:
        """Select from candidates using IQ-based softmax temperature."""
        if len(candidates) == 1:
            return candidates[0]

        scores = [self._candidate_score(c) for c in candidates]
        max_score = max(scores) if scores else 1.0
        min_score = min(scores) if scores else 0.0

        if max_score < 0.001:
            return random.choice(candidates)

        # Temperature is scaled to the candidate score spread. This keeps the
        # choice probabilistic, but prevents near-zero candidates from winning
        # too often when the value model has a clear preference.
        iq_noise = (100 - max(1, min(99, self.iq_value))) / 100.0
        score_spread = max(0.0, max_score - min_score)
        temperature = (0.0012 + score_spread * 0.10) * (0.18 + iq_noise * 0.62)
        temperature = max(0.0008, min(0.018, temperature))

        exp_scores = [math.exp((s - max_score) / temperature) for s in scores]
        total = sum(exp_scores)
        if total < 1e-10:
            return candidates[0]

        r = random.random() * total
        cumulative = 0.0
        for i, e in enumerate(exp_scores):
            cumulative += e
            if r <= cumulative:
                return candidates[i]

        return candidates[-1]

    def _candidate_score(self, candidate) -> float:
        if hasattr(candidate, "score"):
            return candidate.score
        return candidate[0]

    # =========================================================================
    # Legacy compatibility methods (delegate to new system)
    # =========================================================================

    def decide_off_ball_attacking(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ):
        """Legacy method - delegates to new system."""
        self.choose_off_ball_attack(ball_pos, config, pitch, attacking_right)

    def decide_off_ball_attacking_v2(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        ball_carrier: Optional["Player"] = None,
        opponents: Optional[List["Player"]] = None,
        teammates: Optional[List["Player"]] = None,
    ):
        """Legacy v2 method - delegates to new system."""
        self.choose_off_ball_attack(
            ball_pos, config, pitch, attacking_right,
            ball_carrier=ball_carrier, opponents=opponents, teammates=teammates,
        )

    def decide_off_ball_defending(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ):
        """Legacy method - delegates to new system."""
        self.choose_off_ball_defend(ball_pos, config, pitch, attacking_right)

    def decide_off_ball_defending_v2(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opponents: Optional[List["Player"]] = None,
    ):
        """Legacy v2 method - delegates to new system."""
        self.choose_off_ball_defend(
            ball_pos, config, pitch, attacking_right, opponents=opponents,
        )

    def decide_press(
        self,
        ball_carrier_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
    ):
        """Set target to press the ball carrier."""
        self.state = PlayerState.PRESSING
        self.target_pos = ball_carrier_pos

    def on_ball_tick(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        phase: str = "attacking",
    ):
        """Legacy on_ball_tick for backward compatibility.

        The new system uses choose_on_ball() in the match tick loop instead.
        This method wraps choose_on_ball to return an Action for old callers.
        """
        from .actions import Action, ActionType

        action_type, details = self.choose_on_ball(teammates, opponents, config, pitch, attacking_right)

        if action_type == "carry":
            return None  # carry is the default (no release)
        elif action_type in ("pass", "pass_to_space"):
            at = ActionType.LONG_PASS if details.get("is_long") else ActionType.SHORT_PASS
            return Action(
                at, details["target"], details.get("target_player_idx", details.get("intended_receiver", -1)),
                details.get("success_prob", 0.7), details.get("success_prob", 0.7),
            )
        elif action_type == "shoot":
            return Action(
                ActionType.SHOOT, details["target"], -1,
                details.get("on_target_prob", 0.3), details.get("on_target_prob", 0.3),
            )
        elif action_type == "clear":
            return Action(ActionType.LONG_PASS, details["target"], -1, 0.5, 0.6)
        return None
