"""Match statistics tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MatchStats:
    """Tracks match-level statistics."""

    # Possession tracking
    home_possession_ticks: int = 0
    away_possession_ticks: int = 0
    total_ticks: int = 0

    # Events
    goals: List[Dict] = field(default_factory=list)

    @property
    def home_possession_pct(self) -> float:
        if self.total_ticks == 0:
            return 50.0
        return round(self.home_possession_ticks / self.total_ticks * 100, 1)

    @property
    def away_possession_pct(self) -> float:
        return round(100.0 - self.home_possession_pct, 1)

    def record_possession(self, team_side: str):
        """Record one tick of possession for a team."""
        self.total_ticks += 1
        if team_side == "home":
            self.home_possession_ticks += 1
        elif team_side == "away":
            self.away_possession_ticks += 1
        else:
            # Neutral / dead ball: split equally
            pass

    def record_goal(
        self,
        minute: int,
        team_side: str,
        scorer_name: str,
        assister_name: str,
        scorer_color: str = "",
        assister_color: str = "",
    ):
        """Record a goal."""
        self.goals.append({
            "minute": minute,
            "team_side": team_side,
            "scorer": scorer_name,
            "assister": assister_name,
            "scorer_color": scorer_color,
            "assister_color": assister_color,
        })

    def get_home_stats(self, home_team) -> Dict:
        """Get final home team statistics."""
        team_stats = home_team.get_stats()
        team_stats["possession"] = self.home_possession_pct
        return team_stats

    def get_away_stats(self, away_team) -> Dict:
        """Get final away team statistics."""
        team_stats = away_team.get_stats()
        team_stats["possession"] = self.away_possession_pct
        return team_stats
