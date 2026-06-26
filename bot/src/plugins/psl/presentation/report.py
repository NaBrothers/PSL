"""Generate narrative match report from MatchResult.

Input: MatchResult + CommentaryRenderer
Output: report text string
"""

from engine.types import MatchResult
from engine.commentary import CommentaryRenderer
from engine.rating import compute_match_ratings


def _position_group(position: str) -> str:
    if position == "GK":
        return "goalkeeper"
    if position in ("LCB", "CB", "RCB", "LB", "RB", "LWB", "RWB"):
        return "defender"
    if position in ("ST", "CF", "LW", "RW", "LS", "RS"):
        return "forward"
    return "midfielder"


def _build_rating_paragraph(ratings: dict, player_stats_home: list, player_stats_away: list, commentary: CommentaryRenderer) -> str:
    parts = []
    motm = ratings["motm"]
    if not motm:
        return ""
    motm_name = motm["name"]
    motm_colored = motm.get("colored_name", motm_name)
    motm_rating = motm["rating"]
    motm_side = motm["team_side"]

    all_stats = player_stats_home if motm_side == "home" else player_stats_away
    motm_stats = next((ps for ps in all_stats if ps["name"] == motm_name), None)

    if motm_stats:
        group = _position_group(motm_stats["position"])
        goals = motm_stats.get("goals", 0)
        saves = motm_stats.get("saves", 0)

        if group == "forward":
            key = "motm_forward" if goals > 0 else "motm_forward_no_goal"
            parts.append(commentary.render("rating", key,
                player=motm_colored, goals=str(goals), rating=str(motm_rating)))
        elif group == "midfielder":
            parts.append(commentary.render("rating", "motm_midfielder",
                player=motm_colored, rating=str(motm_rating)))
        elif group == "defender":
            parts.append(commentary.render("rating", "motm_defender",
                player=motm_colored, rating=str(motm_rating)))
        else:
            parts.append(commentary.render("rating", "motm_goalkeeper",
                player=motm_colored, saves=str(saves), rating=str(motm_rating)))

    all_rated = ratings["home_ratings"] + ratings["away_ratings"]
    high_players = [p for p in all_rated if p["rating"] >= 7.5 and p["name"] != motm_name]
    high_players.sort(key=lambda x: x["rating"], reverse=True)
    for p in high_players[:2]:
        group = _position_group(p["position"])
        key = f"high_rating_{group}"
        text = commentary.render("rating", key, player=p.get("colored_name", p["name"]), rating=str(p["rating"]))
        if text:
            parts.append(text)

    low_players = [p for p in all_rated if p["rating"] < 5.5]
    low_players.sort(key=lambda x: x["rating"])
    for p in low_players[:1]:
        group = _position_group(p["position"])
        key = f"low_rating_{group}"
        text = commentary.render("rating", key, player=p.get("colored_name", p["name"]), rating=str(p["rating"]))
        if text:
            parts.append(text)

    return " ".join(parts)


def build_report(result: MatchResult, commentary: CommentaryRenderer) -> str:
    home = result.home_stats
    away = result.away_stats
    home_name = home.name
    away_name = away.name
    total_control = home.control + away.control
    home_ctrl = round(home.control * 100 / total_control, 1) if total_control else 50
    away_ctrl = round(away.control * 100 / total_control, 1) if total_control else 50
    score = f"{home.point}:{away.point}"

    paragraphs = []

    if home.point == away.point:
        key = "result_draw_0" if home.point == 0 else "result_draw"
    elif home.point > away.point:
        diff = home.point - away.point
        key = "result_home_big_win" if diff >= 3 else ("result_home_win_2" if diff == 2 else "result_home_win_1")
    else:
        diff = away.point - home.point
        key = "result_away_big_win" if diff >= 3 else ("result_away_win_2" if diff == 2 else "result_away_win_1")
    paragraphs.append(commentary.render("narrative", key, home=home_name, away=away_name, score=score))

    shots = f"{home.shoots}:{away.shoots}"
    sot = f"{home.shoots_in_target}:{away.shoots_in_target}"
    if home_ctrl > 55:
        paragraphs.append(commentary.render("narrative", "control_dominant",
            dominant=home_name, other=away_name, ctrl=str(home_ctrl), shots=shots, sot=sot))
    elif away_ctrl > 55:
        paragraphs.append(commentary.render("narrative", "control_dominant",
            dominant=away_name, other=home_name, ctrl=str(away_ctrl), shots=shots, sot=sot))
    else:
        paragraphs.append(commentary.render("narrative", "control_balanced",
            home_ctrl=str(home_ctrl), away_ctrl=str(away_ctrl), shots=shots, sot=sot))

    goal_events = [ev for ev in result.events if ev.event_type == "goal"]
    if goal_events:
        parts = []
        for ev in goal_events:
            if ev.target_name:
                parts.append(commentary.render("narrative", "goal_desc",
                    minute=str(ev.minute), scorer=ev.player_name, assister=ev.target_name))
            else:
                parts.append(commentary.render("narrative", "goal_desc_solo",
                    minute=str(ev.minute), scorer=ev.player_name))
        paragraphs.append(" ".join(parts))
    else:
        shots_total = home.shoots + away.shoots
        if shots_total > 20:
            paragraphs.append(commentary.render("narrative", "goals_none_many_shots", total_shots=str(shots_total)))
        else:
            paragraphs.append(commentary.render("narrative", "goals_none_few_shots"))

    saves_events = [ev for ev in result.events if ev.event_type == "save"]
    if saves_events:
        keeper_saves = {}
        for ev in saves_events:
            name = ev.target_name or ev.player_name
            if name:
                keeper_saves[name] = keeper_saves.get(name, 0) + 1
        if keeper_saves:
            best_keeper = max(keeper_saves, key=keeper_saves.get)
            best_saves = keeper_saves[best_keeper]
            if best_saves >= 3:
                paragraphs.append(commentary.render("narrative", "keeper_heroic", keeper=best_keeper, saves=str(best_saves)))

    home_xg = round(home.xg, 2)
    away_xg = round(away.xg, 2)
    if home_xg + away_xg > 0:
        if home.point > home_xg + 0.5:
            paragraphs.append(commentary.render("narrative", "xg_overperform_home", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))
        elif away.point > away_xg + 0.5:
            paragraphs.append(commentary.render("narrative", "xg_overperform_away", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))
        elif home_xg > home.point + 0.8:
            paragraphs.append(commentary.render("narrative", "xg_underperform_home", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))
        elif away_xg > away.point + 0.8:
            paragraphs.append(commentary.render("narrative", "xg_underperform_away", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))

    ratings = compute_match_ratings(home.player_stats, away.player_stats)
    rating_text = _build_rating_paragraph(ratings, home.player_stats, away.player_stats, commentary)
    if rating_text:
        paragraphs.append(rating_text)

    return "\n".join(paragraphs)
