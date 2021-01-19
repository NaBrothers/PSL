from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.kernel.account import check_account
from game.engine.game import Game
from game.model.user import User
from game.model.card import Card
from game.model.formation import Formation
from game.model.league import League
from game.utils.database import *
from game.kernel.server import *

league_matcher = on_startswith(msg="联赛", rule=to_me(), priority=1)

return_text = '''联赛 ID：挑战对手
联赛 快速 ID：只显示比赛结果
联赛 积分：查看积分榜
联赛 排名 类型：查看排行榜（支持类型：进球、助攻、抢断、扑救）
阵容 ID：查看对手阵容
'''


@league_matcher.handle()
async def league_matcher_handler(bot: Bot, event: Event, state: dict):
    await check_account(league_matcher, event)
    args = str(event.message).split(" ")
    mode = 2

    if len(args) == 1:
        users = User.getAllUsers()
        ret = "请选择对手：\n"
        for user in users:
            if user.qq == event.user_id:
                continue
            ret += "[" + str(user.id) + "]\t" + user.name + "\n"
        ret += return_text
        await league_matcher.finish(toImage(ret), **{"at_sender": True})
        return

    if len(args) == 3 and args[1] == "快速" and args[2].isdecimal():
        mode = 1
        str_id = args[2]
        await start_game(event.user_id, str_id, mode)
    elif len(args) == 2 and args[1].isdecimal():
        str_id = args[1]
        await start_game(event.user_id, str_id, mode)
    elif len(args) == 2 and args[1] == "积分":
        await show_leaderboard()
    elif len(args) == 3 and args[1] == "排名":
        await show_rank(args[2])
    else:
        await league_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return


async def show_leaderboard():
    ret =  "======================== 积分榜 ======================\n"
    ret += "排名  积分  场次    胜   平   负    进球  失球  净胜球       球队\n"
    league = League.getLeague()
    if league == None:
        ret += "空"
    else:
        for i, entry in enumerate(league.entries):
            ret += str("[" + str(i+1) + "]").ljust(4) + "   " + str(entry.score).ljust(2) + "     " + str(entry.appearance).ljust(2) + "    " + str(entry.win).ljust(2) + "   " + str(entry.tie).ljust(2) + "    " + \
                str(entry.lose).ljust(2) + "    " + str(entry.goal).ljust(2) + "    " + str(entry.lost_goal).ljust(2) + \
                "    " + str(entry.goal - entry.lost_goal).ljust(2) + \
                "      " + str("[" + str(entry.user.id) + "]").ljust(2) + " " + entry.user.name + "\n"

    await league_matcher.finish(toImage(ret), **{"at_sender": True})


async def show_rank(arg):
    if arg == "进球":
        string = "goal"
    elif arg == "助攻":
        string = "assist"
    elif arg == "抢断":
        string = "tackle"
    elif arg == "扑救":
        string = "save"
    else:
        await league_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return

    cursor = g_database.cursor()
    count = cursor.execute(
        "select user, id from cards order by " + string + " desc, appearance limit 10")
    data = cursor.fetchall()
    ret = "===== " + arg + "榜 =====\n"
    for i in range(count):
        user = User.getUserByQQ(data[i][0])
        card = Card.getCardByID(data[i][1])
        if getattr(card, string) == 0:
            break
        ret += str("[" + str(i+1) + "]").ljust(4) + "  " + str(getattr(card, string)).ljust(2) + "  " + "[" + str(
            card.id) + "]" + "\t" + card.player.Position + " " + card.getNameWithColor() + " " + user.name + "\n"
    cursor.close()

    await league_matcher.finish(toImage(ret), **{"at_sender": True})


async def start_game(id1, str_id, mode):
    if g_server.get("in_game") == True:
        await league_matcher.finish("比赛正在进行中！", **{"at_sender": True})
    user1 = User.getUserByQQ(id1)
    formation1 = Formation.getFormation(user1)
    if str_id == str(user1.id):
        await league_matcher.finish("请不要挑战自己！", **{"at_sender": True})
        return
    if not formation1.isValid():
        await league_matcher.finish("阵容不完整！", **{"at_sender": True})
        return
    cursor = g_database.cursor()
    count = cursor.execute("select * from users where id = " + str_id)
    if count == 0:
        await league_matcher.finish("找不到此对手", **{"at_sender": True})
        return

    user2 = User.getUserById(int(str_id))
    formation2 = Formation.getFormation(user2)
    if not formation2.isValid():
        await league_matcher.finish("对手阵容不完整！", **{"at_sender": True})
        return
    game = Game(league_matcher, user1, user2)
    if mode != 1:
        await league_matcher.send("开始比赛", **{"at_sender": True})
    g_server.set("in_game", True)
    await game.start(mode)
    g_server.set("in_game", False)

    update_stats(game, formation1, formation2)


def update_stats(game, formation1, formation2):
    for i in range(11):
        player = game.home.players[i]
        card = formation1.cards[i]
        card.set("appearance", card.appearance + 1)
        card.set("goal", card.goal + player.goals)
        card.set("assist", card.assist + player.assists)
        card.set("tackle", card.tackle + player.tackles)
        card.set("save", card.save + player.saves)
        card.set("total_appearance", card.total_appearance + 1)
        card.set("total_goal", card.total_goal + player.goals)
        card.set("total_assist", card.total_assist + player.assists)
        card.set("total_tackle", card.total_tackle + player.tackles)
        card.set("total_save", card.total_save + player.saves)

    for i in range(11):
        player = game.away.players[i]
        card = formation2.cards[i]
        card.set("appearance", card.appearance + 1)
        card.set("goal", card.goal + player.goals)
        card.set("assist", card.assist + player.assists)
        card.set("tackle", card.tackle + player.tackles)
        card.set("save", card.save + player.saves)
        card.set("total_appearance", card.total_appearance + 1)
        card.set("total_goal", card.total_goal + player.goals)
        card.set("total_assist", card.total_assist + player.assists)
        card.set("total_tackle", card.total_tackle + player.tackles)
        card.set("total_save", card.total_save + player.saves)

    entry1 = League.getLeagueEntryByQQ(formation1.user.qq)
    if not entry1:
        League.addUser(formation1.user.qq)
        entry1 = League.getLeagueEntryByQQ(formation1.user.qq)

    entry2 = League.getLeagueEntryByQQ(formation2.user.qq)
    if not entry2:
        League.addUser(formation2.user.qq)
        entry2 = League.getLeagueEntryByQQ(formation2.user.qq)

    entry1.set("appearance", entry1.appearance + 1)
    entry2.set("appearance", entry2.appearance + 1)
    entry1.set("goal", entry1.goal + game.home.goals)
    entry2.set("goal", entry2.goal + game.away.goals)
    entry1.set("lost_goal", entry1.lost_goal + game.away.goals)
    entry2.set("lost_goal", entry2.lost_goal + game.home.goals)

    if game.home.goals > game.away.goals:
        entry1.set("win", entry1.win + 1)
        entry2.set("lose", entry2.lose + 1)
        entry1.set("score", entry1.score + 3)
    elif game.home.goals < game.away.goals:
        entry2.set("win", entry2.win + 1)
        entry1.set("lose", entry1.lose + 1)
        entry2.set("score", entry2.score + 3)
    else:
        entry1.set("tie", entry1.tie + 1)
        entry2.set("tie", entry2.tie + 1)
        entry1.set("score", entry1.score + 1)
        entry2.set("score", entry2.score + 1)
