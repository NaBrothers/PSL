"""Player model, state machine, and decision-making (Phase 2).

Major changes from Phase 1:
- Unified decision framework with tactic_weight * role_modifier
- 5 attacking off-ball actions (HOLD_POS, FIND_SPACE, MAKE_RUN, DROP_DEEP, GO_WIDE)
- 5 defending off-ball actions (PRESS, BLOCK_LANE, MAN_MARK, COVER, HOLD_SHAPE)
- CARRY and CROSS on-ball actions
- Vision-filtered pass targets
"""

from __future__ import annotations

import random
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .physics import distance, move_toward, player_speed, angle_between_points
from .actions import (
    Action,
    ActionType,
    OffBallAttackAction,
    OffBallDefendAction,
    score_short_pass,
    score_long_pass,
    score_shoot,
    score_dribble,
    score_carry,
    score_cross,
    select_action_iq_weighted,
    apply_unified_scoring,
)

if TYPE_CHECKING:
    from .config import EngineConfig
    from .pitch import Pitch
    from .ball import Ball


class PlayerState(Enum):
    OFF_BALL = "off_ball"
    ON_BALL = "on_ball"
    PRESSING = "pressing"
    CONTEST = "contest"


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

    # Phase 2: facing direction (degrees, 0=right)
    facing_direction: float = 0.0

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

    # Phase 2 stats
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
        """Check if this player is in an attacking position."""
        return self.position in ("ST", "CF", "LW", "RW", "LF", "RF", "LS", "RS")

    @property
    def is_midfielder(self) -> bool:
        """Check if this player is a midfielder."""
        return self.position in (
            "CM", "LCM", "RCM", "CDM", "LDM", "RDM", "CAM", "RAM", "LAM",
            "LM", "RM", "AM",
        )

    @property
    def is_defender(self) -> bool:
        """Check if this is a defensive position."""
        return self.position in (
            "CB", "LCB", "RCB", "LB", "RB", "LWB", "RWB",
        )

    @property
    def is_wide(self) -> bool:
        """Check if player is in a wide position."""
        return self.position in (
            "LW", "RW", "LM", "RM", "LB", "RB", "LWB", "RWB",
        )

    def get_move_speed(self, config: "EngineConfig") -> float:
        """Get this player's movement speed in meters per tick."""
        return player_speed(self.speed_value, config.player_max_speed, config.player_min_speed)

    def move_tick(self, config: "EngineConfig", pitch: "Pitch"):
        """Move player toward their target position for one tick."""
        if self.state == PlayerState.ON_BALL:
            return

        speed = self.get_move_speed(config)
        old_pos = self.pos
        new_pos = move_toward(self.pos, self.target_pos, speed)
        new_pos = pitch.clamp(new_pos[0], new_pos[1])
        self.pos = new_pos

        # Track distance
        self.distance_covered += distance(old_pos, new_pos)

        # Update facing direction toward target
        if distance(old_pos, new_pos) > 0.1:
            self.facing_direction = angle_between_points(old_pos, new_pos)

    # =========================================================================
    # Phase 2: Attacking Off-Ball (5 actions)
    # =========================================================================

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
        """Intelligent attacking off-ball decision (Phase 2).

        Chooses between:
        - HOLD_POSITION: stay near formation anchor
        - FIND_SPACE: move toward highest space-value point
        - MAKE_RUN: timed forward sprint into space behind defense
        - DROP_DEEP: move toward carrier to offer short option
        - GO_WIDE: move toward sideline to stretch play
        """
        if opponents is None:
            opponents = []
        if teammates is None:
            teammates = []

        # GK special: always hold position when team has ball
        if self.is_goalkeeper:
            self.target_pos = self.formation_pos
            return

        # Score each off-ball action
        candidates = []

        # 1. HOLD_POSITION
        hold_score = self._score_hold_position(ball_pos, config, pitch, attacking_right)
        candidates.append((hold_score, OffBallAttackAction.HOLD_POSITION))

        # 2. FIND_SPACE
        space_score = self._score_find_space(ball_pos, config, pitch, attacking_right, opponents, teammates)
        candidates.append((space_score, OffBallAttackAction.FIND_SPACE))

        # 3. MAKE_RUN (only for attackers/midfielders, when conditions met)
        run_score = self._score_make_run(ball_pos, config, pitch, attacking_right, ball_carrier, opponents, teammates)
        candidates.append((run_score, OffBallAttackAction.MAKE_RUN))

        # 4. DROP_DEEP
        deep_score = self._score_drop_deep(ball_pos, config, pitch, attacking_right, ball_carrier, opponents)
        candidates.append((deep_score, OffBallAttackAction.DROP_DEEP))

        # 5. GO_WIDE
        wide_score = self._score_go_wide(ball_pos, config, pitch, attacking_right, opponents, teammates)
        candidates.append((wide_score, OffBallAttackAction.GO_WIDE))

        # Select action using IQ-weighted selection
        chosen = self._select_off_ball_action(candidates, config)

        # Execute chosen action
        self._execute_off_ball_attack(chosen, ball_pos, config, pitch, attacking_right, ball_carrier, opponents)

    def _compute_structure_bonus(self, target_pos, teammates, config, pitch) -> float:
        """Reward actions that maintain good team structure."""
        bonus = 1.0

        # 1. Don't go where teammates already are (spacing)
        for tm in teammates:
            if tm.index == self.index:
                continue
            d = distance(target_pos, tm.pos)
            if d < 8.0:  # too close to a teammate
                bonus *= 0.5

        # 2. Stay within your zone (defenders shouldn't run to forward positions)
        dist_from_home = distance(target_pos, self.formation_pos)
        max_roam = 25.0 if self.is_attacker else 18.0 if self.is_midfielder else 12.0
        if dist_from_home > max_roam:
            bonus *= 0.3

        # 3. Team width reward - if we're going wide and no one else is wide on that side
        mid_y = pitch.width / 2
        if abs(target_pos[1] - mid_y) > 20:  # going to a wide position
            others_wide_same_side = sum(
                1 for tm in teammates
                if abs(tm.pos[1] - target_pos[1]) < 10 and tm.index != self.index
            )
            if others_wide_same_side == 0:
                bonus *= 1.4  # reward - we're providing width no one else gives

        return max(0.2, min(1.5, bonus))

    def _score_hold_position(self, ball_pos, config, pitch, attacking_right) -> float:
        """Score for holding formation position. Maintains team layers."""
        dist_to_ball = distance(self.pos, ball_pos)
        base = 0.6
        if self.is_defender:
            base = 0.85
        if self.is_midfielder:
            base = 0.65
        if dist_to_ball > 40.0:
            base += 0.15
        return apply_unified_scoring(base, "attacking", "hold_position", self.position)

    def _score_find_space(self, ball_pos, config, pitch, attacking_right, opponents, teammates=None) -> float:
        """Score for finding open space. Mainly for attackers and midfielders near ball."""
        if teammates is None:
            teammates = []
        base = 0.3
        if self.is_attacker:
            base = 0.6
        elif self.is_midfielder:
            base = 0.45
        # Defenders rarely leave position to find space
        if self.is_defender:
            base = 0.1

        # Higher if currently marked
        nearby_opps = sum(1 for o in opponents if distance(self.pos, o.pos) < 8.0)
        if nearby_opps > 0:
            base += 0.1

        # Apply team structure bonus
        target = self._find_best_space(config, pitch, opponents)
        structure_bonus = self._compute_structure_bonus(target, teammates, config, pitch)
        base *= structure_bonus

        return apply_unified_scoring(base, "attacking", "find_space", self.position)

    def _score_make_run(self, ball_pos, config, pitch, attacking_right, carrier, opponents, teammates=None) -> float:
        """Score for making a forward run behind the defense.

        Conditions: carrier facing + space ahead + player is attacker/midfielder
        """
        if teammates is None:
            teammates = []
        if self.is_defender:
            return 0.0

        # Check if there's space behind the defensive line
        if not opponents:
            return 0.3

        # Find defensive line
        if attacking_right:
            def_line_x = max(o.pos[0] for o in opponents if not o.is_goalkeeper) if opponents else pitch.length * 0.8
            space_ahead = def_line_x - self.pos[0]
        else:
            def_line_x = min(o.pos[0] for o in opponents if not o.is_goalkeeper) if opponents else pitch.length * 0.2
            space_ahead = self.pos[0] - def_line_x

        if space_ahead < 5.0:
            return 0.0

        base = 0.4
        if self.is_attacker:
            base = 0.7
        elif self.is_midfielder:
            base = 0.5

        # Speed bonus for making runs
        speed_factor = self.speed_value / 100.0
        base += speed_factor * 0.2

        # Apply team structure bonus using estimated run target
        run_dist = config.make_run_distance * (0.7 + 0.3 * self.speed_value / 100.0)
        if attacking_right:
            target_pos = pitch.clamp(self.pos[0] + run_dist, self.pos[1])
        else:
            target_pos = pitch.clamp(self.pos[0] - run_dist, self.pos[1])
        structure_bonus = self._compute_structure_bonus(target_pos, teammates, config, pitch)
        base *= structure_bonus

        return apply_unified_scoring(base, "attacking", "make_run", self.position)

    def _score_drop_deep(self, ball_pos, config, pitch, attacking_right, carrier, opponents) -> float:
        """Score for dropping deep to offer a short option.

        Triggered when carrier is under pressure.
        """
        if carrier is None:
            return 0.2

        # Check if carrier is under pressure
        carrier_pressure = sum(1 for o in opponents if distance(carrier.pos, o.pos) < config.press_radius)
        if carrier_pressure == 0:
            return 0.1

        # More valuable for midfielders
        base = 0.3 + carrier_pressure * 0.15
        if self.is_midfielder:
            base += 0.15

        # Distance to carrier matters - too far away is not useful
        dist_to_carrier = distance(self.pos, carrier.pos)
        if dist_to_carrier > 30.0:
            base *= 0.5
        elif dist_to_carrier < 10.0:
            base *= 0.8  # already close enough

        return apply_unified_scoring(base, "attacking", "drop_deep", self.position)

    def _score_go_wide(self, ball_pos, config, pitch, attacking_right, opponents, teammates=None) -> float:
        """Score for going wide to stretch the defense."""
        if teammates is None:
            teammates = []
        # Best for wide players
        base = 0.3
        if self.is_wide:
            base = 0.65

        # Check if the wide area is open
        y_from_center = abs(self.pos[1] - pitch.width / 2.0)
        if y_from_center > pitch.width * 0.3:
            # Already wide, less value in going wider
            base *= 0.5

        # Apply team structure bonus for the wide target position
        if self.pos[1] < pitch.width / 2.0:
            target_y = config.go_wide_y_target
        else:
            target_y = pitch.width - config.go_wide_y_target
        target_pos = pitch.clamp(self.formation_pos[0], target_y)
        structure_bonus = self._compute_structure_bonus(target_pos, teammates, config, pitch)
        base *= structure_bonus

        return apply_unified_scoring(base, "attacking", "go_wide", self.position)

    def _select_off_ball_action(
        self, candidates: List[Tuple[float, float]], config: "EngineConfig"
    ) -> OffBallAttackAction:
        """Select off-ball action using IQ-weighted softmax."""
        if not candidates:
            return OffBallAttackAction.HOLD_POSITION

        # IQ-based temperature
        noise = (100 - max(1, min(99, self.iq_value))) / 100.0 * config.iq_noise_factor
        temperature = config.decision_temperature * (0.3 + noise * 2.0)

        scores = [c[0] for c in candidates]
        max_score = max(scores) if scores else 1.0

        if max_score < 0.01:
            return OffBallAttackAction.HOLD_POSITION

        exp_scores = [math.exp((s - max_score) / max(0.01, temperature)) for s in scores]
        total = sum(exp_scores)
        if total < 1e-10:
            return candidates[0][1]

        r = random.random() * total
        cumulative = 0.0
        for i, e in enumerate(exp_scores):
            cumulative += e
            if r <= cumulative:
                return candidates[i][1]

        return candidates[-1][1]

    def _execute_off_ball_attack(
        self,
        action: OffBallAttackAction,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        carrier: Optional["Player"],
        opponents: List["Player"],
    ):
        """Execute the chosen off-ball attacking action by setting target_pos."""
        if action == OffBallAttackAction.HOLD_POSITION:
            # Stay near formation anchor with small noise
            tx = self.formation_pos[0] + random.uniform(-2.0, 2.0)
            ty = self.formation_pos[1] + random.uniform(-1.5, 1.5)
            self.target_pos = pitch.clamp(tx, ty)

        elif action == OffBallAttackAction.FIND_SPACE:
            # Move toward space away from defenders
            best_pos = self._find_best_space(config, pitch, opponents)
            self.target_pos = best_pos

        elif action == OffBallAttackAction.MAKE_RUN:
            # Sprint forward into space behind defense
            run_dist = config.make_run_distance * (0.7 + 0.3 * self.speed_value / 100.0)
            if attacking_right:
                tx = self.pos[0] + run_dist
                ty = self.pos[1] + random.uniform(-5.0, 5.0)
            else:
                tx = self.pos[0] - run_dist
                ty = self.pos[1] + random.uniform(-5.0, 5.0)
            self.target_pos = pitch.clamp(tx, ty)

        elif action == OffBallAttackAction.DROP_DEEP:
            # Move toward ball carrier
            if carrier:
                direction_x = carrier.pos[0] - self.pos[0]
                direction_y = carrier.pos[1] - self.pos[1]
                d = max(1.0, math.sqrt(direction_x**2 + direction_y**2))
                move_dist = min(config.drop_deep_distance, d * 0.6)
                tx = self.pos[0] + direction_x / d * move_dist
                ty = self.pos[1] + direction_y / d * move_dist
                self.target_pos = pitch.clamp(tx, ty)
            else:
                self.target_pos = pitch.clamp(ball_pos[0], ball_pos[1])

        elif action == OffBallAttackAction.GO_WIDE:
            # Move toward sideline
            if self.pos[1] < pitch.width / 2.0:
                target_y = config.go_wide_y_target
            else:
                target_y = pitch.width - config.go_wide_y_target

            # Maintain x-position roughly
            target_x = self.formation_pos[0]
            # Push slightly forward
            if attacking_right:
                target_x += random.uniform(0, 5.0)
            else:
                target_x -= random.uniform(0, 5.0)
            self.target_pos = pitch.clamp(target_x, target_y)

    def _find_best_space(
        self,
        config: "EngineConfig",
        pitch: "Pitch",
        opponents: List["Player"],
    ) -> Tuple[float, float]:
        """Find the position with most space (away from defenders) within player's tactical zone."""
        best_pos = self.formation_pos
        best_space = 0.0

        # Constrain search to within max_roam of formation position (tactical zone)
        max_roam = 25.0 if self.is_attacker else 18.0 if self.is_midfielder else 12.0
        search_radius = min(config.find_space_radius, max_roam)

        # Sample several candidate positions within tactical zone
        for _ in range(5):
            cx = self.formation_pos[0] + random.uniform(-search_radius, search_radius)
            cy = self.formation_pos[1] + random.uniform(-search_radius, search_radius)
            cx, cy = pitch.clamp(cx, cy)

            # Ensure candidate is within max_roam of formation position
            if distance((cx, cy), self.formation_pos) > max_roam:
                continue

            # Compute space value: minimum distance to any opponent
            min_opp_dist = min(
                (distance((cx, cy), o.pos) for o in opponents if not o.is_goalkeeper),
                default=30.0,
            )

            # Also consider distance from formation (don't drift too far)
            dist_from_formation = distance((cx, cy), self.formation_pos)
            space_value = min_opp_dist - dist_from_formation * 0.15

            if space_value > best_space:
                best_space = space_value
                best_pos = (cx, cy)

        return best_pos

    # =========================================================================
    # Phase 2: Defending Off-Ball (5 actions)
    # =========================================================================

    def decide_off_ball_defending_v2(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opponents: Optional[List["Player"]] = None,
    ):
        """Intelligent defending off-ball decision (Phase 2).

        Chooses between:
        - PRESS: close down ball carrier
        - BLOCK_LANE: position between carrier and dangerous teammate
        - MAN_MARK: track specific nearby attacker
        - COVER: position behind pressing teammate
        - HOLD_SHAPE: stay in formation position
        """
        if opponents is None:
            opponents = []

        # GK: always adjust position toward ball
        if self.is_goalkeeper:
            self._gk_position_adjust(ball_pos, config, pitch, attacking_right)
            return

        # Score each defending action
        candidates = []

        # 1. PRESS
        press_score = self._score_press(ball_pos, config)
        candidates.append((press_score, OffBallDefendAction.PRESS))

        # 2. BLOCK_LANE
        lane_score = self._score_block_lane(ball_pos, config, opponents)
        candidates.append((lane_score, OffBallDefendAction.BLOCK_LANE))

        # 3. MAN_MARK
        mark_score = self._score_man_mark(ball_pos, config, opponents)
        candidates.append((mark_score, OffBallDefendAction.MAN_MARK))

        # 4. COVER
        cover_score = self._score_cover(ball_pos, config)
        candidates.append((cover_score, OffBallDefendAction.COVER))

        # 5. HOLD_SHAPE
        shape_score = self._score_hold_shape(ball_pos, config)
        candidates.append((shape_score, OffBallDefendAction.HOLD_SHAPE))

        # Select using IQ-weighted softmax
        chosen = self._select_defend_action(candidates, config)

        # Execute
        self._execute_off_ball_defend(chosen, ball_pos, config, pitch, attacking_right, opponents)

    def _gk_position_adjust(self, ball_pos, config, pitch, attacking_right):
        """GK positions between ball and center of goal."""
        if attacking_right:
            goal_x = 0.0
        else:
            goal_x = pitch.length

        goal_y = pitch.width / 2.0

        # Position on the line between ball and goal center, close to goal
        dx = ball_pos[0] - goal_x
        dy = ball_pos[1] - goal_y
        d = max(1.0, math.sqrt(dx * dx + dy * dy))

        # Stay 3-5m off the goal line
        offset = 4.0
        tx = goal_x + dx / d * offset
        ty = goal_y + dy / d * min(offset * 2, abs(dy))

        # Clamp to reasonable GK area
        if attacking_right:
            tx = max(0.5, min(16.0, tx))
        else:
            tx = max(pitch.length - 16.0, min(pitch.length - 0.5, tx))
        ty = max(pitch.width * 0.2, min(pitch.width * 0.8, ty))

        self.target_pos = (tx, ty)

    def _score_press(self, ball_pos, config) -> float:
        """Score for pressing the ball carrier. Only 1-2 closest should press."""
        dist_to_ball = distance(self.pos, ball_pos)
        if dist_to_ball > config.press_radius * 1.5:
            return 0.0

        proximity = max(0, 1.0 - dist_to_ball / config.press_radius)
        tackling = self.abilities.get("Tackling", 50) / 100.0
        base = proximity * 0.8 + tackling * 0.1
        if self.is_defender:
            base *= 0.5
        return apply_unified_scoring(base, "defending", "press", self.position)

    def _score_block_lane(self, ball_pos, config, opponents) -> float:
        """Score for blocking passing lane."""
        if not opponents:
            return 0.1

        # Find the most dangerous opponent near our position
        base = 0.3
        defence = self.abilities.get("Defence", 50) / 100.0
        base += defence * 0.2

        # Better for central defenders
        if self.is_defender:
            base += 0.1

        return apply_unified_scoring(base, "defending", "block_lane", self.position)

    def _score_man_mark(self, ball_pos, config, opponents) -> float:
        """Score for man-marking a specific attacker."""
        if not opponents:
            return 0.1

        # Find nearby attackers
        nearby_attackers = [
            o for o in opponents
            if distance(self.pos, o.pos) < 15.0 and not o.is_goalkeeper
        ]
        if not nearby_attackers:
            return 0.1

        base = 0.4
        defence = self.abilities.get("Defence", 50) / 100.0
        base += defence * 0.15

        return apply_unified_scoring(base, "defending", "man_mark", self.position)

    def _score_cover(self, ball_pos, config) -> float:
        """Score for covering behind a pressing teammate."""
        base = 0.35
        if self.is_defender:
            base = 0.5
        return apply_unified_scoring(base, "defending", "cover", self.position)

    def _score_hold_shape(self, ball_pos, config) -> float:
        """Score for holding formation shape. Key for maintaining team structure."""
        dist_to_ball = distance(self.pos, ball_pos)
        base = 0.65
        if dist_to_ball > 20.0:
            base = 0.8
        if dist_to_ball > 40.0:
            base = 0.95
        if self.is_defender:
            base += 0.15
        return apply_unified_scoring(base, "defending", "hold_shape", self.position)

    def _select_defend_action(
        self, candidates: List[Tuple[float, float]], config: "EngineConfig"
    ) -> OffBallDefendAction:
        """Select defending action using IQ-weighted softmax."""
        if not candidates:
            return OffBallDefendAction.HOLD_SHAPE

        noise = (100 - max(1, min(99, self.iq_value))) / 100.0 * config.iq_noise_factor
        temperature = config.decision_temperature * (0.3 + noise * 2.0)

        scores = [c[0] for c in candidates]
        max_score = max(scores) if scores else 1.0

        if max_score < 0.01:
            return OffBallDefendAction.HOLD_SHAPE

        exp_scores = [math.exp((s - max_score) / max(0.01, temperature)) for s in scores]
        total = sum(exp_scores)
        if total < 1e-10:
            return candidates[0][1]

        r = random.random() * total
        cumulative = 0.0
        for i, e in enumerate(exp_scores):
            cumulative += e
            if r <= cumulative:
                return candidates[i][1]

        return candidates[-1][1]

    def _execute_off_ball_defend(
        self,
        action: OffBallDefendAction,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        opponents: List["Player"],
    ):
        """Execute the chosen off-ball defending action."""
        if action == OffBallDefendAction.PRESS:
            # Move toward ball
            self.target_pos = ball_pos
            self.state = PlayerState.PRESSING

        elif action == OffBallDefendAction.BLOCK_LANE:
            # Position between ball and nearest dangerous opponent
            if opponents:
                # Find the most dangerous forward opponent
                dangerous = [o for o in opponents if not o.is_goalkeeper]
                if dangerous:
                    # Pick closest to goal
                    if attacking_right:
                        target_opp = min(dangerous, key=lambda o: o.pos[0])
                    else:
                        target_opp = max(dangerous, key=lambda o: o.pos[0])

                    # Position between ball and this opponent
                    mid_x = (ball_pos[0] + target_opp.pos[0]) / 2.0
                    mid_y = (ball_pos[1] + target_opp.pos[1]) / 2.0
                    # Bias toward our goal
                    if attacking_right:
                        mid_x -= config.block_lane_offset
                    else:
                        mid_x += config.block_lane_offset
                    self.target_pos = pitch.clamp(mid_x, mid_y)
                else:
                    self.target_pos = self.formation_pos
            else:
                self.target_pos = self.formation_pos

        elif action == OffBallDefendAction.MAN_MARK:
            # Track nearest attacker
            nearby_attackers = [
                o for o in opponents
                if distance(self.pos, o.pos) < 20.0 and not o.is_goalkeeper
            ]
            if nearby_attackers:
                target = min(nearby_attackers, key=lambda o: distance(self.pos, o.pos))
                # Stay slightly goalside
                offset = 1.5
                if attacking_right:
                    tx = target.pos[0] - offset
                else:
                    tx = target.pos[0] + offset
                self.target_pos = pitch.clamp(tx, target.pos[1])
            else:
                self.target_pos = self.formation_pos

        elif action == OffBallDefendAction.COVER:
            # Position behind the ball (between ball and own goal)
            if attacking_right:
                tx = self.pos[0] - config.cover_depth
            else:
                tx = self.pos[0] + config.cover_depth
            # Shift toward ball y
            ty = self.pos[1] + (ball_pos[1] - self.pos[1]) * 0.3
            self.target_pos = pitch.clamp(tx, ty)

        elif action == OffBallDefendAction.HOLD_SHAPE:
            # Stay in formation with slight shift toward ball
            tx = self.formation_pos[0]
            ty = self.formation_pos[1]
            # Slight pull toward ball
            ty += (ball_pos[1] - ty) * 0.15
            self.target_pos = pitch.clamp(tx, ty)

    # =========================================================================
    # Legacy off-ball methods (kept for compatibility, delegate to v2)
    # =========================================================================

    def decide_off_ball_attacking(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ):
        """Legacy method - delegates to v2."""
        self.decide_off_ball_attacking_v2(ball_pos, config, pitch, attacking_right)

    def decide_off_ball_defending(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ):
        """Legacy method - delegates to v2."""
        self.decide_off_ball_defending_v2(ball_pos, config, pitch, attacking_right)

    def decide_press(
        self,
        ball_carrier_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
    ):
        """Set target to press the ball carrier."""
        self.state = PlayerState.PRESSING
        self.target_pos = ball_carrier_pos

    # =========================================================================
    # On-Ball Decision Making (Phase 2)
    # =========================================================================

    def generate_actions(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        phase: str = "attacking",
    ) -> List[Action]:
        """Generate and score candidate actions for a player on the ball.

        Phase 2 additions:
        - Vision-filtered pass targets
        - CARRY action (open space)
        - CROSS action (wide positions)
        - Unified scoring framework applied to all actions
        """
        from .vision import get_visible_targets

        actions: List[Action] = []

        # Determine goal position
        if attacking_right:
            goal_center = pitch.away_goal_center()
        else:
            goal_center = pitch.home_goal_center()

        dist_to_goal = distance(self.pos, goal_center)

        # Get vision-filtered teammates
        visible_teammates = get_visible_targets(self, teammates, self.pos, config)

        # Short passes to visible nearby teammates
        for tm in visible_teammates:
            d = distance(self.pos, tm.pos)
            if 3.0 < d < 35.0:
                action = score_short_pass(self, tm, config, opponents, phase)
                if action.score > 0.01:
                    actions.append(action)

        # Long passes to visible distant teammates
        for tm in visible_teammates:
            d = distance(self.pos, tm.pos)
            if 25.0 < d < 70.0:
                action = score_long_pass(self, tm, config, opponents, phase)
                if action.score > 0.01:
                    actions.append(action)

        # Shoot if in range
        if dist_to_goal <= config.shot_max_distance:
            action = score_shoot(self, goal_center, config, pitch, phase)
            if action.score > 0.01:
                actions.append(action)

        # CARRY: open space forward movement
        if not self.is_goalkeeper:
            carry_dist = config.carry_min_distance + (
                config.carry_max_distance - config.carry_min_distance
            ) * self.speed_value / 100.0
            if attacking_right:
                carry_target = pitch.clamp(self.pos[0] + carry_dist, self.pos[1] + random.uniform(-3, 3))
            else:
                carry_target = pitch.clamp(self.pos[0] - carry_dist, self.pos[1] + random.uniform(-3, 3))

            nearby_opps = [o for o in opponents if distance(self.pos, o.pos) < config.carry_defender_check_radius]
            action = score_carry(self, carry_target, config, nearby_opps, attacking_right, phase)
            if action.score > 0.01:
                actions.append(action)

        # DRIBBLE: 1v1 take-on when pressed
        if not self.is_goalkeeper:
            nearby_opps = [o for o in opponents if distance(self.pos, o.pos) < config.press_radius]
            if nearby_opps:
                if attacking_right:
                    dx = random.uniform(3.0, 5.0)
                else:
                    dx = random.uniform(-5.0, -3.0)
                dribble_target = pitch.clamp(self.pos[0] + dx, self.pos[1] + random.uniform(-2, 2))
                action = score_dribble(self, dribble_target, config, nearby_opps, phase)
                if action.score > 0.01:
                    actions.append(action)

        # CROSS: from wide positions
        if not self.is_goalkeeper:
            # Target the penalty area
            if attacking_right:
                cross_target_x = pitch.length - config.cross_target_box_depth
            else:
                cross_target_x = config.cross_target_box_depth
            cross_target_y = pitch.width / 2.0 + random.uniform(-10.0, 10.0)
            cross_target = pitch.clamp(cross_target_x, cross_target_y)

            action = score_cross(self, cross_target, config, opponents, attacking_right, pitch, phase)
            if action.score > 0.01:
                actions.append(action)

        # HOLD: keep the ball, control, observe (simulates ball preparation time)
        if not self.is_goalkeeper:
            hold_base = 0.55
            # Just received ball? Higher hold score (stop and control)
            if getattr(self, '_ticks_with_ball', 0) <= 1:
                hold_base = 0.85  # strongly prefer holding when just received
            # Under pressure? Less hold, more urgency to pass
            pressers = sum(1 for o in opponents if distance(self.pos, o.pos) < config.press_radius)
            if pressers > 0:
                hold_base *= 0.6
            # Defenders hold less (clear quickly)
            if self.is_defender:
                hold_base *= 0.8
            hold_score = apply_unified_scoring(hold_base, phase, "hold", self.position)
            if hold_score > 0.01:
                hold_target = pitch.clamp(self.pos[0], self.pos[1])
                actions.append(Action(ActionType.HOLD, hold_target, -1, hold_score, 0.99))

        # Goalkeeper special: always prefer distribution
        if self.is_goalkeeper and not actions:
            if attacking_right:
                target = pitch.clamp(pitch.length * 0.6, pitch.width / 2 + random.uniform(-15, 15))
            else:
                target = pitch.clamp(pitch.length * 0.4, pitch.width / 2 + random.uniform(-15, 15))
            actions.append(Action(ActionType.LONG_PASS, target, -1, 0.5, 0.5))

        return actions

    def choose_action(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
        phase: str = "attacking",
    ) -> Optional[Action]:
        """Choose an action for a player on the ball."""
        # Track how long we've been holding the ball (reset externally when holder changes)
        if not hasattr(self, '_ticks_with_ball'):
            self._ticks_with_ball = 0
        self._ticks_with_ball += 1
        actions = self.generate_actions(teammates, opponents, config, pitch, attacking_right, phase)
        if not actions:
            # Fallback: just carry forward
            dx = 5.0 if attacking_right else -5.0
            return Action(
                ActionType.CARRY,
                pitch.clamp(self.pos[0] + dx, self.pos[1]),
                -1, 0.5, 0.85,
            )
        return select_action_iq_weighted(actions, self.iq_value, config)
