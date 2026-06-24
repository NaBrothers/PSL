"""Format match statistics into centered-alignment display text.

Input: MatchResult (pure data)
Output: formatted string
"""

from engine.types import MatchResult


def format_stats(result: MatchResult) -> str:
    home = result.home_stats
    away = result.away_stats

    msg = "[终场比分]\n"
    msg += "主 " + home.name + " " + str(home.point) + ":" + str(away.point) + " " + away.name + " 客\n\n"

    if result.timeline:
        msg += "[比赛事件]\n"
        max_len = -1
        for goal in result.timeline:
            if goal.team_side == "home":
                max_len = max(max_len, len(goal.scorer_name))
                if goal.assister_name:
                    max_len = max(max_len, len(goal.assister_name))
        max_len = max(max_len + 2, 8)
        for goal in result.timeline:
            if goal.team_side == "home":
                msg += goal.scorer_name.rjust(max_len) + "   ⚽ "
                msg += "  " + str(str(goal.minute) + "'").ljust(3)
                if goal.assister_name:
                    msg += "\n"
                    msg += str("(" + goal.assister_name + ")").rjust(max_len)
            else:
                msg += "".ljust(max_len + 4) + str(goal.minute) + "'  "
                msg += " ⚽   " + goal.scorer_name
                if goal.assister_name:
                    msg += "\n"
                    msg += "".ljust(max_len + 9) + "      (" + goal.assister_name + ")"
            msg += "\n\n"

    if home.goals_detailed or away.goals_detailed:
        msg += "[进球统计]\n"

    if home.goals_detailed:
        msg += "主队：\n"
        for item in home.goals_detailed:
            msg += item[0] + " ("
            for i in item[1]:
                msg += str(i) + "', "
            msg = msg[:-2]
            msg += ")\n"

    if away.goals_detailed:
        msg += "客队：\n"
        for item in away.goals_detailed:
            msg += item[0] + " ("
            for i in item[1]:
                msg += str(i) + "', "
            msg = msg[:-2]
            msg += ")\n"

    if home.goals_detailed or away.goals_detailed:
        msg += "\n"

    msg += "[数据统计]\n"
    total_control = home.control + away.control
    home_ctrl = str(round(home.control * 100 / total_control, 1)) + "%" if total_control else "50%"
    away_ctrl = str(round(away.control * 100 / total_control, 1)) + "%" if total_control else "50%"
    home_pass_rate = "0%" if home.passes == 0 else str(round(home.successful_passes * 100 / home.passes, 1)) + "%"
    away_pass_rate = "0%" if away.passes == 0 else str(round(away.successful_passes * 100 / away.passes, 1)) + "%"

    stats = [
        (home_ctrl, "控球率", away_ctrl),
        (str(home.shoots_in_target), "射正", str(away.shoots_in_target)),
        (str(home.shoots), "射门", str(away.shoots)),
        (str(home.passes), "传球", str(away.passes)),
        (home_pass_rate, "传球成功率", away_pass_rate),
        (str(home.dribbles), "过人", str(away.dribbles)),
        (str(home.carries), "带球推进", str(away.carries)),
        (str(home.tackles), "抢断", str(away.tackles)),
        (str(home.interceptions), "拦截", str(away.interceptions)),
        (str(home.blocks), "封堵", str(away.blocks)),
        (str(home.saves), "扑救", str(away.saves)),
        (str(round(home.xg, 2)), "xG", str(round(away.xg, 2))),
        (str(home.key_passes), "关键传球", str(away.key_passes)),
        (str(home.box_touches), "禁区触球", str(away.box_touches)),
        (str(home.big_chances), "绝对机会", str(away.big_chances)),
    ]

    label_width = max(len(s[1]) for s in stats) + 2
    val_width = 8
    for home_val, label, away_val in stats:
        line = home_val.rjust(val_width) + "  " + label.center(label_width) + "  " + away_val.ljust(val_width)
        msg += line + "\n"

    return msg
