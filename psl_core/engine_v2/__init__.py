"""Rust-only PSL match engine.

Usage:
    from psl_core.engine_v2 import MatchV2, MatchResult, EngineConfig

    match = MatchV2(home_cards, away_cards, "442", "433")
    result = match.run()
    replay = match.get_replay_data()
"""

from .match import MatchV2, MatchResult
from .config import EngineConfig, TraceConfig, load_config_from_service
from .rust_bridge import RustEngineError

__all__ = [
    "MatchV2",
    "MatchResult",
    "EngineConfig",
    "TraceConfig",
    "load_config_from_service",
    "RustEngineError",
]
