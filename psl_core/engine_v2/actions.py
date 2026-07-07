"""Action definitions and scoring for player decisions (Phase 2).

All actions use the unified scoring framework:
    score = base_score(situation, abilities) * tactic_weight[phase][action] * role_modifier[action]

For Phase 2, tactic_weight and role_modifier default to 1.0.
The multiplication is present so Phase 3 can fill them.

Decision model (reward-driven):
- All on-ball candidates (carry, pass, shoot, cross, clear) are scored simultaneously.
- The highest-scoring candidate is chosen (with IQ-based softmax temperature).
- No threshold gates or forced decisions -- behavior emerges from score competition.
- The ActionType enum retains CARRY/HOLD for trace logging and backward compatibility.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, TYPE_CHECKING

from .decision import iq_temperature_factor

if TYPE_CHECKING:
    from .player import Player
    from .config import EngineConfig
    from .pitch import Pitch


class ActionType(Enum):
    SHORT_PASS = "short_pass"
    LONG_PASS = "long_pass"
    SHOOT = "shoot"
    DRIBBLE = "dribble"
    CARRY = "carry"   # retained for trace logging; no longer a player "decision"
    CROSS = "cross"
    HOLD = "hold"     # retained for trace logging; no longer a player "decision"


class OffBallAttackAction(Enum):
    HOLD_POSITION = "hold_position"
    FIND_SPACE = "find_space"
    MAKE_RUN = "make_run"
    DROP_DEEP = "drop_deep"
    GO_WIDE = "go_wide"


class OffBallDefendAction(Enum):
    PRESS = "press"
    BLOCK_LANE = "block_lane"
    MAN_MARK = "man_mark"
    COVER = "cover"
    HOLD_SHAPE = "hold_shape"


@dataclass
class Action:
    """A candidate action for a player on the ball."""
    action_type: ActionType
    target: Tuple[float, float]  # target position
    target_player_idx: int = -1  # target player index for passes
    score: float = 0.0  # utility score
    success_prob: float = 0.0  # probability of success


# =========================================================================
# Tactic weight / role modifier stubs (Phase 3 fills these)
# =========================================================================

def get_tactic_weight(phase: str, action_type: str) -> float:
    """Get tactic weight for an action in a given phase.

    Phase 2: always returns 1.0.
    Phase 3 will implement per-tactic lookup tables.
    """
    return 1.0


def get_role_modifier(position: str, action_type: str) -> float:
    """Get role modifier for a player position performing an action.

    Phase 2: always returns 1.0.
    Phase 3 will implement per-role modifiers.
    """
    return 1.0


def apply_unified_scoring(base_score: float, phase: str, action_type: str, position: str) -> float:
    """Apply the unified scoring framework.

    score = base_score * tactic_weight[phase][action] * role_modifier[action]
    """
    tactic_w = get_tactic_weight(phase, action_type)
    role_m = get_role_modifier(position, action_type)
    return base_score * tactic_w * role_m


# =========================================================================
# On-ball action scoring
# =========================================================================

def score_short_pass(
    passer: "Player",
    target_player: "Player",
    config: "EngineConfig",
    opponents: List["Player"],
    phase: str = "attacking",
) -> Action:
    """Score a short pass action."""
    from .physics import distance

    dist = distance(passer.pos, target_player.pos)
    if dist < 3.0 or dist > 35.0:
        return Action(ActionType.SHORT_PASS, target_player.pos, target_player.index, 0.0, 0.0)

    # Base probability from Short_Passing ability
    ability = passer.abilities.get("Short_Passing", 50) / 100.0
    base = config.short_pass_base_success

    # Distance penalty (gentle - real players can pass 30m accurately)
    dist_factor = max(0.5, 1.0 - (dist - 15.0) / 60.0)

    # Opponent proximity penalty (check if any defender is close to pass lane)
    intercept_risk = 0.0
    for opp in opponents:
        opp_dist = distance(opp.pos, target_player.pos)
        if opp_dist < config.interception_radius:
            intercept_risk += 0.1

    success_prob = base * (0.4 + 0.6 * ability) * dist_factor * max(0.3, 1.0 - intercept_risk)
    success_prob = max(0.1, min(0.95, success_prob))

    # Score = success_prob * target value
    # Target value based on: role (attacker > mid > def) + forward progress
    # This naturally makes forward passes to attackers most valuable
    role_value = 0.5  # default
    if target_player.is_goalkeeper:
        role_value = 0.05
    elif target_player.is_defender:
        role_value = 0.25
    elif target_player.is_midfielder:
        role_value = 0.55
    elif target_player.is_attacker:
        role_value = 0.85

    # Forward progress bonus (relative to passer)
    dx = target_player.pos[0] - passer.pos[0]
    progress_bonus = max(0, dx / 50.0) * 0.3  # up to +0.3 for 50m forward

    position_value = min(1.0, role_value + progress_bonus)

    # Penalty for skipping positional lines (def->mid->fwd progression)
    passer_line = 0 if passer.is_goalkeeper else 1 if passer.is_defender else 2 if passer.is_midfielder else 3
    target_line = 0 if target_player.is_goalkeeper else 1 if target_player.is_defender else 2 if target_player.is_midfielder else 3
    line_skip = target_line - passer_line
    if line_skip > 1:  # skipping a line (e.g., def directly to fwd)
        position_value *= 0.6  # penalty for bypassing midfield

    raw_score = success_prob * position_value

    # Apply unified framework
    score = apply_unified_scoring(raw_score, phase, "short_pass", passer.position)

    return Action(ActionType.SHORT_PASS, target_player.pos, target_player.index, score, success_prob)


def score_long_pass(
    passer: "Player",
    target_player: "Player",
    config: "EngineConfig",
    opponents: List["Player"],
    phase: str = "attacking",
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

    # Penalty for skipping positional lines (def->mid->fwd progression)
    passer_line = 0 if passer.is_goalkeeper else 1 if passer.is_defender else 2 if passer.is_midfielder else 3
    target_line = 0 if target_player.is_goalkeeper else 1 if target_player.is_defender else 2 if target_player.is_midfielder else 3
    line_skip = target_line - passer_line
    line_skip_penalty = 1.0
    if line_skip > 1:  # skipping a line (e.g., def directly to fwd)
        line_skip_penalty = 0.6  # penalty for bypassing midfield

    raw_score = (success_prob * 0.7 + forward_bonus) * line_skip_penalty
    score = apply_unified_scoring(raw_score, phase, "long_pass", passer.position)

    return Action(ActionType.LONG_PASS, target_player.pos, target_player.index, score, success_prob)


def score_shoot(
    shooter: "Player",
    goal_center: Tuple[float, float],
    config: "EngineConfig",
    pitch: "Pitch",
    phase: str = "attacking",
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

    raw_score = on_target_prob * dist_factor * 4.5  # shots are high-reward, must exceed release threshold
    score = apply_unified_scoring(raw_score, phase, "shoot", shooter.position)

    return Action(ActionType.SHOOT, goal_center, -1, score, on_target_prob)


def score_carry(
    carrier: "Player",
    forward_target: Tuple[float, float],
    config: "EngineConfig",
    nearby_opponents: List["Player"],
    attacking_right: bool,
    phase: str = "attacking",
) -> Action:
    """Score a CARRY action (open space forward movement).

    CARRY is triggered when no defender is ahead within press_radius.
    Success rate: 85-95% (Speed-driven).
    Displacement: 8-15m (Speed-driven).
    """
    from .physics import distance

    # Check if there's a defender ahead blocking the path
    has_defender_ahead = False
    for opp in nearby_opponents:
        d = distance(carrier.pos, opp.pos)
        if d < config.carry_defender_check_radius:
            # Check if defender is in front (in carrying direction)
            if attacking_right:
                if opp.pos[0] > carrier.pos[0] and abs(opp.pos[1] - carrier.pos[1]) < 8.0:
                    has_defender_ahead = True
                    break
            else:
                if opp.pos[0] < carrier.pos[0] and abs(opp.pos[1] - carrier.pos[1]) < 8.0:
                    has_defender_ahead = True
                    break

    if has_defender_ahead:
        # Can't carry in open space - defender blocking
        return Action(ActionType.CARRY, forward_target, -1, 0.0, 0.0)

    # Speed-driven success probability (85-95%)
    speed = carrier.abilities.get("Speed", 50) / 100.0
    success_prob = config.carry_base_success * (0.9 + 0.1 * speed)
    success_prob = max(0.80, min(0.97, success_prob))

    # Score based on forward progress potential
    raw_score = success_prob * 1.1

    # Bonus if moving toward goal
    score = apply_unified_scoring(raw_score, phase, "carry", carrier.position)

    return Action(ActionType.CARRY, forward_target, -1, score, success_prob)


def score_dribble(
    dribbler: "Player",
    forward_target: Tuple[float, float],
    config: "EngineConfig",
    nearby_opponents: List["Player"],
    phase: str = "attacking",
) -> Action:
    """Score a DRIBBLE action (1v1 take-on under pressure).

    DRIBBLE is only scored when a defender is pressing.
    Dribbling vs Tackling contest. Success: 40-70%.
    Displacement: 3-5m past beaten defender.
    """
    from .physics import distance

    if not nearby_opponents:
        return Action(ActionType.DRIBBLE, forward_target, -1, 0.0, 0.0)

    # Find closest opponent (the one being dribbled past)
    closest_opp = None
    closest_dist = float("inf")
    for opp in nearby_opponents:
        d = distance(dribbler.pos, opp.pos)
        if d < closest_dist:
            closest_dist = d
            closest_opp = opp

    if closest_opp is None or closest_dist > config.press_radius:
        return Action(ActionType.DRIBBLE, forward_target, -1, 0.0, 0.0)

    # Dribbling vs Tackling contest
    dribbling = dribbler.abilities.get("Dribbling", 50) / 100.0
    tackling = closest_opp.abilities.get("Tackling", 50) / 100.0

    # Success probability: 40-70% range
    success_prob = 0.40 + 0.30 * (dribbling / (dribbling + tackling + 0.01))
    success_prob = max(0.35, min(0.72, success_prob))

    raw_score = success_prob * 0.65  # dribbling is risky
    score = apply_unified_scoring(raw_score, phase, "dribble", dribbler.position)

    return Action(ActionType.DRIBBLE, forward_target, -1, score, success_prob)


def score_cross(
    crosser: "Player",
    target_pos: Tuple[float, float],
    config: "EngineConfig",
    opponents: List["Player"],
    attacking_right: bool,
    pitch: "Pitch",
    phase: str = "attacking",
) -> Action:
    """Score a CROSS action (wide position aerial delivery into box).

    Cross is from wide positions near byline, uses Long_Passing for accuracy.
    """
    from .physics import distance

    # Check if player is in crossing position (wide)
    x_progress = crosser.pos[0] / pitch.length if attacking_right else (1.0 - crosser.pos[0] / pitch.length)
    y_from_center = abs(crosser.pos[1] - pitch.width / 2.0)
    is_wide = (crosser.pos[1] < 15.0 or crosser.pos[1] > pitch.width - 15.0)

    # cross_zone_x_threshold gate removed: cross score is now naturally determined
    # by whether there's a good target in the box. A low x_progress reduces score
    # organically via the success_prob distance factor below.
    if not is_wide:
        return Action(ActionType.CROSS, target_pos, -1, 0.0, 0.0)

    # Long_Passing determines cross accuracy
    long_passing = crosser.abilities.get("Long_Passing", 50) / 100.0
    success_prob = config.cross_base_success * (0.5 + 0.5 * long_passing)
    success_prob = max(0.25, min(0.80, success_prob))

    raw_score = success_prob * 1.2  # crosses are high-value in attacking position
    score = apply_unified_scoring(raw_score, phase, "cross", crosser.position)

    return Action(ActionType.CROSS, target_pos, -1, score, success_prob)


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
    temperature = config.decision_temperature * iq_temperature_factor(
        iq,
        floor=0.3,
        low_iq_range=2.0 * config.iq_noise_factor,
        elite_discount=0.30,
    )

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
