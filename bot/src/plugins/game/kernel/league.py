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
from game.model.offline import Offline
from game.model.schedule import Schedule
from collections import deque
import random
league_matcher = on_startswith(msg="联赛", rule=to_me(), priority=1)

return_text = '''联赛 比赛：开始下一轮比赛
联赛 快速：跳过比赛过程
联赛 积分：查看积分榜
联赛 排名 类型：查看排行榜（支持类型：进球、助攻、抢断、扑救）
阵容 ID：查看对手阵容
'''

@league_matcher.handle()
async def league_matcher_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(league_matcher, event)
    args = str(event.message).split(" ")
  
    count = League.getCount()
    if count < LEAGUE_COUNT:
      await register_league(args, user)
    else:
      await start_league(args, user)
    
async def register_league(args, user):
    league = League.getLeague()
    ret = "当前联赛已结束\n球队数量达到" + str(LEAGUE_COUNT) + "时自动开始下一赛季\n输入“联赛 报名”报名联赛\n已报名球队：\n"
    if league != None:
      for entry in league.entries:
          ret += "[" + str(entry.user.id) + "]\t" + entry.user.name + "\n"
    if len(args) == 2 and args[1] == "报名":
        entry = League.getLeagueEntryByQQ(user.qq)
        if entry != None:
          await league_matcher.finish("请不要重复报名！", **{"at_sender": True})
        League.addUser(user.qq)
        await league_matcher.send("报名成功！", **{"at_sender": True})
        count = League.getCount()
        if count == LEAGUE_COUNT:
          await league_matcher.send("新赛季开始了！", **{"at_sender": True})
          Offline.broadcast(user, "新赛季开始了！")
          League.clearStats()
          if LEAGUE_COUNT % 2 == 1:
            League.addUser(0)
        generate_schedule()
    else:
       await league_matcher.finish(toImage(ret), **{"at_sender": True})


def generate_schedule():
    league = League.getLeague()
    users = [entry.user for entry in league.entries]
    random.shuffle(users)
    fix = users[0]
    ring = users[1:]
    ring = deque(ring)
    rounds1 = []
    rounds2 = []
    for r in range(len(users) - 1):
      teams = [fix] + list(ring)
      home, away = teams[:len(teams)//2], teams[len(teams)//2:]
      away = away[::-1]
      one_round = [(x,y) if random.random()>=0.5 else (y,x) for x,y in zip(home, away)]
      rounds1.append(one_round)
      reverse_round = [(y,x) for x,y in one_round]
      rounds2.append(reverse_round)
      ring.rotate(1)
    rounds = rounds1 + rounds2
    final_rounds = rounds * LEAGUE_REPEAT

    for i in range(len(final_rounds)):
      one_round = final_rounds[i]
      for j in range(len(one_round)):
        pair = one_round[j]
        if pair[0] != None:
          home = pair[0].qq
        else:
          home = 0
        if pair[1] != None:
          away = pair[1].qq
        else:
          away = 0
        if home == 0 or away == 0:
          entry = (i*len(one_round)+j+1, i+1, home, away, True, 0, 0)
        else:
          entry = (i*len(one_round)+j+1, i+1, home, away, False, 0, 0)
        Schedule.addEntry(entry)

async def start_league(args, user):
    if len(args) == 1:
        await print_schedule(user)
    elif len(args) == 2 and args[1] == "快速":
        entry = Schedule.getCurrentEntry(user)
        if entry.finished:
          await league_matcher.finish("本轮比赛已完成，请等待下一轮", **{"at_sender": True})
        await start_game(entry.home, entry.away, 1, entry)
    elif len(args) == 2 and args[1] == "比赛":
        entry = Schedule.getCurrentEntry(user)
        if entry.finished:
          await league_matcher.finish("本轮比赛已完成，请等待下一轮", **{"at_sender": True})
        await start_game(entry.home, entry.away, 2, entry)
    elif len(args) == 2 and args[1] == "积分":
        await show_leaderboard()
    elif len(args) == 3 and args[1] == "排名":
        await show_rank(args[2])
    else:
        await league_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return


async def print_schedule(user):
    schedule = Schedule.getCurrentRound()
    if schedule == None:
      ret = "所有赛程已结束\n"
    else:
      ret = "第" + str(schedule.entries[0].round) + "轮联赛\n"
      ret += "===== 本轮赛程 =====\n"
      for entry in schedule.entries:
        if entry.home == None:
          home = "轮空"
        else:
          home = "[" + str(entry.home.id) + "] " + entry.home.name
        if entry.away == None:
          away = "轮空"
        else:
          away = entry.away.name + " [" + str(entry.away.id) + "]"
        ret += "主 " + home + " vs " + away + " 客"
        if entry.home != None and entry.away != None and entry.finished:
          ret += " (" + str(entry.home_goal) + "-" + str(entry.away_goal) + ")\n"
        else:
          ret += "\n" 
      ret += "===== 下一比赛 =====\n"
      for entry in schedule.entries:
        if entry.home != None and entry.home.qq == user.qq or entry.away != None and entry.away.qq == user.qq:
          if entry.home == None or entry.away == None:
            ret += "本轮轮空\n"
          elif entry.finished:
            ret += "本轮比赛已完成\n"
          else:
            ret += "主 " + "[" + str(entry.home.id) + "] " + entry.home.name + " vs " + entry.away.name + " [" + str(entry.away.id) + "] " + "客\n"
    await league_matcher.finish(toImage(ret + "\n" + return_text), **{"at_sender": True})

async def show_leaderboard():
    ret =  "======================== 积分榜 ======================\n"
    ret += "排名  积分  场次    胜   平   负    进球  失球  净胜球       球队\n"
    league = League.getLeague()
    if league == None:
        ret += "空"
    else:
        n = 0
        for i, entry in enumerate(league.entries):
            if entry.user == None:
              n = 1
              continue
            ret += str("[" + str(i+1-n) + "]").ljust(4) + "   " + str(entry.score).ljust(2) + "     " + str(entry.appearance).ljust(2) + "    " + str(entry.win).ljust(2) + "   " + str(entry.tie).ljust(2) + "    " + \
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


async def start_game(user1, user2, mode, entry):
    if g_server.get("in_game") == True:
        await league_matcher.finish("比赛正在进行中！", **{"at_sender": True})
    formation1 = Formation.getFormation(user1)
    if not formation1.isValid():
        await league_matcher.finish("阵容不完整！", **{"at_sender": True})
        return
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
    entry.set("finished", True)
    entry.set("home_goal", game.home.goals)
    entry.set("away_goal", game.away.goals)

    


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
