"""Pure data types produced by the match engine - no IO dependencies."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MatchEvent:
    minute: int
    second: int
    seq: int
    event_type: str
    text: str
    home_score: int = 0
    away_score: int = 0
    importance: int = 1
    team_side: str = ""  # "home" or "away"
    player_name: str = ""
    xg: float = 0
    target_name: str = ""
    result: str = ""


@dataclass
class TeamStats:
    name: str = ""
    point: int = 0
    control: int = 0
    shoots: int = 0
    shoots_in_target: int = 0
    goals: int = 0
    passes: int = 0
    successful_passes: int = 0
    dribbles: int = 0
    carries: int = 0
    progressive_carries: int = 0
    assists: int = 0
    tackles: int = 0
    tackle_attempts: int = 0
    interceptions: int = 0
    blocks: int = 0
    saves: int = 0
    xg: float = 0
    adjusted_xg: float = 0
    xt: float = 0
    key_passes: int = 0
    box_touches: int = 0
    big_chances: int = 0
    possessions: int = 0
    goals_detailed: list = field(default_factory=list)


@dataclass
class GoalRecord:
    minute: int
    team_side: str  # "home" or "away"
    scorer_name: str
    assister_name: Optional[str] = None


@dataclass
class MatchResult:
    home_stats: TeamStats
    away_stats: TeamStats
    events: List[MatchEvent] = field(default_factory=list)
    timeline: List[GoalRecord] = field(default_factory=list)
    replay_path: Optional[str] = None
