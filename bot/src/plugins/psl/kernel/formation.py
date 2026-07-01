from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.database import *
from model.user import *
from model.card import *
from model.bag import *
from kernel.account import *
from model.formation import *
from utils.image import toImage

from queue import PriorityQueue

get_team = on_startswith(msg="阵容", rule=to_me(), priority=1)

AVAILABLE_FORMATIONS = "、".join(Const.FORMATION.keys())

error_text = '''阵容 自动：按能力值自动更新阵容
阵容 [ID]：查看其他玩家阵容
阵容 替换 [球员1] [球员2]：替换两名球员
阵容 更改 [阵型]：更改其他阵型（''' + AVAILABLE_FORMATIONS + '''）
'''


@get_team.handle()
async def get_team_handler(bot: Bot, event: Event):
    user = await check_account(get_team, event)
    args = str(event.message).split(" ")
    if len(args) == 1:
        await show_team(user)
    elif len(args) == 2:
        if args[1] == "自动":
            await auto_update(user)
        elif args[1].isdecimal():
            await show_others(args[1])
        else:
          await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
    elif len(args) == 3:
        if args[1] == "更改" and args[2] in Const.FORMATION.keys():
            await change_formation(user, args[2])
        else:
            await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
    elif len(args) == 4:
        if args[1] == "替换" and args[2].isdecimal() and args[3].isdecimal():
            await change_player(user, args[2], args[3])
        else:
            await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
    else:
        await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})

async def change_player(user, id1, id2):
    team = Formation.getFormation(user)
    bag = Bag.getBag(user)
    bag_ids = [str(x.id) for x in bag.cards if x != None]

    if id1 not in bag_ids:
      await get_team.finish("找不到球员1！", **{'at_sender': True})
      return

    if id2 not in bag_ids:
      await get_team.finish("找不到球员2！", **{'at_sender': True})
      return

    team_ids = [str(x.id) for x in team.cards if x != None]

    if id1 not in team_ids and id2 not in team_ids:
      await get_team.finish("请至少选择一名阵容中的球员！", **{'at_sender': True})
      return

    player_ids = [x.player.ID for x in team.cards if x != None]
    card1 = Card.getCardByID(id1)
    card2 = Card.getCardByID(id2)

    cursor = g_database.cursor()
    if id1 in team_ids and id2 in team_ids:
        cursor.execute("update team set card = " + "-1" + " where card = " + str(id1))
        cursor.execute("update team set card = " + str(id1) + " where card = " + str(id2))
        cursor.execute("update team set card = " + str(id2) + " where card = " + "-1")
    elif id1 in team_ids:
        if card1.player.ID != card2.player.ID and card2.player.ID in player_ids:
          await get_team.finish("阵容中存在同名球员！", **{'at_sender': True})
          return
        if card2.status != 0:
          await get_team.finish("替换失败！球员2状态：" + Const.STATUS[card2.status], **{'at_sender': True})
          return
        cursor.execute("update team set card = " + str(id2) + " where card = " + str(id1))
        card1.set("status", 0)
        card2.set("status", 2)
    elif id2 in team_ids:
        if card1.player.ID != card2.player.ID and card1.player.ID in player_ids:
          await get_team.finish("阵容中存在同名球员！", **{'at_sender': True})
          return
        if card1.status != 0:
          await get_team.finish("替换失败！球员1状态：" + Const.STATUS[card1.status], **{'at_sender': True})
          return
        cursor.execute("update team set card = " + str(id1) + " where card = " + str(id2))
        card1.set("status", 2)
        card2.set("status", 0)
    cursor.close()   

    await get_team.finish("替换成功！", **{'at_sender': True})

async def change_formation(user, formation):
    user.setFormation(formation)
    ret = "更改成功，当前阵容：" + user.formation
    await get_team.finish(ret, **{'at_sender': True})

async def show_team(user):
    team = Formation.getFormation(user)
    ret = ""
    ret += "教练：" + user.name + "\n"
    ret += "阵容：" + team.formation + "\n"
    total, forward, midfield, guard = team.getAbilities(user)
    ret += "总能力：" + str(total) + "  前场：" + str(forward) + "  中场：" + str(midfield) + "  后场：" + str(guard) + "\n"
    total_price = 0
    for card in team.cards:
        if card != None:
          total_price += card.price
    ret += "总身价：" + Card.formatPrice(total_price) + "\n"
    ret += "===== 主力 =====\n"
    for i, card in enumerate(team.cards):
        if i == 11:
            ret += "===== 替补 =====\n"
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
            if i <= 10:
              overall = card.printRealOverall(Const.FORMATION[team.formation]["positions"][i])
              ret += str(overall).ljust(10) + "  [" + str(card.id) + "] " + card.getNameWithColor() + " "  + Const.STARS[card.star]["star"] + " ◆+" + str(card.breach) + " " + card.getStyle()
            else:
              overall = card.overall
              ret += str(overall).ljust(3) + "  [" + str(card.id) + "] " + card.getNameWithColor() + " "  + Const.STARS[card.star]["star"]+ " ◆+" + str(card.breach)  + " " + card.getStyle()
        ret += "\n"
    await get_team.finish("当前阵容：\n" + toImage(ret + error_text), **{'at_sender': True})

async def show_others(id):
    user = User.getUserById(id)
    if user == None:
       await get_team.finish("找不到该玩家！", **{'at_sender': True})
    await show_team(user)

async def auto_update(user):
    from psl_core.card import position_group
    from psl_core.formation import position_fit_bonus as _fit_bonus

    def position_fit_bonus(card, slot):
      positions = [p.strip() for p in card.player.Position.split(",")]
      return _fit_bonus(positions, slot)

    team = Formation.getFormation(user)
    bag = Bag.getBag(user)
    result = [0 for i in range(Formation.PLAYERS_COUNT)]
    selected_players = set()
    available_cards = [
      card for card in bag.cards
      if card is not None and (card.status == 0 or card.status == 2)
    ]

    positions = Const.FORMATION[team.formation]["positions"]
    slot_order = sorted(range(11), key=lambda idx: {"GK": 0, "D": 1, "F": 2, "M": 3}[position_group(positions[idx])])
    for slot_index in slot_order:
      slot = positions[slot_index]
      candidates = [
        card for card in available_cards
        if card.player.ID not in selected_players
      ]
      if not candidates:
        break
      best = max(
        candidates,
        key=lambda card: (
          card.getRealOverall(slot) + position_fit_bonus(card, slot),
          position_fit_bonus(card, slot),
          card.overall,
        )
      )
      result[slot_index] = best.id
      selected_players.add(best.player.ID)

    for card in team.cards:
      if card != None:
        card.set("status", 0)

    cursor = g_database.cursor()
    for i in range(len(result)):
        cursor.execute("update team set card = " + str(
            result[i]) + " where user = " + str(user.qq) + " and position = " + str(i))
    cursor.close()

    team = Formation.getFormation(user)
    for card in team.cards:
      if card != None:
        card.set("status", 2)

    await show_team(user)

# 此方法已废弃
async def auto_update2(user):
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
