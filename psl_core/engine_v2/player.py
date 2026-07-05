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

    # Facing direction (degrees, 0=right)
    facing_direction: float = 0.0

    # Stun state (after failed tackle)
    stun_ticks_remaining: int = 0
    hold_ticks: int = 0
    possession_ticks: int = 0

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

        if self.movement_intent in ("press", "contest", "attack_run"):
            blend = min(0.60, blend + 0.18)
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
    ) -> Tuple[str, dict]:
        """Choose on-ball action via score comparison. Returns (action_type, details).

        action_type is one of: "carry", "pass", "pass_to_space", "shoot", "hold", "clear"
        details contains target info needed by the match loop.
        """
        from .position_value import position_value

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

        candidates = []  # List of (score, action_type, details)

        # ------- CARRY candidates -------
        current_state_value = self._current_state_value(
            teammates, opponents, config, pitch, attacking_right
        )

        carry_candidates = self._score_carry_options(
            config, pitch, attacking_right, opponents, opp_positions, tm_positions,
            teammates, current_state_value
        )
        candidates.extend(carry_candidates)

        # ------- PASS candidates (unified pass-to-point model) -------
        pass_candidates = self._score_pass_point_options(
            teammates, opponents, config, pitch, attacking_right,
            opp_positions, tm_positions, current_state_value
        )
        candidates.extend(pass_candidates)

        # ------- SHOOT candidate -------
        shoot_score = 0.0
        if dist_to_goal <= config.shot_max_distance:
            shoot_score, shoot_details = self._score_shoot(
                goal_center, config, pitch, opponents, dist_to_goal
            )
            if shoot_score > 0:
                candidates.append((shoot_score, "shoot", shoot_details))

        # ------- HOLD / OBSERVE candidate -------
        hold_score = self._score_hold(
            teammates, opponents, config, pitch, attacking_right,
            pressure, shoot_score, pass_candidates, [],
        )
        if hold_score > 0:
            candidates.append((hold_score, "hold", {"target": self.pos}))

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
            candidates.append((clear_score, "clear", {"target": clear_target}))

        # If no candidates (shouldn't happen), default to carry forward
        if not candidates:
            if attacking_right:
                target = pitch.clamp(self.pos[0] + 5.0, self.pos[1])
            else:
                target = pitch.clamp(self.pos[0] - 5.0, self.pos[1])
            return ("carry", {"target": target})

        # Apply IQ noise to all candidate scores
        noisy_candidates = [
            (self._apply_iq_noise(score, config), action_type, details)
            for score, action_type, details in candidates
        ]

        # Selection via softmax with IQ-based temperature
        chosen = self._softmax_select(noisy_candidates, config)
        return (chosen[1], chosen[2])

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
        base_dist = config.carrier_speed
        candidate_offsets = [
            (forward_dir * base_dist, 0.0),
            (forward_dir * base_dist * 0.75, base_dist * 0.75),
            (forward_dir * base_dist * 0.75, -base_dist * 0.75),
            (0.0, base_dist),
            (0.0, -base_dist),
        ]

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
                
                # Time for defender to reach my path
                def_speed = (opp.abilities.get("Speed", 50) / 100.0) * config.player_max_speed
                time_def_reaches = perp_dist / max(def_speed, 0.1)
                
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
                    feasibility *= max(0.2, 1.0 - reduction)

            # Carry should be rewarded for improving the situation, not for
            # repeatedly re-claiming the absolute value of an already good
            # shooting position. This prevents one-more-touch loops near goal.
            pv_gain = pv - current_pv
            retain_value = current_pv * 0.18
            from .value_model import state_value, action_delta_score
            after_value = state_value(
                target, self, teammates, opponents, config, pitch, attacking_right
            )
            risk_cost = (1.0 - feasibility) * 0.10
            continuity = current_pv * 0.08
            score = action_delta_score(current_state_value, after_value, feasibility, risk_cost, continuity)

            # Near goal, continuing toward a worse angle/byline should lose
            # value quickly so shooting or cut-back can win naturally.
            if attacking_right:
                goal_x = config.pitch_length
            else:
                goal_x = 0.0
            old_goal_dist = distance(self.pos, (goal_x, config.pitch_width / 2.0))
            new_goal_dist = distance(target, (goal_x, config.pitch_width / 2.0))
            old_angle_width = abs(self.pos[1] - config.pitch_width / 2.0)
            new_angle_width = abs(target[1] - config.pitch_width / 2.0)
            if old_goal_dist < 22.0:
                score *= 0.75
                if new_angle_width > old_angle_width + 0.5:
                    score *= 0.55
                if new_goal_dist < 5.0:
                    score *= 0.25
                elif new_goal_dist > old_goal_dist + 0.5:
                    score *= 0.65
                if pv_gain < 0.04:
                    score *= 0.65
            if self.possession_ticks > 3 and pv_gain < 0.08:
                score *= max(0.30, 1.0 - (self.possession_ticks - 3) * 0.12)
            results.append((score, "carry", {"target": target}))

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

        iq = self.iq_value / 100.0
        pressure_factor = 1.0 / (1.0 + pressure * 0.55)
        nearest_pressure = 0.0
        for opp in opponents:
            if opp.is_goalkeeper:
                continue
            d = distance(self.pos, opp.pos)
            if d < 5.0:
                nearest_pressure = max(nearest_pressure, 1.0 - d / 5.0)
        pressure_factor *= max(0.18, 1.0 - nearest_pressure * 0.82)
        poor_options_bonus = max(0.0, 0.18 - best_pass) * 0.9
        settle_value = 0.055 + current_pv * 0.14 + developing_runs * 0.045 + poor_options_bonus

        if self.is_midfielder:
            settle_value *= 1.20
        elif self.is_defender:
            settle_value *= 1.12

        score = settle_value * (0.65 + 0.45 * iq) * pressure_factor

        # If there is already a good shot, observing should usually lose.
        if shoot_score > 0.12:
            score *= 0.45

        # Repeated holding gets less attractive unless pressure is low and options are bad.
        if self.hold_ticks > 0:
            score *= max(0.25, 1.0 - self.hold_ticks * 0.30)
        if self.possession_ticks > 2:
            score *= max(0.20, 1.0 - (self.possession_ticks - 2) * 0.18)

        return max(0.0, score)

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
        from .value_model import expected_pass_value

        results = []
        forward_dir = 1.0 if attacking_right else -1.0
        offside_line = self._get_offside_line(opponents, attacking_right, config)

        for tm in teammates:
            if tm.index == self.index or tm.is_goalkeeper:
                continue

            raw_targets = [(tm.pos, 1.0)]

            # Half-tick predicted position.
            future_x = tm.pos[0] + (tm.target_pos[0] - tm.pos[0]) * 0.5
            future_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.5
            raw_targets.append((pitch.clamp(future_x, future_y), 0.92))

            # A small leading pass if the team-mate is moving forward.
            move_progress = (tm.target_pos[0] - tm.pos[0]) * forward_dir
            if move_progress > 1.0:
                lead_x = tm.pos[0] + forward_dir * min(12.0, 4.0 + move_progress)
                lead_y = tm.pos[1] + (tm.target_pos[1] - tm.pos[1]) * 0.35
                raw_targets.append((pitch.clamp(lead_x, lead_y), 0.82))

            for target, receiver_arrival in raw_targets:
                d = distance(self.pos, target)
                if d < 3.0 or d > 55.0:
                    continue

                if self._is_offside_position(target, attacking_right, offside_line, config):
                    receiver_arrival *= 0.25

                is_long = d > 30.0
                passing = self.abilities.get("Long_Passing" if is_long else "Short_Passing", 50) / 100.0
                base = config.long_pass_base_success if is_long else config.short_pass_base_success
                dist_factor = max(0.35, 1.0 - max(0.0, d - 10.0) / 65.0)
                base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor

                continuity = 0.075 if distance(target, tm.pos) <= 4.0 else 0.045
                score, success_prob, lane_risk, consequence = expected_pass_value(
                    self, tm, self.pos, target,
                    teammates, opponents, config, pitch, attacking_right,
                    current_state_value, base_accuracy,
                    receiver_arrival=receiver_arrival,
                    continuity=continuity,
                )

                if score <= 0.001:
                    continue

                pass_type = "long_pass" if is_long else "short_pass"
                action_type = "pass_to_space" if distance(target, tm.pos) > 4.0 else "pass"
                details = {
                    "target": target,
                    "success_prob": success_prob,
                    "lane_risk": lane_risk,
                    "turnover_consequence": consequence,
                    "is_long": is_long,
                    "pass_type": pass_type,
                }
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
            if self._is_offside_position(tm.pos, attacking_right, offside_line, config):
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
            if self._is_offside_position(future_pos, attacking_right, offside_line, config):
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
        offside_line: float, config: "EngineConfig"
    ) -> bool:
        """Check if a position would be offside (used for pass-to-space filtering)."""
        if attacking_right:
            # Must be in opponent half AND ahead of offside line AND ahead of ball
            if pos[0] <= config.pitch_length / 2.0:
                return False
            return pos[0] > offside_line
        else:
            if pos[0] >= config.pitch_length / 2.0:
                return False
            return pos[0] < offside_line

    def _score_shoot(
        self,
        goal_center: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        opponents: List["Player"],
        dist_to_goal: float,
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
            dist_factor = 1.0 - excess * 0.055
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

        # On-target probability
        on_target_prob = (
            config.shot_on_target_base
            * (0.4 + 0.6 * ability)
            * dist_factor
            * angle_factor
            * pressure_factor
            * lane_factor
        )
        min_on_target = 0.16 if dist_to_goal < 25.0 else 0.08
        on_target_prob = max(min_on_target, min(0.78, on_target_prob))


        # Score = on_target_prob * (1 - save_estimate) * goal_reward
        # xG-based decision: angle/distance/pressure drive the chance quality;
        # keeper quality affects final conversion, but not enough to forbid
        # otherwise good shots.
        base_save = config.gk_save_base
        distance_save_relief = min(0.18, max(0.0, (dist_to_goal - 16.0) * 0.006))
        angle_save_bonus = (1.0 - angle_factor) * 0.12
        pressure_save_bonus = (1.0 - pressure_factor * lane_factor) * 0.10
        central_bonus = 0.0
        if dist_to_goal < 18.0 and abs(self.pos[1] - config.pitch_width / 2.0) < 12.0:
            central_bonus = 0.12

        save_estimate = max(
            0.35,
            min(0.90, base_save + angle_save_bonus + pressure_save_bonus - distance_save_relief - central_bonus),
        )

        from .value_model import shot_quality_at
        xG = shot_quality_at(self.pos, self, opponents, config, goal_center[0] > self.pos[0])
        score = xG * config.goal_reward_constant
        if dist_to_goal < 18.0 and angle_factor > 0.65:
            score *= 1.70
        elif dist_to_goal < 25.0 and angle_factor > 0.55:
            score *= 1.65

        return (score, {
            "target": goal_center,
            "on_target_prob": on_target_prob,
            "xg": xG,
        })

    def _score_clear(self, x_progress: float, pressure: int, config: "EngineConfig") -> float:
        """Score clearance from danger and pressure as an opportunity tradeoff."""
        danger = max(0.0, 1.0 - x_progress / 0.45)
        pressure_factor = 1.0 - math.exp(-pressure / 2.0)
        return max(0.0, danger * pressure_factor * config.clear_reward_base)

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

        forward_x = config.pitch_length * (0.55 if attacking_right else 0.45)
        target = pitch.clamp(forward_x, config.pitch_width / 2 + random.uniform(-12, 12))
        return ("pass", {"target": target, "target_player_idx": -1, "success_prob": 0.45, "is_long": True, "pass_type": "long_pass"})

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

        candidates = []  # (score, position)

        # "Stay" option: score = position_value(current_pos)
        stay_pv = position_value(
            self.pos[0], self.pos[1], pitch, attacking_right,
            opp_positions, tm_positions, config,
            runner_formation_pos=anchor,
        )
        # Apply offside penalty to stay option (soft, allows offside trap runs)
        if self._is_offside_position(self.pos, attacking_right, offside_line, config):
            stay_pv *= 0.15
        candidates.append((stay_pv, self.pos))

        search_radius = 24.0 if self.is_attacker else 18.0 if self.is_midfielder else 14.0
        raw_candidates = []

        # Spatial samples around the dynamic role anchor.
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
            if self.is_midfielder:
                support_center = (ball_pos[0] - forward_dir * 10.0, ball_pos[1])
            elif self.is_defender:
                support_center = (ball_pos[0] - forward_dir * 24.0, ball_pos[1])
            else:
                support_center = (ball_pos[0] + forward_dir * 7.0, ball_pos[1])
            for _ in range(5):
                angle = random.random() * math.tau
                radius = random.random() ** 0.7 * 16.0
                raw_candidates.append((
                    support_center[0] + math.cos(angle) * radius,
                    support_center[1] + math.sin(angle) * radius,
                    (
                        anchor[0] * 0.55 + support_center[0] * 0.45,
                        anchor[1] * 0.65 + support_center[1] * 0.35,
                    ),
                ))

        for raw_x, raw_y, anchor_pos in raw_candidates:
            pos = pitch.clamp(raw_x, raw_y)

            # Position value (with role_distance_decay applied via runner_formation_pos)
            pv = position_value(
                pos[0], pos[1], pitch, attacking_right,
                opp_positions, tm_positions, config,
                runner_formation_pos=anchor_pos,
            )

            # Receive reachability: can I arrive before defenders?
            reach = receive_reachability(
                pos, self.pos, max_speed,
                opp_positions, opp_speeds,
                ball_pos, config.pass_to_space_ball_speed, config
            )

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
            role_limit = 26.0 if self.is_attacker else 22.0 if self.is_midfielder else 18.0
            role_shape_factor = max(0.005, 1.0 - (role_dist / role_limit) ** 1.55)

            lane_factor = 1.0
            if self.position in ("LW", "LM", "LB", "LWB") and pos[1] > config.pitch_width * 0.58:
                lane_factor = 0.005
            elif self.position in ("RW", "RM", "RB", "RWB") and pos[1] < config.pitch_width * 0.42:
                lane_factor = 0.005

            # Offside penalty: soft penalty (allows deliberate offside trap runs)
            offside_penalty = 1.0
            if self._is_offside_position(pos, attacking_right, offside_line, config):
                offside_penalty = 0.08
            else:
                # Softly discourage living right on the line; good timed runs
                # can still happen, but the default support shape stays onside.
                if attacking_right and pos[0] > offside_line - 3.0:
                    offside_penalty *= 0.45
                elif (not attacking_right) and pos[0] < offside_line + 3.0:
                    offside_penalty *= 0.45

            score = pv * reach * pass_feasibility * space_bonus * offside_penalty * role_shape_factor * lane_factor
            candidates.append((score, pos))

        if not candidates:
            self.target_pos = anchor
            return self.target_pos

        # Apply IQ noise to all candidate scores
        noisy_candidates = [
            (self._apply_iq_noise(score, config), pos)
            for score, pos in candidates
        ]

        # IQ-based temperature selection
        temperature = (100 - max(1, min(99, self.iq_value))) / 100.0
        temperature = max(0.05, temperature * 0.5)

        scores = [c[0] for c in noisy_candidates]
        max_score = max(scores)
        if max_score < 0.01:
            self.set_movement_target(anchor, "recover_shape")
            return self.target_pos

        exp_scores = [math.exp((s - max_score) / max(0.01, temperature)) for s in scores]
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
        if move_progress > 4.0:
            intent = "attack_run"
        elif distance(chosen_pos, anchor) > 10.0:
            intent = "support"
        else:
            intent = "recover_shape"
        self.set_movement_target(chosen_pos, intent)
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
        attackers = [o for o in opponents if not o.is_goalkeeper]
        teammates_no_gk = [t for t in teammates if t.index != self.index and not t.is_goalkeeper]
        attacker_positions = [(o.pos[0], o.pos[1]) for o in attackers]
        teammate_positions = [(t.pos[0], t.pos[1]) for t in teammates_no_gk]
        defenders_closer_to_ball = sum(
            1 for t in teammates_no_gk
            if distance(t.pos, ball_pos) < dist_to_ball - 1.0
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
            for oy in (-3.0, 0.0, 3.0):
                sampled_points.append(pitch.clamp(ball_pos[0] + goal_side * 2.2, ball_pos[1] + oy))

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
            score = base_score * (1.0 + press_value * (0.25 + shot_danger * 0.75)) * (1.0 - cover_cost * 0.45)

            if ball_carrier and distance(point, ball_carrier.pos) < config.tackle_range:
                score *= 1.0 + shot_danger * 0.55
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
        if (
            ball_carrier
            and dist_to_ball < config.tackle_range * (0.55 + shot_danger * 0.15)
            and distance(raw_target, ball_carrier.pos) < config.tackle_range * (0.75 + shot_danger * 0.15)
        ):
            action_type = "tackle"
        elif ball_carrier and distance(raw_target, ball_carrier.pos) < config.press_radius:
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

        # Temperature from IQ: higher IQ = lower temperature = more rational
        temperature = (100 - max(1, min(99, self.iq_value))) / 100.0
        temperature = max(0.05, temperature * 0.5)

        scores = [c[0] for c in candidates]
        max_score = max(scores) if scores else 1.0

        if max_score < 0.001:
            return random.choice(candidates)

        exp_scores = [math.exp((s - max_score) / max(0.01, temperature)) for s in scores]
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
