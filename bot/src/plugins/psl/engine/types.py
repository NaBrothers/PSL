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
    shots_in_box: int = 0
    shots_outside_box: int = 0
    passes: int = 0
    successful_passes: int = 0
    progressive_passes: int = 0
    passes_into_final_third: int = 0
    passes_into_box: int = 0
    long_passes: int = 0
    completed_long_passes: int = 0
    short_passes: int = 0
    completed_short_passes: int = 0
    crosses: int = 0
    successful_crosses: int = 0
    final_third_entries: int = 0
    box_entries: int = 0
    dribbles: int = 0
    carries: int = 0
    progressive_carries: int = 0
    carries_into_final_third: int = 0
    carries_into_box: int = 0
    take_ons: int = 0
    successful_take_ons: int = 0
    assists: int = 0
    tackles: int = 0
    tackle_attempts: int = 0
    interceptions: int = 0
    blocks: int = 0
    clearances: int = 0
    pressures: int = 0
    successful_pressures: int = 0
    defensive_actions: int = 0
    turnovers: int = 0
    offsides: int = 0
    offsides_forced: int = 0
    saves: int = 0
    xg: float = 0
    open_play_xg: float = 0
    set_piece_xg: float = 0
    npxg: float = 0
    post_shot_xg: float = 0
    psxg_faced: float = 0
    goals_prevented: float = 0
    adjusted_xg: float = 0
    xt: float = 0
    key_passes: int = 0
    box_touches: int = 0
    big_chances: int = 0
    possessions: int = 0
    avg_possession_duration: float = 0
    goals_detailed: list = field(default_factory=list)
    player_stats: list = field(default_factory=list)
    position_stats: dict = field(default_factory=dict)
    zone_stats: dict = field(default_factory=dict)


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
