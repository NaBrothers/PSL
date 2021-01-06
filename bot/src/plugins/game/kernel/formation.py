from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.card import *
from game.model.bag import *
from game.kernel.account import *
from game.model.formation import *
from game.utils.image import toImage

get_team = on_startswith(msg="阵容", rule=to_me(), priority=1)

error_text = '''阵容 自动：按能力值自动更新阵容
'''


@get_team.handle()
async def get_team_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(get_team, event)
    args = str(event.message).split(" ")
    if len(args) == 1:
        await show_team(user)
    elif len(args) == 2:
        if args[1] == "自动":
            await auto_update(user)
        else:
          await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
    else:
        await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})


async def show_team(user):
    team = Formation.getFormation(user)
    ret = ""
    ret += "教练：" + user.name + "\n"
    ret += "阵容：" + team.formation + "\n"
    ret += "===== 主力 =====\n"
    for i, card in enumerate(team.cards):
        #ret += str(i).ljust(2) + "  "
        if i <= 10:
            ret += Const.FORMATION[team.formation]["positions"][i].ljust(3) + "  "
        else:
            if card == None:
                ret += "无" + "   "
            else:
                ret += card.player.Position.ljust(3) + "  "
        if card == None:
            ret += "空缺"
        else:
            ret += "[" + str(card.id) + "] " + card.getNameWithColor() + " " + str(
                card.overall) + " " + Const.STARS[card.star]["star"] + " " + card.getStyle()
        ret += "\n"
        if i == 10:
            ret += "===== 替补 =====\n"
    await get_team.finish("当前阵容：\n" + toImage(ret + error_text), **{'at_sender': True})


async def auto_update(user):
    team = Formation.getFormation(user)
    bag = Bag.getBag(user)
    gk = 0
    guard = 0
    midfield = 0
    forward = 0
    sub = Formation.PLAYERS_COUNT - 11
    for i in range(11):
        position = Const.FORMATION[team.formation]["positions"][i]
        if position in Const.GOALKEEPER:
            gk += 1
        elif position in Const.GUARD:
            guard += 1
        elif position in Const.MIDFIELD:
            midfield += 1
        elif position in Const.FORWARD:
            forward += 1

    result = [0 for i in range(Formation.PLAYERS_COUNT)]
    gk_start = 0
    guard_start = gk_start + gk
    midfield_start = guard_start + guard
    forward_start = midfield_start + midfield
    sub_start = 11
    available_cards = set()
    for card in bag.cards:
        if card.player.ID in available_cards:
          continue
        if gk == 0 and guard == 0 and midfield == 0 and forward == 0 and sub == 0:
            break
        if card.player.Position in Const.GOALKEEPER and gk > 0:
            result[gk_start] = card.id
            gk -= 1
            gk_start += 1
        elif card.player.Position in Const.GUARD and guard > 0:
            result[guard_start] = card.id
            guard -= 1
            guard_start += 1
        elif card.player.Position in Const.MIDFIELD and midfield > 0:
            result[midfield_start] = card.id
            midfield -= 1
            midfield_start += 1
        elif card.player.Position in Const.FORWARD and forward > 0:
            result[forward_start] = card.id
            forward -= 1
            forward_start += 1
        elif sub > 0:
            result[sub_start] = card.id
            sub -= 1
            sub_start += 1
        available_cards.add(card.player.ID)
  
    cursor = g_database.cursor()
    for i in range(len(result)):
        cursor.execute("update team set card = " + str(
            result[i]) + " where user = " + str(user.qq) + " and position = " + str(i))
    cursor.close()

    await show_team(user)
