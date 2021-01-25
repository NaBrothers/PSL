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
from game.model.item import Item
from game.utils.database import *
from game.kernel.server import *
from game.model.offline import Offline
from game.model.schedule import Schedule
from game.kernel.pool import g_pool
from game.model.globalAttr import Global
from collections import deque
import math
import random
league_matcher = on_startswith(msg="联赛", rule=to_me(), priority=1)

return_text = '''联赛 比赛：开始下一轮比赛
联赛 赛程：查看赛程
联赛 积分：查看积分榜
联赛 排名 [类型]：查看排行榜（支持类型：进球、助攻、抢断、扑救）
联赛 奖励：查看联赛奖励
阵容 [ID]：查看对手阵容
'''

award_text = '''赛季奖励：
===== 日常奖励 =====
胜利：$2000 + 初级球员卡包*5
平局：$1500 + 初级球员卡包*5
失败：$1000 + 初级球员卡包*5
进球奖励：$100每球（上限$500）
===== 赛季奖励 =====
冠军：$14000 + 高级球员卡包*2
亚军：$13000 + 高级球员卡包*1
季军：$12000 + 中级球员卡包*2
殿军：$11000 + 中级球员卡包*1
其他名次：(15-名次)*1000
副班长：高级球员卡包*1（安慰奖）
===== 单项奖励 =====
金靴：$5000 + 中级球员卡包*2
助攻王：$5000 + 中级球员卡包*2
抢断王：$5000 + 中级球员卡包*2
金手套：$5000 + 中级球员卡包*2
'''
@league_matcher.handle()
async def league_matcher_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(league_matcher, event)
    args = str(event.message).split(" ")
    if len(args) == 4 and args[1] == "重置" and args[2].isdecimal() and args[3].isdecimal():
        await reset_league(user, int(args[2]), int(args[3]))
        return
    status = Global.get("league_status", 0)
    if status == 0:
      await register_league(args, user)
    else:
      await start_league(args, user)
    
async def register_league(args, user):
    league = League.getLeague()
    league_count = Global.get("league_count", LEAGUE_COUNT)
    league_repeat = Global.get("league_repeat", LEAGUE_REPEAT)
    ret = "当前联赛已结束\n球队数量达到" + str(league_count) + "时自动开始下一赛季\n"
    ret += "赛程循环数：" + str(league_repeat) + "\n"
    ret += "输入“联赛 报名”报名联赛\n已报名球队：\n"
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
        if count == league_count:
          await league_matcher.send("新赛季开始了！", **{"at_sender": True})
          Offline.broadcast(user, "新赛季开始了！")
          if league_count % 2 == 1:
            League.addUser(0)
          generate_schedule()
          Global.set("league_status", 1)
    else:
       await league_matcher.finish(toImage(ret), **{"at_sender": True})


def generate_schedule():
    league = League.getLeagueWithNull()
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
    league_repeat = Global.get("league_repeat", LEAGUE_REPEAT)
    final_rounds = rounds * league_repeat
    for i in range(len(final_rounds)):
      one_round = final_rounds[i]
      for j in range(len(one_round)):
        pair = one_round[j]
        if pair[0] is not None:
          home = pair[0].qq
        else:
          home = 0
        if pair[1] is not None:
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
    # elif len(args) == 2 and args[1] == "快速":
    #     await start_game(user, 1)
    elif len(args) == 2 and args[1] == "比赛":
        await start_game(user, 2)
    elif len(args) == 2 and args[1] == "赛程":
        await show_schedule("1")
    elif len(args) == 3 and args[1] == "赛程":
        await show_schedule(args[2])
    elif len(args) == 2 and args[1] == "积分":
        await show_leaderboard()
    elif len(args) == 3 and args[1] == "排名":
        await show_rank(args[2])
    elif len(args) == 2 and args[1] == "奖励":
        await league_matcher.finish(toImage(award_text), **{"at_sender" : True})
    else:
        await league_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return

