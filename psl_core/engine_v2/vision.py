"""Player vision system (Phase 2): IQ-linked field of view for pass filtering."""

from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING

from .physics import angle_between_points, is_in_fov

if TYPE_CHECKING:
    from .player import Player
    from .config import EngineConfig


def compute_facing_direction(
    player_pos: Tuple[float, float],
    ball_pos: Tuple[float, float],
    last_action_target: Tuple[float, float] = None,
) -> float:
    """Compute player facing direction in degrees.

    Defaults to facing the ball. If the player just performed an action,
    they face toward the action target briefly.
    """
    target = last_action_target if last_action_target else ball_pos
    return angle_between_points(player_pos, target)


def compute_fov(iq: int, config: "EngineConfig") -> float:
    """Compute player field of view in degrees based on IQ.

    FOV = base_fov + IQ * bonus_factor
    """
    return config.vision_base_fov + iq * config.vision_iq_bonus_factor


def get_visible_targets(
    passer: "Player",
    teammates: List["Player"],
    ball_pos: Tuple[float, float],
    config: "EngineConfig",
) -> List["Player"]:
    """Filter teammates to only those within the passer's field of view.

    Args:
        passer: The player making the pass.
        teammates: All teammates.
        ball_pos: Current ball position for facing calculation.
        config: Engine configuration.

    Returns:
        List of teammates visible to the passer.
    """
    facing = compute_facing_direction(passer.pos, ball_pos)
    fov = compute_fov(passer.iq_value, config)
    half_fov = fov / 2.0

    visible = []
    for tm in teammates:
        if tm.index == passer.index:
            continue
        angle_to_tm = angle_between_points(passer.pos, tm.pos)
        if is_in_fov(facing, angle_to_tm, half_fov):
            visible.append(tm)

    # Safety: always see at least a couple of teammates (peripheral awareness)
    # If no one visible, allow all (to prevent stuck states)
    if not visible:
        return [tm for tm in teammates if tm.index != passer.index]

    return visible


def is_target_visible(
    passer: "Player",
    target_pos: Tuple[float, float],
    ball_pos: Tuple[float, float],
    config: "EngineConfig",
) -> bool:
    """Check if a specific target position is within the passer's FOV."""
    facing = compute_facing_direction(passer.pos, ball_pos)
    fov = compute_fov(passer.iq_value, config)
    half_fov = fov / 2.0
    angle_to_target = angle_between_points(passer.pos, target_pos)
    return is_in_fov(facing, angle_to_target, half_fov)
