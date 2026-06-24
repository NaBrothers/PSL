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
        "shots_in_box": stats.shots_in_box,
        "shots_outside_box": stats.shots_outside_box,
        "passes": stats.passes,
        "pass_success": stats.successful_passes,
        "progressive_passes": stats.progressive_passes,
        "passes_into_final_third": stats.passes_into_final_third,
        "passes_into_box": stats.passes_into_box,
        "long_passes": stats.long_passes,
        "completed_long_passes": stats.completed_long_passes,
        "crosses": stats.crosses,
        "successful_crosses": stats.successful_crosses,
        "final_third_entries": stats.final_third_entries,
        "box_entries": stats.box_entries,
        "dribbles": stats.dribbles,
        "carries": stats.carries,
        "progressive_carries": stats.progressive_carries,
        "carries_into_final_third": stats.carries_into_final_third,
        "carries_into_box": stats.carries_into_box,
        "take_ons": stats.take_ons,
        "successful_take_ons": stats.successful_take_ons,
        "tackles": stats.tackles,
        "tackle_attempts": stats.tackle_attempts,
        "interceptions": stats.interceptions,
        "blocks": stats.blocks,
        "pressures": stats.pressures,
        "successful_pressures": stats.successful_pressures,
        "defensive_actions": stats.defensive_actions,
        "turnovers": stats.turnovers,
        "offsides": stats.offsides,
        "offsides_forced": stats.offsides_forced,
        "saves": stats.saves,
        "xg": round(stats.xg, 2),
        "npxg": round(stats.npxg, 2),
        "open_play_xg": round(stats.open_play_xg, 2),
        "post_shot_xg": round(stats.post_shot_xg, 2),
        "psxg_faced": round(stats.psxg_faced, 2),
        "goals_prevented": round(stats.goals_prevented, 2),
        "key_passes": stats.key_passes,
        "box_touches": stats.box_touches,
        "big_chances": stats.big_chances,
        "avg_possession_duration": round(stats.avg_possession_duration, 2),
        "player_stats": stats.player_stats,
        "position_stats": stats.position_stats,
        "zone_stats": stats.zone_stats,
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
