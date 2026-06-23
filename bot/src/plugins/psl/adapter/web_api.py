"""Web API adapter - serializes MatchResult for HTTP/WebSocket clients.

This module will be used by a future web frontend to get match data
as structured JSON rather than formatted text strings.
"""

from engine.types import MatchResult


def serialize_match_result(result: MatchResult) -> dict:
    """Convert MatchResult to a JSON-serializable dictionary."""
    return {
        "home": {
            "name": result.home_stats.name,
            "score": result.home_stats.point,
            "stats": _serialize_stats(result.home_stats),
        },
        "away": {
            "name": result.away_stats.name,
            "score": result.away_stats.point,
            "stats": _serialize_stats(result.away_stats),
        },
        "events": [_serialize_event(ev) for ev in result.events if ev.importance >= 3],
        "timeline": [
            {
                "minute": g.minute,
                "team": g.team_side,
                "scorer": g.scorer_name,
                "assister": g.assister_name,
            }
            for g in result.timeline
        ],
    }


def _serialize_stats(stats) -> dict:
    return {
        "possession": stats.control,
        "shots": stats.shoots,
        "shots_on_target": stats.shoots_in_target,
        "passes": stats.passes,
        "pass_success": stats.successful_passes,
        "dribbles": stats.dribbles,
        "carries": stats.carries,
        "tackles": stats.tackles,
        "interceptions": stats.interceptions,
        "blocks": stats.blocks,
        "saves": stats.saves,
        "xg": round(stats.xg, 2),
        "key_passes": stats.key_passes,
        "box_touches": stats.box_touches,
        "big_chances": stats.big_chances,
    }


def _serialize_event(ev) -> dict:
    return {
        "minute": ev.minute,
        "second": ev.second,
        "type": ev.event_type,
        "text": ev.text,
        "team": ev.team_side,
        "player": ev.player_name,
        "xg": ev.xg,
        "importance": ev.importance,
    }
