"""Player model with pure reward-driven decision making.

Every player, every tick, chooses from candidates by score comparison.
NO hard rules -- all behavior emerges from reward/score comparisons.

On-ball candidates:
    carry_to(pos) -- score = position_value(target) * path_feasibility
    pass_to(tm)   -- score = pass_success_rate * position_value(tm.pos)
    shoot         -- score = on_target_prob * (1-save_estimate) * goal_reward
    clear         -- score = danger_reduction (high when pressured in own half)

Off-ball attacking:
    move_to(X) -- score = position_value(X) * reachability * receive_probability
    stay        -- score = position_value(current_pos)

Off-ball defending:
    approach       -- safe, moderate score
    tackle         -- score = success_rate * ball_value - (1-success_rate) * stun_penalty
    block_lane     -- score = lane_threat_value
    mark_runner    -- score = attacker_threat
    hold_position  -- score = 0.35 (baseline safe choice)

IQ effect: temperature = (100 - IQ) / 100, selection via softmax.
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

        action_type is one of: "carry", "pass", "shoot", "clear"
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

        # Selection via softmax with IQ-based temperature
        chosen = self._softmax_select(candidates, config)
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

            # Path feasibility: 1.0 if no opp within 4m of path, decays with proximity
            feasibility = 1.0
            for opp in opponents:
                if opp.is_goalkeeper:
                    continue
                # Check if opponent is near the movement path
                opp_dx = opp.pos[0] - self.pos[0]
                opp_dy = opp.pos[1] - self.pos[1]
                move_len = math.sqrt(dx * dx + dy * dy)
                if move_len > 0.1:
                    proj = (opp_dx * dx + opp_dy * dy) / (move_len * move_len)
                    if 0 < proj < 1.2:
                        perp = abs(opp_dx * dy - opp_dy * dx) / move_len
                        if perp < 4.0:
                            # Any defender in path is a major obstacle
                            proximity_decay = max(0.15, perp / 4.0)
                            # Attacker Dribbling vs Defender Tackling
                            def_tackling = opp.abilities.get("Tackling", 50) / 100.0
                            my_dribbling = self.abilities.get("Dribbling", 50) / 100.0
                            # Net = how much better I am than the defender
                            # Even matched = ~0.3 feasibility, much better = ~0.6
                            skill_ratio = my_dribbling / (my_dribbling + def_tackling + 0.01)
                            ability_factor = 0.15 + 0.5 * skill_ratio  # range: 0.15-0.65
                            feasibility *= proximity_decay * ability_factor

            # Multiple defenders nearby = much harder to carry
            nearby_defenders = sum(
                1 for opp in opponents
                if not opp.is_goalkeeper and math.sqrt((opp.pos[0]-self.pos[0])**2 + (opp.pos[1]-self.pos[1])**2) < 6.0
            )
            if nearby_defenders >= 2:
                feasibility *= 0.2  # surrounded = almost impossible to carry
            elif nearby_defenders == 1:
                feasibility *= 0.5  # one defender = risky
            
            # Near goal line/byline = dead end (can't carry further)
            if attacking_right:
                dist_to_byline = pitch.length - target[0]
            else:
                dist_to_byline = target[0]
            if dist_to_byline < 5.0:
                feasibility *= 0.3  # near byline, nowhere to go
            elif dist_to_byline < 10.0:
                feasibility *= 0.6

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

        # Distance factor
        if dist_to_goal <= config.shot_ideal_distance:
            dist_factor = 1.0
        else:
            excess = dist_to_goal - config.shot_ideal_distance
            dist_factor = math.exp(-excess / 8.0)

        # Angle factor
        angle = angle_to_goal(self.pos, goal_center, config.goal_width)
        angle_factor = min(1.0, angle / 0.3)

        # On-target probability
        on_target_prob = config.shot_on_target_base * (0.4 + 0.6 * ability) * dist_factor * angle_factor
        on_target_prob = max(0.05, min(0.85, on_target_prob))


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
        """Score clearance.

        score = 0.1 normally, 0.8 when in own third under pressure
        """
        if x_progress > 0.45:
            # Not in defensive zone, clearance has very low value
            return config.clear_reward_base * 0.1

        # In own third: high danger when under pressure
        if x_progress < 0.33 and pressure >= 2:
            return 0.8

        # In own half with some pressure
        danger = (0.45 - x_progress) * 2.0  # 0..0.9
        pressure_factor = min(3.0, pressure) / 3.0  # 0..1
        score = config.clear_reward_base + danger * pressure_factor * 0.5
        return score

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

        For each of 5 sampled positions:
            score = position_value(pos) * reachability * receive_chance
        Also: "stay" option with score = position_value(current_pos)

        Returns the chosen target position.
        """
        from .position_value import position_value

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

        candidates = []  # (score, position)

        # "Stay" option: score = position_value(current_pos)
        stay_pv = position_value(
            self.pos[0], self.pos[1], pitch, attacking_right,
            opp_positions, tm_positions, config
        )
        candidates.append((stay_pv, self.pos))

        # Sample 5 candidate positions
        max_roam = 25.0 if self.is_attacker else 18.0 if self.is_midfielder else 12.0
        for _ in range(5):
            cx = self.formation_pos[0] + random.uniform(-max_roam, max_roam)
            cy = self.formation_pos[1] + random.uniform(-max_roam * 0.6, max_roam * 0.6)
            pos = pitch.clamp(cx, cy)

            # Position value
            pv = position_value(
                pos[0], pos[1], pitch, attacking_right,
                opp_positions, tm_positions, config
            )

            # Reachability: 1.0 if within speed*1 tick, decays for further
            dist = distance(self.pos, pos)
            if dist <= max_speed:
                reachability = 1.0
            else:
                reachability = max_speed / max(1.0, dist)

            # Receive chance: can I get a pass here? (no opp between me and ball)
            receive_chance = 1.0
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
                            receive_chance *= 0.5

            # Reduce receive_chance if too far from ball (can't get a pass that far)
            dist_to_ball = distance(pos, ball_pos)
            if dist_to_ball > 25.0:
                receive_chance *= max(0.1, 1.0 - (dist_to_ball - 25.0) / 35.0)

            score = pv * reachability * receive_chance
            candidates.append((score, pos))

        if not candidates:
            self.target_pos = self.formation_pos
            return self.target_pos

        # IQ-based temperature selection
        temperature = (100 - max(1, min(99, self.iq_value))) / 100.0
        temperature = max(0.05, temperature * 0.5)

        scores = [c[0] for c in candidates]
        max_score = max(scores)
        if max_score < 0.01:
            self.target_pos = self.formation_pos
            return self.target_pos

        exp_scores = [math.exp((s - max_score) / max(0.01, temperature)) for s in scores]
        total = sum(exp_scores)
        if total < 1e-10:
            chosen_pos = candidates[0][1]
        else:
            r = random.random() * total
            cumulative = 0.0
            chosen_pos = candidates[-1][1]
            for i, e in enumerate(exp_scores):
                cumulative += e
                if r <= cumulative:
                    chosen_pos = candidates[i][1]
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
    # Off-Ball Defending Decision: Pure Reward
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
        """Choose defending action. Returns (action_type, details).

        Candidates and scores:
        - approach: 0.3 + 0.3*(1.0 - dist/press_radius)
        - tackle: success_rate * ball_value - (1-success_rate) * stun_cost
        - block_lane: threat_of_nearest_attacker_in_zone * 0.5
        - mark_runner: nearest_attacker_threat * 0.4
        - hold_position: 0.35 (baseline safe choice)
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

        # 1. APPROACH: score = 0.3 + 0.3*(1.0 - dist/press_radius)
        if dist_to_ball < config.press_radius * 2:
            proximity = max(0.0, 1.0 - dist_to_ball / config.press_radius)
            approach_score = 0.3 + 0.4 * proximity  # defenders should actively close down carrier
            # Predict where carrier will be (lead the press)
            if ball_carrier:
                # Rough prediction: carrier moves forward ~4m per tick
                import math
                lead_dist = config.carrier_speed * 0.5  # predict half a tick ahead
                carrier_dir_x = 1.0 if attacking_right else -1.0  # assume carrier goes forward
                predicted = (ball_pos[0] + carrier_dir_x * lead_dist, ball_pos[1])
                approach_target = predicted
            else:
                approach_target = ball_pos
            candidates.append((approach_score, "approach", {"target": approach_target}))

        # 2. TACKLE: score = success_rate * ball_value - (1-success_rate) * stun_cost
        if ball_carrier and dist_to_ball < config.tackle_range:
            tackle_score = self._score_tackle(ball_carrier, dist_to_ball, config)
            if tackle_score > 0:
                candidates.append((tackle_score, "tackle", {"target": ball_carrier.pos}))

        # 3. BLOCK_LANE: score = threat_of_nearest_attacker_in_zone * 0.5
        lane_score, lane_target = self._score_block_lane(
            ball_pos, opponents, config, pitch, attacking_right
        )
        if lane_score > 0:
            candidates.append((lane_score, "block_lane", {"target": lane_target}))

        # 4. MARK_RUNNER: score = nearest_attacker_threat * 0.4
        mark_score, mark_target = self._score_mark_runner(
            ball_pos, opponents, config, pitch, attacking_right
        )
        if mark_score > 0:
            candidates.append((mark_score, "mark_runner", {"target": mark_target}))

        # 5. HOLD_POSITION: only strong when ball is far away
        if dist_to_ball > 30.0:
            hold_score = 0.45  # ball far, hold shape
        elif dist_to_ball > 15.0:
            hold_score = 0.30  # ball medium, slightly hold
        else:
            hold_score = 0.15  # ball close, should be engaging!
        candidates.append((hold_score, "hold_position", {"target": self.formation_pos}))

        if not candidates:
            self.target_pos = self.formation_pos
            return ("hold_position", {"target": self.formation_pos})

        # Softmax select
        chosen = self._softmax_select(candidates, config)
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

    def _score_block_lane(
        self,
        ball_pos: Tuple[float, float],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> Tuple[float, Tuple[float, float]]:
        """Score for blocking a passing lane.

        score = threat_of_nearest_attacker_in_zone * 0.5
        """
        # Find most dangerous attacking opponent in zone
        dangerous = [o for o in opponents if not o.is_goalkeeper and distance(self.pos, o.pos) < 25.0]
        if not dangerous:
            return (0.0, self.formation_pos)

        # Pick the one nearest to us (in our zone)
        target_opp = min(dangerous, key=lambda o: distance(self.pos, o.pos))

        # Position between ball and this opponent
        mid_x = (ball_pos[0] + target_opp.pos[0]) / 2.0
        mid_y = (ball_pos[1] + target_opp.pos[1]) / 2.0
        lane_target = pitch.clamp(mid_x, mid_y)

        # Threat level based on proximity
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
        """Score for man-marking an attacker.

        score = nearest_attacker_threat * 0.4
        """
        # Find nearby threatening attackers
        nearby_attackers = [
            o for o in opponents
            if not o.is_goalkeeper and distance(self.pos, o.pos) < 25.0
        ]
        if not nearby_attackers:
            return (0.0, self.formation_pos)

        # Pick the closest
        target = min(nearby_attackers, key=lambda o: distance(self.pos, o.pos))

        # Threat based on their proximity to ball and our goal
        dist_to_ball = distance(target.pos, ball_pos)
        threat = max(0.2, 1.0 - dist_to_ball / 30.0)

        # Mark position: slightly goalside
        offset = 1.5
        if attacking_right:
            # We're attacking right, so defending left - but we need to think about
            # the opponent's attack direction. If we're defending, opponent attacks our goal.
            mark_x = target.pos[0] - offset if attacking_right else target.pos[0] + offset
        else:
            mark_x = target.pos[0] + offset
        mark_target = pitch.clamp(mark_x, target.pos[1])

        score = threat * 0.6  # marking is important
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
        elif action_type == "pass":
            at = ActionType.LONG_PASS if details.get("is_long") else ActionType.SHORT_PASS
            return Action(
                at, details["target"], details.get("target_player_idx", -1),
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
