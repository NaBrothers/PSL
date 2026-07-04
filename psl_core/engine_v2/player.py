"""Player model with pure reward-driven decision making.

Every player, every tick, chooses from candidates by score comparison.
NO hard rules -- all behavior emerges from reward/score comparisons.

On-ball candidates:
    carry_to(pos) -- score = position_value(target) * path_feasibility
    pass_to(tm)   -- score = pass_success_rate * position_value(tm.pos)
    pass_to_space -- score = PV(future_pos) * arrival_prob * pass_accuracy
    shoot         -- score = on_target_prob * (1-save_estimate) * goal_reward
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
    formation_pos: Tuple[float, float] = (0.0, 0.0)  # base formation position
    target_pos: Tuple[float, float] = (0.0, 0.0)  # where player is moving to

    # Facing direction (degrees, 0=right)
    facing_direction: float = 0.0

    # Stun state (after failed tackle)
    stun_ticks_remaining: int = 0

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
        """Get movement speed based on distance to target (near=walk, far=run)."""
        max_speed = player_speed(self.speed_value, config.player_max_speed, config.player_min_speed)

        if self.state == PlayerState.PRESSING:
            return max_speed * 0.85

        dist_to_target = distance(self.pos, self.target_pos)

        if dist_to_target < 2.0:
            return max_speed * 0.05
        elif dist_to_target < 5.0:
            return max_speed * 0.2
        elif dist_to_target < 10.0:
            return max_speed * 0.35
        elif dist_to_target < 20.0:
            return max_speed * 0.55
        else:
            return max_speed * 0.7

    def move_tick(self, config: "EngineConfig", pitch: "Pitch"):
        """Move player toward their target position for one tick."""
        if self.state == PlayerState.ON_BALL:
            return
        if self.state == PlayerState.STUNNED:
            return

        speed = self.get_move_speed(config)
        old_pos = self.pos
        new_pos = move_toward(self.pos, self.target_pos, speed)
        new_pos = pitch.clamp(new_pos[0], new_pos[1])
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

        action_type is one of: "carry", "pass", "pass_to_space", "shoot", "clear"
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
        carry_candidates = self._score_carry_options(
            config, pitch, attacking_right, opponents, opp_positions, tm_positions
        )
        candidates.extend(carry_candidates)

        # ------- PASS candidates -------
        pass_candidates = self._score_pass_options(
            teammates, config, pitch, attacking_right, opponents, opp_positions, tm_positions
        )
        candidates.extend(pass_candidates)

        # ------- PASS TO SPACE candidates -------
        space_pass_candidates = self._score_pass_to_space_options(
            teammates, opponents, config, pitch, attacking_right, opp_positions, tm_positions
        )
        candidates.extend(space_pass_candidates)

        # ------- SHOOT candidate -------
        if dist_to_goal <= config.shot_max_distance:
            shoot_score, shoot_details = self._score_shoot(
                goal_center, config, pitch, opponents, dist_to_goal
            )
            if shoot_score > 0:
                candidates.append((shoot_score, "shoot", shoot_details))

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
    ) -> List[Tuple[float, str, dict]]:
        """Generate and score carry candidates.

        score = position_value(target) * path_feasibility
        path_feasibility = 1.0 if no opp within 4m of path, decays with proximity
        """
        from .position_value import position_value

        results = []
        forward_dir = 1.0 if attacking_right else -1.0

        # Generate 3 carry directions: forward, forward-left, forward-right
        carry_dist = config.carrier_speed  # one tick carry distance
        directions = [
            (forward_dir * carry_dist, 0.0),  # straight forward
            (forward_dir * carry_dist * 0.7, carry_dist * 0.7),  # forward-right
            (forward_dir * carry_dist * 0.7, -carry_dist * 0.7),  # forward-left
        ]

        for dx, dy in directions:
            target = pitch.clamp(self.pos[0] + dx, self.pos[1] + dy)

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

            score = pv * feasibility
            results.append((score, "carry", {"target": target}))

        return results

    def _score_pass_options(
        self,
        teammates: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opponents: List["Player"],
        opp_positions: List[Tuple[float, float]],
        tm_positions: List[Tuple[float, float]],
    ) -> List[Tuple[float, str, dict]]:
        """Score pass candidates: pass_success_prob * position_value(target).

        pass_success = f(Passing ability, distance, lane clarity)
        """
        from .position_value import position_value

        results = []
        passing_ability = self.abilities.get("Short_Passing", 50)
        long_passing = self.abilities.get("Long_Passing", 50)

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

            # Position value of teammate's position
            pv = position_value(
                tm.pos[0], tm.pos[1], pitch, attacking_right,
                opp_positions, tm_positions, config
            )

            score = success_rate * pv

            pass_type = "long_pass" if is_long else "short_pass"
            results.append((score, "pass", {
                "target": tm.pos,
                "target_player_idx": tm.index,
                "success_prob": success_rate,
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

            # Position value of future position
            pv = position_value(
                future_pos[0], future_pos[1], pitch, attacking_right,
                opp_pos_no_gk, tm_positions, config
            )

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

            score = pv * arrival_prob * pass_acc * lane_clarity

            is_long = d > 30.0
            results.append((score, "pass_to_space", {
                "target": future_pos,
                "intended_receiver": tm.index,
                "success_prob": pass_acc * lane_clarity,
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

        # Distance factor - gentler decay for medium-range shots
        if dist_to_goal <= config.shot_ideal_distance:
            dist_factor = 1.0
        elif dist_to_goal <= 30.0:
            # 20-30m: gradual decay
            excess = dist_to_goal - config.shot_ideal_distance
            dist_factor = 1.0 - excess * 0.03  # 0.7 at 30m
        else:
            # 30m+: steeper decay
            dist_factor = 0.7 * math.exp(-(dist_to_goal - 30.0) / 20.0)

        # Angle factor
        angle = angle_to_goal(self.pos, goal_center, config.goal_width)
        angle_factor = min(1.0, angle / 0.2)  # easier threshold for angle

        # On-target probability
        on_target_prob = config.shot_on_target_base * (0.4 + 0.6 * ability) * dist_factor * angle_factor
        on_target_prob = max(0.18, min(0.85, on_target_prob))


        # Score = on_target_prob * (1 - save_estimate) * goal_reward
        # xG-based decision: angle/distance(main) + space + GK(minor)
        # Block factor: defenders in shot path reduce score
        block_factor = 1.0
        # (block detection happens in interaction resolution, here we estimate)
        
        # GK factor: small influence (10-15%), player still shoots if angle is good
        gk_factor = 1.0 - (config.gk_save_base * 0.15)
        
        # xG estimate
        xG = on_target_prob * block_factor * gk_factor
        score = xG * config.goal_reward_constant

        return (score, {
            "target": goal_center,
            "on_target_prob": on_target_prob,
        })

    def _score_clear(self, x_progress: float, pressure: int, config: "EngineConfig") -> float:
        """Score clearance. Only a last resort under extreme pressure in own box."""
        if x_progress > 0.35:
            return 0.0  # never clear when not deep in own half

        # Only consider clearing under heavy pressure (3+) in own box
        if x_progress < 0.15 and pressure >= 3:
            return 0.5  # extreme danger, clear it
        
        # Moderate pressure in own third
        if pressure >= 2:
            return 0.2  # might clear, but pass is usually better
        
        return 0.0  # no pressure = no reason to clear

    def _gk_choose(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[str, dict]:
        """Goalkeeper distribution choice - always passes out quickly."""
        from .position_value import position_value

        opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
        tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != self.index]

        # Find best pass target among teammates
        best_score = 0.0
        best_target = None
        best_idx = -1

        passing_ability = self.abilities.get("Short_Passing", 50) / 100.0

        for tm in teammates:
            if tm.is_goalkeeper:
                continue
            d = distance(self.pos, tm.pos)
            if d < 5.0 or d > 50.0:
                continue

            pv = position_value(
                tm.pos[0], tm.pos[1], pitch, attacking_right,
                opp_positions, tm_positions, config
            )
            success_rate = 0.85 * (0.5 + 0.5 * passing_ability)
            score = success_rate * pv

            if score > best_score:
                best_score = score
                best_target = tm.pos
                best_idx = tm.index

        if best_target:
            d = distance(self.pos, best_target)
            is_long = d > 30.0
            return ("pass", {
                "target": best_target,
                "target_player_idx": best_idx,
                "success_prob": 0.85,
                "is_long": is_long,
                "pass_type": "long_pass" if is_long else "short_pass",
            })

        # Fallback: long pass forward
        if attacking_right:
            target = pitch.clamp(config.pitch_length * 0.6, config.pitch_width / 2 + random.uniform(-15, 15))
        else:
            target = pitch.clamp(config.pitch_length * 0.4, config.pitch_width / 2 + random.uniform(-15, 15))
        return ("pass", {
            "target": target,
            "target_player_idx": -1,
            "success_prob": 0.6,
            "is_long": True,
            "pass_type": "long_pass",
        })

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

        # GK: stay near formation position
        if self.is_goalkeeper:
            self.target_pos = self.formation_pos
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
            opp_positions, tm_positions, config
        )
        candidates.append((stay_pv, self.pos))

        # Maximum roam range based on how far from formation
        max_roam = 25.0 if self.is_attacker else 18.0 if self.is_midfielder else 12.0

        # Generate 8 structured candidate positions
        # 3 forward positions (different depths)
        forward_candidates = [
            (self.formation_pos[0] + forward_dir * random.uniform(8, max_roam),
             self.formation_pos[1] + random.uniform(-5, 5)),
            (self.formation_pos[0] + forward_dir * random.uniform(5, 15),
             self.formation_pos[1] + random.uniform(-8, 8)),
            (self.formation_pos[0] + forward_dir * random.uniform(12, max_roam),
             self.formation_pos[1] + random.uniform(-3, 3)),
        ]

        # 2 wide positions
        wide_offset = random.uniform(10, 20)
        wide_candidates = [
            (self.formation_pos[0] + forward_dir * random.uniform(0, 8),
             self.formation_pos[1] + wide_offset),
            (self.formation_pos[0] + forward_dir * random.uniform(0, 8),
             self.formation_pos[1] - wide_offset),
        ]

        # 1 back (drop deep)
        back_candidates = [
            (self.formation_pos[0] - forward_dir * random.uniform(5, 12),
             self.formation_pos[1] + random.uniform(-8, 8)),
        ]

        # 2 diagonal positions
        diagonal_candidates = [
            (self.formation_pos[0] + forward_dir * random.uniform(5, 15),
             self.formation_pos[1] + random.uniform(8, 15)),
            (self.formation_pos[0] + forward_dir * random.uniform(5, 15),
             self.formation_pos[1] - random.uniform(8, 15)),
        ]

        all_raw = forward_candidates + wide_candidates + back_candidates + diagonal_candidates
        for raw_x, raw_y in all_raw:
            pos = pitch.clamp(raw_x, raw_y)

            # Position value
            pv = position_value(
                pos[0], pos[1], pitch, attacking_right,
                opp_positions, tm_positions, config
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

            # Offside penalty: heavily penalize positions that are offside
            offside_penalty = 1.0
            if self._is_offside_position(pos, attacking_right, offside_line, config):
                offside_penalty = 0.05  # almost never go offside intentionally

            score = pv * reach * pass_feasibility * space_bonus * offside_penalty
            candidates.append((score, pos))

        if not candidates:
            self.target_pos = self.formation_pos
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
            self.target_pos = self.formation_pos
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

        # Clamp: players don't roam too far from formation
        max_roam = 25.0 if self.is_attacker else 20.0 if self.is_midfielder else 15.0
        from .physics import distance as _dist
        roam_dist = _dist(chosen_pos, self.formation_pos)
        if roam_dist > max_roam:
            ratio = max_roam / roam_dist
            self.target_pos = (
                self.formation_pos[0] + (chosen_pos[0] - self.formation_pos[0]) * ratio,
                self.formation_pos[1] + (chosen_pos[1] - self.formation_pos[1]) * ratio,
            )
        else:
            self.target_pos = chosen_pos
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
        """Choose defending action using zone-based marking. Returns (action_type, details).

        Zone-based: each defender marks attackers within 20m of their formation_pos.
        - mark_runner: most threatening attacker in MY zone
        - block_lane: position between ball and attacker I'm marking
        - If NO attacker in my zone -> hold_position
        """
        if opponents is None:
            opponents = []
        if teammates is None:
            teammates = []

        # GK: position adjustment
        if self.is_goalkeeper:
            self._gk_position_adjust(ball_pos, config, pitch, attacking_right)
            return ("hold_position", {"target": self.target_pos})

        # Stunned players can't do anything
        if self.state == PlayerState.STUNNED:
            return ("hold_position", {"target": self.pos})

        dist_to_ball = distance(self.pos, ball_pos)

        candidates = []  # (score, action_type, details)

        # Zone radius for marking
        zone_radius = 20.0

        # Find attackers in MY zone (within zone_radius of my formation_pos)
        attackers_in_zone = [
            o for o in opponents
            if not o.is_goalkeeper and distance(self.formation_pos, o.pos) < zone_radius
        ]

        # 1. APPROACH: only for designated presser
        if dist_to_ball < config.press_radius * 2:
            proximity = max(0.0, 1.0 - dist_to_ball / config.press_radius)
            approach_score = 0.3 + 0.4 * proximity
            if ball_carrier:
                lead_dist = config.carrier_speed * 0.5
                carrier_dir_x = 1.0 if attacking_right else -1.0
                predicted = (ball_pos[0] + carrier_dir_x * lead_dist, ball_pos[1])
                approach_target = predicted
            else:
                approach_target = ball_pos
            if getattr(self, '_is_closest_presser', False):
                candidates.append((approach_score, "approach", {"target": approach_target}))

        # 2. TACKLE: score = success_rate * ball_value - (1-success_rate) * stun_cost
        if ball_carrier and dist_to_ball < config.tackle_range:
            tackle_score = self._score_tackle(ball_carrier, dist_to_ball, config)
            if tackle_score > 0:
                candidates.append((tackle_score, "tackle", {"target": ball_carrier.pos}))

        # 3. MARK_RUNNER (zone-based): most threatening attacker in MY zone
        if attackers_in_zone:
            mark_score, mark_target = self._score_mark_runner_zone(
                ball_pos, attackers_in_zone, config, pitch, attacking_right
            )
            if mark_score > 0:
                candidates.append((mark_score, "mark_runner", {"target": mark_target}))

        # 4. BLOCK_LANE (zone-based): between ball and attacker I'm marking
        if attackers_in_zone:
            lane_score, lane_target = self._score_block_lane_zone(
                ball_pos, attackers_in_zone, config, pitch, attacking_right
            )
            if lane_score > 0:
                candidates.append((lane_score, "block_lane", {"target": lane_target}))

        # 5. HOLD_POSITION: strong when no attackers in zone or ball is far
        if not attackers_in_zone:
            # No attacker in zone -- hold position (don't chase ball)
            hold_score = 0.55
        elif dist_to_ball > 30.0:
            hold_score = 0.45
        elif dist_to_ball > 15.0:
            hold_score = 0.30
        else:
            hold_score = 0.15
        candidates.append((hold_score, "hold_position", {"target": self.formation_pos}))

        if not candidates:
            self.target_pos = self.formation_pos
            return ("hold_position", {"target": self.formation_pos})

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
        raw_target = details.get("target", self.formation_pos)
        # Clamp: defenders don't roam more than max_roam from formation
        max_roam = 20.0 if self.is_defender else 30.0 if self.is_midfielder else 40.0
        from .physics import distance as _dist
        roam_dist = _dist(raw_target, self.formation_pos)
        if roam_dist > max_roam:
            # Move toward target but only up to max_roam
            ratio = max_roam / roam_dist
            self.target_pos = (
                self.formation_pos[0] + (raw_target[0] - self.formation_pos[0]) * ratio,
                self.formation_pos[1] + (raw_target[1] - self.formation_pos[1]) * ratio,
            )
        else:
            self.target_pos = raw_target

        # If approaching, set pressing state
        if action_type == "approach":
            self.state = PlayerState.PRESSING

        return (action_type, details)

    def _score_tackle(self, ball_carrier: "Player", dist_to_ball: float, config: "EngineConfig") -> float:
        """Score for attempting a tackle.

        score = success_rate * ball_value - (1-success_rate) * stun_cost
        Only positive when very close + high Tackling.
        """
        tackling = self.abilities.get("Tackling", 50)
        dribbling = ball_carrier.abilities.get("Dribbling", 50)

        # Success rate based on Tackling vs Dribbling and distance
        dist_factor = max(0.5, 1.0 - dist_to_ball / config.tackle_range)
        success_rate = (tackling / (tackling + dribbling + 1.0)) * dist_factor
        success_rate = max(0.2, min(0.8, success_rate))

        # Ball value: how valuable is winning the ball here
        ball_value = 3.0

        # Stun cost: penalty for being stunned
        stun_cost = 0.15

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
            return (0.0, self.formation_pos)

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
            return (0.0, self.formation_pos)

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
            return (0.0, self.formation_pos)

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
            return (0.0, self.formation_pos)
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
            return (0.0, self.formation_pos)
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
