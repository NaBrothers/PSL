"""Serialize team stats to JSON-friendly dict."""


def serialize_team_stats(team) -> dict:
    s = team.stats
    return {
        "possession": s.control,
        "shots": s.shoots,
        "shots_on_target": s.shoots_in_target,
        "passes": s.passes,
        "pass_success_rate": round(s.successful_passes / max(s.passes, 1) * 100, 1),
        "corners": s.corners,
        "offsides": s.offsides,
        "saves": s.saves,
        "xg": round(s.xg, 2),
    }