async def show_schedule(page):
  if not page.isdecimal():
      await league_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
  schedule = Schedule.getSchedule()
  num_rounds = schedule.getNumOfRounds()
  num_games_per_round = len(schedule.entries) // num_rounds
  ret = []
  for n in range(num_rounds):
    ret.append( "=============== 第" + str(n + 1) + "轮 ===============\n")
    for i in range(num_games_per_round):
        entry = schedule.entries[n * num_games_per_round + i]
        tmp = ""
        if entry.home != None and entry.away != None:
          home = "[" + str(entry.home.id) + "] " + entry.home.name
          away = entry.away.name + " [" + str(entry.away.id) + "]"
          tmp += "主 " + home + " vs " + away + " 客"
          if entry.finished:
            tmp += " (" + str(entry.home_goal) + "-" + str(entry.away_goal) + ")\n"
          else:
            tmp += "\n"
        else:
          if entry.home == None:
            tmp += "[" + str(entry.away.id) + "] " + entry.away.name + " 轮空\n"
          else:
            tmp += "[" + str(entry.home.id) + "] " + entry.home.name + " 轮空\n"
        ret.append(tmp)
    ret.append("\n") 
  total_lines = len(ret)
  total_page = math.ceil(total_lines / 30)
  page = int(page)
  if page > total_page or page <= 0:
        await league_matcher.finish("页码错误", **{"at_sender": True})
  result = ""
  for i in range(30):
    index = (page - 1) * 30 + i
    if index >= total_lines:
        break
    result += ret[index]
  result += "\n第" + str(page) + "页 共" + str(total_page) + "页\n"
  result += "联赛 赛程 [页码]：跳转到指定页"
  await league_matcher.finish(toImage(result), **{"at_sender": True})
    

async def reset_league(user, count,repeat):
  if not user.isAdmin:
    await league_matcher.finish("没有管理员权限！", **{"at_sender": True})
  League.clear()
  Global.set("league_status", 0)
  Global.set("league_count", count)
  Global.set("league_repeat", repeat)
  await league_matcher.send("重置成功！", **{"at_sender": True})
  Offline.broadcast(user, "联赛已重置，请报名新赛季！")

async def finish_league(cur_user):
  ret = "联赛已结束，奖励已发放，请管理员重置联赛\n\n"
  league = League.getLeague()
  ret += "冠军：" + league.entries[0].user.format() + " " + str(league.entries[0].score) + "分\n"
  ret += "亚军：" + league.entries[1].user.format() + " " + str(league.entries[1].score) + "分\n"
  ret += "季军：" + league.entries[2].user.format() + " " + str(league.entries[2].score) + "分\n\n"
  name = ["金靴","助攻王","抢断王","金手套"]
  value = ["goal", "assist", "tackle", "save"]
  winners = []
  cursor = g_database.cursor()
  for i in range(len(name)):
    count = cursor.execute("select id from cards order by " + value[i] + " desc, appearance limit 10")
    id = cursor.fetchone()[0]
    card = Card.getCardByID(id)
    ret += name[i] + "：" + "[" + str(card.id) + "]" + " " + card.player.Position + " " + card.getNameWithColor() + " " + card.user.name + " " + str(getattr(card, value[i])) + "个\n"
    winners.append((card,name[i]))
  cursor = g_database.cursor()

  if Global.get("league_status") == 1:
    await get_award(league, cur_user, winners)

  await league_matcher.finish(toImage(ret + "\n" + return_text), **{"at_sender": True})

