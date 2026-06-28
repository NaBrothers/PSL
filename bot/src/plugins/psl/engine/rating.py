"""Post-match player rating system inspired by WhoScored.

Pure formula-driven, position-weighted. Output: 4.0 - 10.0, base 6.0.
"""


def _position_group(position: str) -> str:
    if position == "GK":
        return "GK"
    if position in ("LCB", "CB", "RCB", "LB", "RB", "LWB", "RWB"):
        return "DF"
    if position in ("ST", "CF", "LW", "RW", "LS", "RS"):
        return "FW"
    return "MF"


def compute_player_rating(stats: dict) -> float:
    """Compute a 4.0-10.0 match rating from a player_stat_dict."""
    base = 6.0
    group = _position_group(stats["position"])
    score = base

    goals = stats.get("goals", 0)
    assists = stats.get("assists", 0)
    key_passes = stats.get("key_passes", 0)
    xg = stats.get("xg", 0)
    big_chances_missed = stats.get("big_chances_missed", 0)
    passes = stats.get("passes", 0)
    completed_passes = stats.get("completed_passes", 0)
    progressive_passes = stats.get("progressive_passes", 0)
    passes_into_box = stats.get("passes_into_box", 0)
    successful_take_ons = stats.get("successful_take_ons", 0)
    tackles_won = stats.get("tackles_won", 0)
    interceptions = stats.get("interceptions", 0)
    blocks = stats.get("blocks", 0)
    clearances = stats.get("clearances", 0)
    successful_pressures = stats.get("successful_pressures", 0)
    turnovers = stats.get("turnovers", 0)
    dispossessed = stats.get("dispossessed", 0)
    offsides = stats.get("offsides", 0)
    saves = stats.get("saves", 0)
    goals_conceded = stats.get("goals_conceded", 0)
    goals_prevented = stats.get("goals_prevented", 0)
    shots_on_target = stats.get("shots_on_target", 0)
    progressive_carries = stats.get("progressive_carries", 0)
    carries_into_box = stats.get("carries_into_box", 0)

    if group == "FW":
        score += goals * 1.5
        score += assists * 1.0
        score += key_passes * 0.1
        score += successful_take_ons * 0.06
        score += progressive_carries * 0.02
        score += carries_into_box * 0.05
        if xg > 0 and goals > xg:
            score += 0.3
        score -= big_chances_missed * 0.5
        score -= turnovers * 0.05
        score -= offsides * 0.1

    elif group == "MF":
        score += goals * 1.5
        score += assists * 1.0
        score += key_passes * 0.12
        score += progressive_passes * 0.02
        score += passes_into_box * 0.04
        score += successful_take_ons * 0.05
        score += tackles_won * 0.08
        score += interceptions * 0.08
        score += successful_pressures * 0.03
        score += progressive_carries * 0.02
        if passes > 0:
            pass_pct = completed_passes / passes
            if pass_pct >= 0.9:
                score += 0.2
            elif pass_pct >= 0.85:
                score += 0.1
        score -= turnovers * 0.08
        score -= dispossessed * 0.05

    elif group == "DF":
        score += goals * 1.8
        score += assists * 1.2
        score += tackles_won * 0.12
        score += interceptions * 0.12
        score += blocks * 0.12
        score += clearances * 0.06
        score += successful_pressures * 0.03
        score += key_passes * 0.1
        score += progressive_passes * 0.02
        if passes > 0:
            pass_pct = completed_passes / passes
            if pass_pct >= 0.9:
                score += 0.15
        score -= turnovers * 0.15
        score -= dispossessed * 0.1

    else:  # GK
        score += saves * 0.3
        if goals_prevented > 0:
            score += goals_prevented * 0.6
        elif goals_prevented < 0:
            score += goals_prevented * 0.3
        if goals_conceded == 0:
            score += 1.0
        else:
            score -= goals_conceded * 0.3

    return round(max(4.0, min(10.0, score)), 1)


def compute_match_ratings(home_player_stats: list, away_player_stats: list) -> dict:
    """Compute ratings for all players and determine MOTM.

    Returns:
        {
            "home_ratings": [{"name", "position", "rating"}, ...],
            "away_ratings": [{"name", "position", "rating"}, ...],
            "motm": {"name", "team_side", "rating"},
        }
    """
    home_ratings = []
    for ps in home_player_stats:
        rating = compute_player_rating(ps)
        ps["rating"] = rating
        home_ratings.append({"name": ps["name"], "colored_name": ps.get("colored_name", ps["name"]), "position": ps["position"], "rating": rating})

    away_ratings = []
    for ps in away_player_stats:
        rating = compute_player_rating(ps)
        ps["rating"] = rating
        away_ratings.append({"name": ps["name"], "colored_name": ps.get("colored_name", ps["name"]), "position": ps["position"], "rating": rating})

    all_rated = [(r, "home") for r in home_ratings] + [(r, "away") for r in away_ratings]
    if not all_rated:
        return {
            "home_ratings": [],
            "away_ratings": [],
            "motm": None,
        }
    best = max(all_rated, key=lambda x: x[0]["rating"])

    return {
        "home_ratings": home_ratings,
        "away_ratings": away_ratings,
        "motm": {"name": best[0]["name"], "colored_name": best[0]["colored_name"], "team_side": best[1], "rating": best[0]["rating"]},
    }
