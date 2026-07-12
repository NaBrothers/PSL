"""Python facade for the Rust-only match engine."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import EngineConfig, load_config_from_service
from .rust_bridge import run_match


@dataclass
class MatchResult:
    """Stable result contract consumed by Web and Bot adapters."""

    home_score: int = 0
    away_score: int = 0
    goals: List[Dict] = field(default_factory=list)
    home_stats: Dict = field(default_factory=dict)
    away_stats: Dict = field(default_factory=dict)
    home_player_stats: List[Dict] = field(default_factory=list)
    away_player_stats: List[Dict] = field(default_factory=list)
    home_ratings: List[Dict] = field(default_factory=list)
    away_ratings: List[Dict] = field(default_factory=list)
    replay_url: Optional[str] = None
    trace_id: str = ""


class MatchV2:
    """Compatibility facade that always executes one complete Rust match."""

    def __init__(
        self,
        home_cards: List[Dict],
        away_cards: List[Dict],
        home_formation: str,
        away_formation: str,
        config: Optional[EngineConfig] = None,
        config_service=None,
        seed: Optional[int] = None,
    ):
        self.config = (
            config
            if config is not None
            else load_config_from_service(config_service)
        )
        self.seed = seed
        self.home_cards = home_cards
        self.away_cards = away_cards
        self.home_formation_key = home_formation
        self.away_formation_key = away_formation
        self._result: Optional[MatchResult] = None
        self._replay_data: List[Dict] = []
        self._trace_data: Dict = {}

    def run(self) -> MatchResult:
        """Execute the Rust whole-match entrypoint exactly once."""
        if self._result is not None:
            return self._result

        response = run_match(
            self.home_cards,
            self.away_cards,
            self.home_formation_key,
            self.away_formation_key,
            self.config,
            seed=self.seed if self.seed is not None else random.getrandbits(64),
        )
        self._replay_data = list(response.get("replay", []))
        self._trace_data = dict(response.get("trace", {}))
        self._result = MatchResult(
            home_score=int(response["home_score"]),
            away_score=int(response["away_score"]),
            goals=list(response.get("goals", [])),
            home_stats=dict(response.get("home_stats", {})),
            away_stats=dict(response.get("away_stats", {})),
            home_player_stats=list(response.get("home_player_stats", [])),
            away_player_stats=list(response.get("away_player_stats", [])),
            home_ratings=list(response.get("home_ratings", [])),
            away_ratings=list(response.get("away_ratings", [])),
            replay_url=response.get("replay_url"),
            trace_id=str(response.get("trace_id", "")),
        )
        return self._result

    def get_replay_data(self) -> List[Dict]:
        """Return the Rust replay contract after ``run``."""
        return self._replay_data

    def get_trace(self) -> Dict:
        """Return the Rust trace contract after ``run``."""
        return self._trace_data
