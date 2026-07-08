"""Player vision system (Phase 2): IQ-linked field of view for pass perception."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, TYPE_CHECKING

from .physics import angle_between_points, angle_diff, distance, is_in_fov

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

    Average-IQ players use the base FOV; higher IQ widens the scan cone.
    """
    fov = config.vision_base_fov + (iq - 80) * config.vision_iq_bonus_factor
    return max(150.0, min(240.0, fov))


def compute_vision_distance(iq: int, config: "EngineConfig") -> float:
    """Compute how far a player can evaluate pass targets."""
    base = getattr(config, "vision_base_distance", 42.0)
    iq_bonus = getattr(config, "vision_iq_distance_bonus_factor", 0.35)
    max_distance = getattr(config, "vision_max_distance", 65.0)
    return max(24.0, min(max_distance, base + max(0, iq - 70) * iq_bonus))


def compute_player_facing(
    passer: "Player",
    attacking_right: bool,
) -> float:
    """Use live body orientation, with attack direction as fallback."""
    facing = getattr(passer, "facing_direction", 0.0)
    if abs(facing) > 1e-3:
        return facing
    return 0.0 if attacking_right else 180.0


@dataclass(frozen=True)
class VisionContext:
    """Per-pass perception envelope for candidate generation and trace."""

    facing: float
    fov: float
    half_fov: float
    max_distance: float

    def confidence(self, origin: Tuple[float, float], target: Tuple[float, float]) -> float:
        """Continuous perception confidence in [0, 1]."""
        d = distance(origin, target)
        if d <= 0.1:
            return 1.0
        target_angle = angle_between_points(origin, target)
        diff = abs(angle_diff(self.facing, target_angle))
        angle_conf = 1.0 - max(0.0, diff - self.half_fov * 0.65) / max(1.0, self.half_fov * 0.70)
        dist_conf = 1.0 - max(0.0, d - self.max_distance * 0.72) / max(1.0, self.max_distance * 0.45)
        return max(0.0, min(1.0, min(angle_conf, dist_conf)))

    def visible(self, origin: Tuple[float, float], target: Tuple[float, float]) -> bool:
        return self.confidence(origin, target) > 0.0


def build_vision_context(
    passer: "Player",
    config: "EngineConfig",
    attacking_right: bool,
) -> VisionContext:
    fov = compute_fov(passer.iq_value, config)
    return VisionContext(
        facing=compute_player_facing(passer, attacking_right),
        fov=fov,
        half_fov=fov / 2.0,
        max_distance=compute_vision_distance(passer.iq_value, config),
    )


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
