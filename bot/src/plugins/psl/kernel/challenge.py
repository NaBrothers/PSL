from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.image import toImage
from kernel.account import check_account
from engine.game import Game
from model.user import User
from model.formation import Formation
from model.npc_formation import NpcFormation
from model.card import Card
from model.item import Item
from utils.database import *
from kernel.server import *
from kernel.pool import g_pool
from model.challenge_times import ChallengeTimes

import time
challenge_matcher = on_startswith(msg="挑战", rule=to_me(), priority=1)

return_text = '''挑战 [难度]：挑战每日巡回赛球队
挑战 快速 [难度]：只显示比赛结果
挑战 阵容 [难度]：查看每日巡回赛球队阵容
'''


@challenge_matcher.handle()
async def challenge_matcher_handler(bot: Bot, event: Event):
    user = await check_account(challenge_matcher, event)
    mode = 0
    npc = time.localtime(time.time()).tm_wday % len(Const.NPC)
    challenge_times = ChallengeTimes.getTimes(user)
    args = str(event.message).split(" ")
    if len(args) == 1:
        difficulties = Const.DIFFICULTY
        ret = "今日巡回赛球队：" + Const.NPC[npc]["name"] + "\n"
        ret += "剩余挑战次数：" + str(challenge_times.times) + "\n"
        ret += "请选择难度：\n"
        for difficulty in difficulties:
            ret += "[" + difficulty + "] " + \
                str(Const.DIFFICULTY[difficulty]["star"]) + "星\n"
        ret += return_text
        await challenge_matcher.finish(toImage(ret), **{"at_sender": True})
        return
    elif len(args) == 3:
        if args[2] not in Const.DIFFICULTY:
            await challenge_matcher.finish("找不到此难度", **{"at_sender": True})
            return
        else:
            if args[1] == "快速":
                mode = 1
                diff_key = args[2]
            elif args[1] == "阵容":
                await show_team(npc, args[2])
                return
            else:
                await challenge_matcher.finish("格式错误！\n" + toImage(return_text), **{'at_sender': True})
                return
    elif len(args) == 2:
        if args[1] in Const.DIFFICULTY:
            diff_key = args[1]
        elif args[1] == "次数":
            await challenge_matcher.finish(str(challenge_times.times), **{"at_sender": True})
        else:
            await challenge_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
            return
    else:
        await challenge_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return

    if challenge_times.times <= 0:
        await challenge_matcher.finish("今日次数已用尽，请明日再来", **{"at_sender": True})
        return

    if g_server.get("in_game") == True:
        await challenge_matcher.finish("比赛正在进行中！", **{"at_sender": True})
    user1 = User.getUserByQQ(event.user_id)
    formation1 = Formation.getFormation(user1)
    if not formation1.isValid():
        await challenge_matcher.finish("阵容不完整！", **{"at_sender": True})
        return
    challenge_times.setTimes(challenge_times.times - 1)
    game = Game(challenge_matcher, user1, 0, npc, diff_key)
    if mode != 1:
        await challenge_matcher.send("开始比赛", **{"at_sender": True})
    g_server.set("in_game", True)
    await game.start(mode)
    g_server.set("in_game", False)
    if game.home.point > game.away.point:
        result = "win"
    elif game.home.point == game.away.point:
        result = "tie"
    else:
        result = "lose"
    await pay_award(user1, result, diff_key, npc)

async def pay_award(user, result, difficulty, npc):
    if result == "lose":
        award_msg = "很遗憾，"
    else:
        award_msg = "恭喜您，"
    award_msg += "挑战" + difficulty + "级别" + Const.NPC[npc]["name"] + "\n"
    award_msg += "结果为"
    if result == "lose":
        award_msg += "失败"
    elif result == "tie":
        award_msg += "平局"
    else:
        award_msg += "胜利"
    award_msg += "，奖励：\n"
    awards = Const.DIFFICULTY[difficulty]["award"]
    if result in awards:
        award_money = awards[result]["money"]
        user.earn(award_money)
        award_msg += "球币：$" + str(award_money) + "\n"
        for item_number in awards[result]["item"]:
            for sub_item_number in awards[result]["item"][item_number]:
                amount = awards[result]["item"][item_number][sub_item_number]
                award_msg += g_pool[Const.ITEM[item_number]["item"][sub_item_number]["name"]]["name"] + "*" + str(amount) + "\n"
                Item.addItem(user, item_number, sub_item_number, amount)
    else:
        award_msg += "无"
    await challenge_matcher.finish(toImage(award_msg), **{"at_sender": True})

async def show_team(npc, difficulty):
    team = NpcFormation(npc, difficulty)
    ret = ""
    ret += "球队：" + Const.NPC[npc]["name"] + " " + difficulty + "\n"
    ret += "阵容：" + team.formation + "\n"
    total, forward, midfield, guard = team.getAbilities()
    ret += "总能力：" + str(total) + "  前场：" + str(forward) + \
        "  中场：" + str(midfield) + "  后场：" + str(guard) + "\n"
    total_price = 0
    for card in team.cards:
        if card != None:
            total_price += card.price
    ret += "总身价：" + Card.formatPrice(total_price) + "\n"
    ret += "===== 主力 =====\n"
    for i, card in enumerate(team.cards):
        #ret += str(i).ljust(2) + "  "
        if i <= 10:
            ret += Const.FORMATION[team.formation]["positions"][i].ljust(
                3) + "  "
        else:
            if card == None:
                ret += "无" + "   "
            else:
                ret += card.player.Position.ljust(3) + "  "
        if card == None:
            ret += "空缺"
        else:
            if i <= 10:
                overall = card.printRealOverall(
                    Const.FORMATION[team.formation]["positions"][i])
                ret += str(overall).ljust(10) + "  " + card.printID() + " " + card.getNameWithColor(
                ) + " " + Const.STARS[card.star]["star"] + " " + card.getStyle()
            else:
                overall = card.overall
                ret += str(overall).ljust(3) + "  " + card.printID() + " " + card.getNameWithColor(
                ) + " " + Const.STARS[card.star]["star"] + " " + card.getStyle()
        ret += "\n"
    await challenge_matcher.finish("当前阵容：\n" + toImage(ret + return_text), **{'at_sender': True})
