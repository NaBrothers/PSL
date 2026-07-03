"""Player model, state machine, and decision-making."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .physics import distance, move_toward, player_speed
from .actions import (
    Action,
    ActionType,
    score_short_pass,
    score_long_pass,
    score_shoot,
    score_dribble,
    select_action_iq_weighted,
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

    def get_move_speed(self, config: "EngineConfig") -> float:
        """Get this player's movement speed in meters per tick."""
        return player_speed(self.speed_value, config.player_max_speed, config.player_min_speed)

    def move_tick(self, config: "EngineConfig", pitch: "Pitch"):
        """Move player toward their target position for one tick."""
        if self.state == PlayerState.ON_BALL:
            # Don't auto-move when on ball (handled by action)
            return

        speed = self.get_move_speed(config)
        old_pos = self.pos
        new_pos = move_toward(self.pos, self.target_pos, speed)
        new_pos = pitch.clamp(new_pos[0], new_pos[1])
        self.pos = new_pos

        # Track distance
        self.distance_covered += distance(old_pos, new_pos)

    def decide_off_ball_attacking(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ):
        """Set target position for off-ball attacking movement."""
        # Base: return toward formation position
        target_x = self.formation_pos[0]
        target_y = self.formation_pos[1]

        # Forward bias when ball is in our attacking half
        if attacking_right:
            ball_progress = ball_pos[0] / pitch.length
        else:
            ball_progress = 1.0 - ball_pos[0] / pitch.length

        if ball_progress > 0.5:
            # Ball is in opponent half, push forward
            push = config.forward_bias_attack * ball_progress
            if attacking_right:
                target_x += push
            else:
                target_x -= push

        # Add slight randomness to avoid static positioning
        target_x += random.uniform(-2.0, 2.0)
        target_y += random.uniform(-1.5, 1.5)

        self.target_pos = pitch.clamp(target_x, target_y)

    def decide_off_ball_defending(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ):
        """Set target position for off-ball defending movement."""
        # Pull back toward formation but shift toward ball
        target_x = self.formation_pos[0]
        target_y = self.formation_pos[1]

        # Shift toward ball y-position (track the ball laterally)
        ball_y_pull = (ball_pos[1] - target_y) * 0.2
        target_y += ball_y_pull

        # Compact: shift toward own goal based on ball position
        if attacking_right:
            ball_depth = ball_pos[0] / pitch.length
            if ball_depth < 0.5:
                # Ball is in our half, pull back
                target_x -= config.forward_bias_attack * (0.5 - ball_depth)
        else:
            ball_depth = 1.0 - ball_pos[0] / pitch.length
            if ball_depth < 0.5:
                target_x += config.forward_bias_attack * (0.5 - ball_depth)

        self.target_pos = pitch.clamp(target_x, target_y)

    def decide_press(
        self,
        ball_carrier_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
    ):
        """Set target to press the ball carrier."""
        self.state = PlayerState.PRESSING
        self.target_pos = ball_carrier_pos

    def generate_actions(
        self,
        teammates: List["Player"],
        opponents: List["Player"],
        config: "EngineConfig",
        pitch: "Pitch",
        attacking_right: bool,
    ) -> List[Action]:
        """Generate and score candidate actions for a player on the ball."""
        actions: List[Action] = []

        # Determine goal position
        if attacking_right:
            goal_center = pitch.away_goal_center()
        else:
            goal_center = pitch.home_goal_center()

        dist_to_goal = distance(self.pos, goal_center)

        # Short passes to nearby teammates
        for tm in teammates:
            if tm.index == self.index:
                continue
            d = distance(self.pos, tm.pos)
            if 3.0 < d < 35.0:
                action = score_short_pass(self, tm, config, opponents)
                if action.score > 0.01:
                    actions.append(action)

        # Long passes to distant teammates
        for tm in teammates:
            if tm.index == self.index:
                continue
            d = distance(self.pos, tm.pos)
            if 25.0 < d < 70.0:
                action = score_long_pass(self, tm, config, opponents)
                if action.score > 0.01:
                    actions.append(action)

        # Shoot if in range
        if dist_to_goal <= config.shot_max_distance:
            action = score_shoot(self, goal_center, config, pitch)
            if action.score > 0.01:
                actions.append(action)

        # Dribble forward
        if not self.is_goalkeeper:
            dx = 8.0 if attacking_right else -8.0
            dribble_target = pitch.clamp(self.pos[0] + dx, self.pos[1] + random.uniform(-3, 3))
            nearby_opps = [o for o in opponents if distance(self.pos, o.pos) < config.press_radius]
            action = score_dribble(self, dribble_target, config, nearby_opps)
            if action.score > 0.01:
                actions.append(action)

        # Goalkeeper special: always prefer long pass/kick
        if self.is_goalkeeper and not actions:
            # Safety valve: kick it forward
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
    ) -> Optional[Action]:
        """Choose an action for a player on the ball."""
        actions = self.generate_actions(teammates, opponents, config, pitch, attacking_right)
        if not actions:
            # Fallback: just dribble forward
            dx = 5.0 if attacking_right else -5.0
            return Action(
                ActionType.DRIBBLE,
                pitch.clamp(self.pos[0] + dx, self.pos[1]),
                -1, 0.5, 0.5,
            )
        return select_action_iq_weighted(actions, self.iq_value, config)
