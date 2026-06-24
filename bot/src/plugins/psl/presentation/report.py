"""Generate narrative match report from MatchResult.

Input: MatchResult + CommentaryRenderer
Output: report text string
"""

from engine.types import MatchResult
from engine.commentary import CommentaryRenderer


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

    return "\n".join(paragraphs)
