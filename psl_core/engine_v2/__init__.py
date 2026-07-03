"""PSL Match Engine V2 - Tick-based football simulation.

Usage:
    from psl_core.engine_v2 import MatchV2, MatchResult, EngineConfig

    match = MatchV2(home_cards, away_cards, "442", "433")
    result = match.run()
    replay = match.get_replay_data()
"""

from .match import MatchV2, MatchResult
from .config import EngineConfig, load_config_from_service
from .player import Player, PlayerState
from .team import Team
from .ball import Ball, BallState, BallFlight, FlightType
from .pitch import Pitch, Zone
from .actions import ActionType, Action
from .physics import distance, move_toward, player_speed
from .stats import MatchStats
from .trace import MatchTrace
from .rating import compute_player_rating, compute_team_ratings
from .replay_adapter import build_header, build_frame

__all__ = [
    "MatchV2",
    "MatchResult",
    "EngineConfig",
    "load_config_from_service",
    "Player",
    "PlayerState",
    "Team",
    "Ball",
    "BallState",
    "BallFlight",
    "FlightType",
    "Pitch",
    "Zone",
    "ActionType",
    "Action",
    "MatchStats",
    "MatchTrace",
    "compute_player_rating",
    "compute_team_ratings",
]
