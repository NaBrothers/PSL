"""Replay adapter: convert engine state to v1-compatible replay JSONL format."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .player import Player
from .team import Team


def build_header(
    home_team: Team,
    away_team: Team,
    home_formation: str,
    away_formation: str,
    pitch_width: float,
    pitch_length: float,
) -> Dict[str, Any]:
    """Build the replay header line."""
    return {
        "type": "header",
        "home": {
            "name": home_team.name,
            "players": [
                {"name": p.name, "pos": p.position, "color": p.color}
                for p in home_team.players
            ],
        },
        "away": {
            "name": away_team.name,
            "players": [
                {"name": p.name, "pos": p.position, "color": p.color}
                for p in away_team.players
            ],
        },
        "formation_home": home_formation,
        "formation_away": away_formation,
        "field": {"width": pitch_width, "length": pitch_length},
    }


def build_frame(
    tick: int,
    tick_duration: float,
    half: int,
    home_team: Team,
    away_team: Team,
    ball_holder_idx: int,
    ball_team: Optional[str],
    home_score: int,
    away_score: int,
    ball_flight: Optional[Dict] = None,
    event_text: Optional[str] = None,
    pause_ms: Optional[int] = None,
    cut: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build a single replay frame."""
    t = round(tick * tick_duration, 1)

    frame: Dict[str, Any] = {
        "type": "frame",
        "t": t,
        "half": half,
        "home": [[round(p.pos[1], 1), round(p.pos[0], 1)] for p in home_team.players],
        "away": [[round(p.pos[1], 1), round(p.pos[0], 1)] for p in away_team.players],
        "ball_holder": ball_holder_idx if ball_holder_idx >= 0 else None,
        "ball_team": ball_team if ball_team else None,
        "score": [home_score, away_score],
        "ball_flight": ball_flight,
        "event_text": event_text,
        "pause_ms": pause_ms,
        "cut": cut,
    }

    return frame


def build_ball_flight_data(
    from_pos: Tuple[float, float],
    to_pos: Tuple[float, float],
    flight_type: str,
    on_target: bool = False,
) -> Dict[str, Any]:
    """Build ball_flight data for a frame."""
    return {
        "from": [round(from_pos[1], 1), round(from_pos[0], 1)],
        "to": [round(to_pos[1], 1), round(to_pos[0], 1)],
        "type": flight_type,
        "on_target": on_target,
    }
