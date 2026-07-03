"""Ball state and flight model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class BallState(Enum):
    HELD = "held"
    IN_FLIGHT = "in_flight"
    DEAD = "dead"  # Out of play, waiting for restart


class FlightType(Enum):
    SHORT_PASS = "pass"
    LONG_PASS = "pass"
    SHOT = "shot"
    CLEARANCE = "pass"


@dataclass
class BallFlight:
    """Represents a ball in flight from one position to another."""
    origin: Tuple[float, float]
    target: Tuple[float, float]
    flight_type: FlightType
    speed: float  # meters per tick
    ticks_total: int
    ticks_elapsed: int = 0
    passer_idx: int = -1
    passer_team: str = ""  # "home" or "away"
    on_target: bool = False  # for shots: whether aimed at goal

    @property
    def progress(self) -> float:
        if self.ticks_total <= 0:
            return 1.0
        return min(1.0, self.ticks_elapsed / self.ticks_total)

    @property
    def is_complete(self) -> bool:
        return self.ticks_elapsed >= self.ticks_total

    @property
    def current_position(self) -> Tuple[float, float]:
        t = self.progress
        x = self.origin[0] + (self.target[0] - self.origin[0]) * t
        y = self.origin[1] + (self.target[1] - self.origin[1]) * t
        return (x, y)


@dataclass
class Ball:
    """Ball state within the match."""
    state: BallState = BallState.DEAD
    position: Tuple[float, float] = (52.5, 34.0)  # center of pitch
    holder_idx: int = -1  # index of player holding ball (-1 if none)
    holder_team: str = ""  # "home" or "away"
    flight: Optional[BallFlight] = None

    # Dead ball info
    dead_reason: str = ""  # "goal_kick", "corner", "throw_in", "kickoff", "goal"
    restart_ticks: int = 0  # ticks until restart
    restart_team: str = ""  # team that gets possession on restart

    def set_held(self, player_idx: int, team: str, position: Tuple[float, float]):
        """Ball is now held by a player."""
        self.state = BallState.HELD
        self.position = position
        self.holder_idx = player_idx
        self.holder_team = team
        self.flight = None

    def set_flight(self, flight: BallFlight):
        """Ball is now in flight."""
        self.state = BallState.IN_FLIGHT
        self.flight = flight
        self.holder_idx = -1
        self.holder_team = ""

    def set_dead(self, reason: str, restart_team: str, restart_ticks: int = 2):
        """Ball is dead (out of play)."""
        self.state = BallState.DEAD
        self.dead_reason = reason
        self.restart_team = restart_team
        self.restart_ticks = restart_ticks
        self.flight = None
        self.holder_idx = -1
        self.holder_team = ""

    def tick_flight(self) -> bool:
        """Advance flight by one tick. Returns True if flight completed."""
        if self.flight is None:
            return False
        self.flight.ticks_elapsed += 1
        self.position = self.flight.current_position
        return self.flight.is_complete

    def tick_dead(self) -> bool:
        """Decrement dead ball timer. Returns True if ready to restart."""
        if self.restart_ticks > 0:
            self.restart_ticks -= 1
        return self.restart_ticks <= 0
