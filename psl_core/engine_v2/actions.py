"""Action definitions and scoring for player decisions."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .player import Player
    from .config import EngineConfig
    from .pitch import Pitch


class ActionType(Enum):
    SHORT_PASS = "short_pass"
    LONG_PASS = "long_pass"
    SHOOT = "shoot"
    DRIBBLE = "dribble"
    HOLD = "hold"  # keeper holds


@dataclass
class Action:
    """A candidate action for a player on the ball."""
    action_type: ActionType
    target: Tuple[float, float]  # target position
    target_player_idx: int = -1  # target player index for passes
    score: float = 0.0  # utility score
    success_prob: float = 0.0  # probability of success


def score_short_pass(
    passer: "Player",
    target_player: "Player",
    config: "EngineConfig",
    opponents: List["Player"],
) -> Action:
    """Score a short pass action."""
    from .physics import distance

    dist = distance(passer.pos, target_player.pos)
    if dist < 3.0 or dist > 35.0:
        return Action(ActionType.SHORT_PASS, target_player.pos, target_player.index, 0.0, 0.0)

    # Base probability from Short_Passing ability
    ability = passer.abilities.get("Short_Passing", 50) / 100.0
    base = config.short_pass_base_success

    # Distance penalty
    dist_factor = max(0.3, 1.0 - (dist - 10.0) / 40.0)

    # Opponent proximity penalty (check if any defender is close to pass lane)
    intercept_risk = 0.0
    for opp in opponents:
        opp_dist = distance(opp.pos, target_player.pos)
        if opp_dist < config.interception_radius:
            intercept_risk += 0.1

    success_prob = base * (0.4 + 0.6 * ability) * dist_factor * max(0.3, 1.0 - intercept_risk)
    success_prob = max(0.1, min(0.95, success_prob))

    # Utility: passes forward in attack are more valuable
    forward_bonus = 0.0
    if target_player.pos[0] > passer.pos[0]:
        forward_bonus = 0.2
    score = success_prob + forward_bonus

    return Action(ActionType.SHORT_PASS, target_player.pos, target_player.index, score, success_prob)


def score_long_pass(
    passer: "Player",
    target_player: "Player",
    config: "EngineConfig",
    opponents: List["Player"],
) -> Action:
    """Score a long pass action."""
    from .physics import distance

    dist = distance(passer.pos, target_player.pos)
    if dist < 25.0 or dist > 70.0:
        return Action(ActionType.LONG_PASS, target_player.pos, target_player.index, 0.0, 0.0)

    ability = passer.abilities.get("Long_Passing", 50) / 100.0
    base = config.long_pass_base_success

    dist_factor = max(0.3, 1.0 - (dist - 30.0) / 50.0)
    success_prob = base * (0.4 + 0.6 * ability) * dist_factor
    success_prob = max(0.05, min(0.85, success_prob))

    # Long passes forward are high value
    forward_bonus = 0.0
    if target_player.pos[0] > passer.pos[0]:
        forward_bonus = 0.3
    score = success_prob * 0.8 + forward_bonus

    return Action(ActionType.LONG_PASS, target_player.pos, target_player.index, score, success_prob)


def score_shoot(
    shooter: "Player",
    goal_center: Tuple[float, float],
    config: "EngineConfig",
    pitch: "Pitch",
) -> Action:
    """Score a shot action."""
    from .physics import distance, angle_to_goal

    dist = distance(shooter.pos, goal_center)
    if dist > config.shot_max_distance or dist < 2.0:
        return Action(ActionType.SHOOT, goal_center, -1, 0.0, 0.0)

    # Finishing ability
    finishing = shooter.abilities.get("Finishing", 50) / 100.0
    long_shot = shooter.abilities.get("Long_Shot", 50) / 100.0

    # Use long_shot ability if far, finishing if close
    if dist > 25.0:
        ability = long_shot
    elif dist > 18.0:
        ability = (finishing + long_shot) / 2.0
    else:
        ability = finishing

    # Distance factor: exponential decay beyond ideal distance
    if dist <= config.shot_ideal_distance:
        dist_factor = 1.0
    else:
        excess = dist - config.shot_ideal_distance
        dist_factor = math.exp(-excess / 20.0)

    # Angle factor
    angle = angle_to_goal(shooter.pos, goal_center, config.goal_width)
    angle_factor = min(1.0, angle / 0.3)  # 0.3 radians ~ decent angle

    # On-target probability
    on_target_prob = config.shot_on_target_base * (0.4 + 0.6 * ability) * dist_factor * angle_factor
    on_target_prob = max(0.05, min(0.90, on_target_prob))

    # Overall success = on_target * (1 - save_chance)
    # Save chance is handled during resolution, not scoring
    score = on_target_prob * dist_factor * 2.5  # shots are high-reward

    return Action(ActionType.SHOOT, goal_center, -1, score, on_target_prob)


def score_dribble(
    dribbler: "Player",
    forward_target: Tuple[float, float],
    config: "EngineConfig",
    nearby_opponents: List["Player"],
) -> Action:
    """Score a dribble action."""
    from .physics import distance

    dribbling = dribbler.abilities.get("Dribbling", 50) / 100.0
    base = config.dribble_base_success

    # Opponent pressure
    pressure = 0.0
    for opp in nearby_opponents:
        d = distance(dribbler.pos, opp.pos)
        if d < config.press_radius:
            pressure += max(0, 1.0 - d / config.press_radius) * 0.3

    success_prob = base * (0.4 + 0.6 * dribbling) * max(0.2, 1.0 - pressure)
    success_prob = max(0.1, min(0.90, success_prob))

    score = success_prob * 0.7  # dribbling is moderate reward

    return Action(ActionType.DRIBBLE, forward_target, -1, score, success_prob)


def select_action_iq_weighted(
    actions: List[Action], iq: int, config: "EngineConfig"
) -> Action:
    """Select an action using IQ-weighted softmax.

    Higher IQ = lower temperature = more likely to pick best action.
    Lower IQ = more random selection.
    """
    if not actions:
        raise ValueError("No actions to select from")

    # Filter out zero-score actions
    valid = [a for a in actions if a.score > 0.01]
    if not valid:
        # Fall back to any action
        return random.choice(actions)

    if len(valid) == 1:
        return valid[0]

    # Temperature based on IQ: lower IQ = higher noise
    noise = (100 - max(1, min(99, iq))) / 100.0 * config.iq_noise_factor
    temperature = config.decision_temperature * (0.3 + noise * 2.0)

    # Softmax with temperature
    max_score = max(a.score for a in valid)
    exp_scores = []
    for a in valid:
        exp_val = math.exp((a.score - max_score) / max(0.01, temperature))
        exp_scores.append(exp_val)

    total = sum(exp_scores)
    if total < 1e-10:
        return random.choice(valid)

    probs = [e / total for e in exp_scores]

    # Weighted random selection
    r = random.random()
    cumulative = 0.0
    for i, p in enumerate(probs):
        cumulative += p
        if r <= cumulative:
            return valid[i]

    return valid[-1]
