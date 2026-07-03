"""Physics helpers: movement, distance, angle calculations."""

from __future__ import annotations

import math
from typing import Tuple


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Euclidean distance between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)


def direction(
    origin: Tuple[float, float], target: Tuple[float, float]
) -> Tuple[float, float]:
    """Unit direction vector from origin to target."""
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1e-6:
        return (0.0, 0.0)
    return (dx / dist, dy / dist)


def move_toward(
    pos: Tuple[float, float],
    target: Tuple[float, float],
    max_dist: float,
) -> Tuple[float, float]:
    """Move from pos toward target by at most max_dist meters."""
    dx = target[0] - pos[0]
    dy = target[1] - pos[1]
    dist = math.sqrt(dx * dx + dy * dy)
    if dist <= max_dist or dist < 1e-6:
        return target
    ratio = max_dist / dist
    return (pos[0] + dx * ratio, pos[1] + dy * ratio)


def interpolate(
    p1: Tuple[float, float], p2: Tuple[float, float], t: float
) -> Tuple[float, float]:
    """Linear interpolation between two points. t in [0, 1]."""
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def angle_to_goal(
    pos: Tuple[float, float], goal_center: Tuple[float, float], goal_width: float
) -> float:
    """Calculate the angle subtended by the goal from the given position (radians)."""
    dx = goal_center[0] - pos[0]
    dy_top = goal_center[1] + goal_width / 2.0 - pos[1]
    dy_bot = goal_center[1] - goal_width / 2.0 - pos[1]

    angle_top = math.atan2(dy_top, dx)
    angle_bot = math.atan2(dy_bot, dx)

    return abs(angle_top - angle_bot)


def player_speed(speed_ability: int, max_speed: float, min_speed: float) -> float:
    """Calculate player movement speed (meters per tick) from Speed ability (1-99)."""
    t = max(0, min(99, speed_ability)) / 99.0
    return min_speed + t * (max_speed - min_speed)


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, value))


# =========================================================================
# Phase 2: Angle/direction utilities
# =========================================================================

def angle_between_points(
    origin: Tuple[float, float], target: Tuple[float, float]
) -> float:
    """Get angle in degrees from origin to target (0=right, 90=up, etc.)."""
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    return math.degrees(math.atan2(dy, dx))


def angle_diff(a1: float, a2: float) -> float:
    """Signed angle difference in degrees, normalized to [-180, 180]."""
    diff = a2 - a1
    while diff > 180.0:
        diff -= 360.0
    while diff < -180.0:
        diff += 360.0
    return diff


def is_in_fov(
    facing_angle: float,
    target_angle: float,
    half_fov: float,
) -> bool:
    """Check if target_angle is within half_fov of facing_angle (all in degrees)."""
    diff = abs(angle_diff(facing_angle, target_angle))
    return diff <= half_fov


def midpoint(p1: Tuple[float, float], p2: Tuple[float, float]) -> Tuple[float, float]:
    """Midpoint between two points."""
    return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)


def point_along(
    origin: Tuple[float, float], angle_deg: float, dist: float
) -> Tuple[float, float]:
    """Get point at given distance and angle from origin."""
    rad = math.radians(angle_deg)
    return (origin[0] + dist * math.cos(rad), origin[1] + dist * math.sin(rad))
