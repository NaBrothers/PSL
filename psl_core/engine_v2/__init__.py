"""PSL Match Engine V2 - Tick-based football simulation (Phase 2).

Usage:
    from psl_core.engine_v2 import MatchV2, MatchResult, EngineConfig

    match = MatchV2(home_cards, away_cards, "442", "433")
    result = match.run()
    replay = match.get_replay_data()
"""

from .match import MatchV2, MatchResult
from .config import EngineConfig, load_config_from_service
from .player import Player, PlayerState
from .team import Team, TeamPhase
from .ball import Ball, BallState, BallOwnership, BallFlight, FlightType
from .pitch import Pitch, Zone
from .actions import ActionType, Action, OffBallAttackAction, OffBallDefendAction
from .physics import distance, move_toward, player_speed
from .vision import get_visible_targets, compute_fov, compute_facing_direction
from .goalkeeper import compute_gk_save_probability, should_rush_out, choose_distribution
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
    "TeamPhase",
    "Ball",
    "BallState",
    "BallOwnership",
    "BallFlight",
    "FlightType",
    "Pitch",
    "Zone",
    "ActionType",
    "Action",
    "OffBallAttackAction",
    "OffBallDefendAction",
    "MatchStats",
    "MatchTrace",
    "compute_player_rating",
    "compute_team_ratings",
    "get_visible_targets",
    "compute_fov",
    "compute_facing_direction",
    "compute_gk_save_probability",
    "should_rush_out",
    "choose_distribution",
]
