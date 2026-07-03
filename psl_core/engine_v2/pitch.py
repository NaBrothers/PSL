"""Pitch geometry, zones, and coordinate helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from .config import EngineConfig


class Zone(Enum):
    """Pitch zones for tactical logic."""
    OWN_BOX = "own_box"
    OWN_HALF = "own_half"
    MIDFIELD = "midfield"
    OPP_HALF = "opp_half"
    OPP_BOX = "opp_box"


@dataclass
class Pitch:
    """Pitch geometry and coordinate helpers.

    Coordinate system:
    - x: along the length (0 = left goal line, LENGTH = right goal line)
    - y: across the width (0 = bottom touchline, WIDTH = top touchline)
    - Home attacks toward x=LENGTH in first half
    - Away attacks toward x=0 in first half
    """

    config: EngineConfig

    @property
    def length(self) -> float:
        return self.config.pitch_length

    @property
    def width(self) -> float:
        return self.config.pitch_width

    @property
    def center(self) -> Tuple[float, float]:
        return (self.length / 2.0, self.width / 2.0)

    @property
    def goal_y_min(self) -> float:
        return self.config.goal_y_min()

    @property
    def goal_y_max(self) -> float:
        return self.config.goal_y_max()

    def home_goal_center(self) -> Tuple[float, float]:
        """Center of home team's goal (what they defend)."""
        return (0.0, self.width / 2.0)

    def away_goal_center(self) -> Tuple[float, float]:
        """Center of away team's goal (what they defend)."""
        return (self.length, self.width / 2.0)

    def is_in_goal(self, x: float, y: float, attacking_right: bool) -> bool:
        """Check if position is inside the goal area."""
        if attacking_right:
            return x >= self.length and self.goal_y_min <= y <= self.goal_y_max
        else:
            return x <= 0 and self.goal_y_min <= y <= self.goal_y_max

    def is_out_of_bounds(self, x: float, y: float) -> bool:
        """Check if ball is out of bounds."""
        return x < 0 or x > self.length or y < 0 or y > self.width

    def is_over_goal_line(self, x: float) -> bool:
        """Check if x is past a goal line."""
        return x <= 0 or x >= self.length

    def is_over_touchline(self, y: float) -> bool:
        """Check if y is past a touchline."""
        return y <= 0 or y >= self.width

    def get_zone(self, x: float, attacking_right: bool) -> Zone:
        """Get the tactical zone for a given x coordinate.

        Args:
            x: x-coordinate on pitch
            attacking_right: if True, team attacks toward x=LENGTH
        """
        # Normalize x so 0 = own goal line, LENGTH = opponent goal line
        nx = x if attacking_right else (self.length - x)
        pct = nx / self.length

        if pct < 0.16:
            return Zone.OWN_BOX
        elif pct < 0.40:
            return Zone.OWN_HALF
        elif pct < 0.60:
            return Zone.MIDFIELD
        elif pct < 0.84:
            return Zone.OPP_HALF
        else:
            return Zone.OPP_BOX

    def clamp(self, x: float, y: float) -> Tuple[float, float]:
        """Clamp coordinates to within pitch bounds."""
        x = max(0.5, min(self.length - 0.5, x))
        y = max(0.5, min(self.width - 0.5, y))
        return (x, y)

    def formation_to_pitch(
        self, coord: Tuple[float, float], attacking_right: bool
    ) -> Tuple[float, float]:
        """Convert formation percentage coordinates to pitch coordinates.

        Formation coords from constants: (x_pct, y_pct) where:
        - x_pct is across width (0-68 range, mapped from percentage)
        - y_pct is along length (100 = own goal, 0 = opponent goal)

        We map these to pitch coordinates with proper orientation.
        """
        fx, fy = coord
        # fx is percentage across width (roughly 0-68 scale based on actual values)
        # fy is percentage along length (100=back/GK, 0/20=front/attackers)

        # Normalize: fx appears to be in ~14-56 range for a 68-wide field
        # Actually these look like they map directly to pitch width
        pitch_y = fx  # fx maps to y (across width)

        # fy: 100=own goal, 20=near opponent goal
        # Convert to distance from own goal line as fraction
        # 100 -> near own goal (x near 0 or LENGTH depending on side)
        # 20 -> near opponent goal
        depth_pct = (100.0 - fy) / 100.0  # 0 = own goal, 0.8 = opponent end

        if attacking_right:
            pitch_x = depth_pct * self.length
        else:
            pitch_x = (1.0 - depth_pct) * self.length

        return self.clamp(pitch_x, pitch_y)