async def get_award(league, cur_user, winners):
  award = {}
  for i in range(len(league.entries)):
    text = "赛季已结束，获得以下奖励：\n"
    text += "===== 第" + str(i+1) + "名 =====\n"
    user = league.entries[i].user
    award_money = (14-i)*1000
    text += "球币：$" + str(award_money) + "\n"
    user.earn((14-i)*1000)
    if i == 0:
      award_card = 3
      award_count = 2
      Item.addItem(user, 0, award_card, award_count)
      text += g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count) + "\n"
    elif i == 1:
      award_card = 3
      award_count = 1
      Item.addItem(user, 0, award_card, award_count)
      text += g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count) + "\n"
    elif i == 2:
      award_card = 2
      award_count = 2
      Item.addItem(user, 0, award_card, award_count)
      text += g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count) + "\n"
    elif i == 3:
      award_card = 2
      award_count = 1
      Item.addItem(user, 0, award_card, award_count)
      text += g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count) + "\n"
    elif i == len(league.entries) - 1:
      award_card = 3
      award_count = 1
      Item.addItem(user, 0, award_card, award_count)
      text += g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count) + "（安慰奖）" + "\n"
    award[user.qq] = text

  for winner,prize in winners:
      award[winner.user.qq] += "===== " + prize + " =====\n"
      award_money = 5000
      winner.user.earn(award_money)
      award[winner.user.qq] += "球币：$" + str(award_money) + "\n"
      award_card = 2
      award_count = 5
      Item.addItem(winner.user, 0, award_card, award_count)
      award[winner.user.qq] += g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count) + "\n"
  
  await league_matcher.send(toImage(award[cur_user.qq]), **{"at_sender": True})
  
  for entry in league.entries:
    if entry.user.qq == cur_user.qq:
      continue
    Offline.send(entry.user, toImage(award[entry.user.qq]))

  Global.set("league_status", "2")

async def print_schedule(user):
    schedule = Schedule.getCurrentRound()
    if schedule == None:
      await finish_league(user)
    else:
      ret = "第" + str(schedule.entries[0].round) + "轮联赛\n"
      ret += "===== 本轮赛程 =====\n"
      for entry in schedule.entries:
        tmp = ""
        if entry.home != None and entry.away != None:
          home = "[" + str(entry.home.id) + "] " + entry.home.name
          away = entry.away.name + " [" + str(entry.away.id) + "]"
          tmp += "主 " + home + " vs " + away + " 客"
          if entry.finished:
            tmp += " (" + str(entry.home_goal) + "-" + str(entry.away_goal) + ")\n"
          else:
            tmp += "\n"
        else:
          if entry.home == None:
            tmp += "[" + str(entry.away.id) + "] " + entry.away.name + " 轮空\n"
          else:
            tmp += "[" + str(entry.home.id) + "] " + entry.home.name + " 轮空\n"
        ret += tmp
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


async def start_game(user, mode):
    entry = Schedule.getCurrentEntry(user)
    if entry == None:
      await league_matcher.finish("联赛已结束", **{"at_sender": True})
    if entry.finished:
      await league_matcher.finish("本轮比赛已完成，请等待下一轮", **{"at_sender": True})
    user1 = entry.home
    user2 = entry.away
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
    stats = await game.start(mode)
    g_server.set("in_game", False)

    update_stats(game, formation1, formation2)
    entry.set("finished", True)
    entry.set("home_goal", game.home.goals)
    entry.set("away_goal", game.away.goals)

    if entry.home_goal > entry.away_goal:
      home_money = 2000
      away_money = 1000
    elif entry.home_goal == entry.away_goal:
      home_money = 1500
      away_money = 1500
    else:
      home_money = 1000
      away_money = 2000

    home_money += 100 * min(5, entry.home_goal)
    away_money += 100 * min(5, entry.away_goal)

    entry.home.earn(home_money)
    entry.away.earn(away_money)
    
    award_card = 1
    award_count = 5
    Item.addItem(entry.home, 0, award_card, award_count)
    Item.addItem(entry.away, 0, award_card, award_count)

    home_award = "获得球币：$" + str(home_money) + "，" + g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count)
    away_award = "获得球币：$" + str(away_money) + "，" + g_pool[Const.ITEM[0]["item"][award_card]["name"]]["name"] + "*" + str(award_count)

    msg = "第" + str(entry.round) + "轮联赛已结束，" 
    if user1.qq == user.qq:
      await league_matcher.send(home_award, **{"at_sender": True})
      Offline.send(user2, msg + away_award + "\n" + stats)
    else:
      await league_matcher.send(away_award, **{"at_sender": True})
      Offline.send(user1, msg + home_award + "\n" + stats)
      

    


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
