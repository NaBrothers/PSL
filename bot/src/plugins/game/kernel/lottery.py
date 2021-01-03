import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.utils.const import *
from game.kernel.pool import *
from game.kernel.account import check_account
from game.kernel.bag import *
from game.model.card import *
from game.utils.image import toImage

return_text = '''所有卡包：
[10]\t普通：一张任意位置球员卡
[30]\t球星：一张任意位置球员卡（能力值84以上）
[50]\t巨星：一张任意位置球员卡（能力值87以上）
[100]\t巅峰：一张任意位置球员卡（能力值89以上）
[30]\t前锋：一张前锋球员卡
[30]\t中场：一张中场球员卡
[30]\t后卫：一张后卫球员卡
[30]\t门将：一张门将球员卡
[200]\t十连：十张任意位置球员卡（至少一张能力值87以上）
[*]\t\t新手：二十张球员卡（前锋*6，中场*6，后卫*6，门将*2，至少一张能力值89以上）
'''

try_lottery = on_startswith(msg="抽卡", rule=to_me(), priority=1)

@try_lottery.handle()
async def try_lottery_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(try_lottery,event)
    args = str(event.message).split(" ")
    if len(args) > 1:
        pool = args[1]
        if pool not in g_pool.keys():
            await try_lottery.finish(toImage(return_text), **{'at_sender': True})
            return
        if user.money < g_pool[pool]["cost"]:
            await try_lottery.finish("余额不足", **{"at_sender": True})
            return
            
        if (pool == "十连"):
          ret = try_ten(user, pool)
        elif (pool == "至尊"):
          ret = try_nb(user, pool)
        elif pool == "新手":
          if not user.isFirst:
            await try_lottery.finish("你不是新手，抽nm呢", **{"at_sender": True})
            return
          ret = try_newbee(user, pool)
        else:
          ret = try_single(user, pool)
        ret += "\n剩余球币：" + str(user.money)
        await try_lottery.finish(toImage(ret), **{"at_sender": True})
    else:
        await try_lottery.finish("格式：抽卡 卡包\n" + toImage(return_text), **{'at_sender': True})

def try_single(user, pool):
  card = g_pool[pool]["pool"].choice(user)
  id = Bag.addToBag(user, card)
  user.spend(g_pool[pool]["cost"])
  return "[" + str(id) + "] " + card.format()

def try_ten(user, pool):
    cards = []
    result = ""
    floored = False
    for i in range(10):
        card = g_pool["普通"]["pool"].choice(user)
        if i == 9 and not floored:
            card = g_pool["巨星"]["pool"].choice(user)
        else:
            card = g_pool["普通"]["pool"].choice(user)
        if card.player.Overall > 86:
            floored = True
        cards.append(card)

    ids = Bag.addToBagMany(user, cards)

    for i,card in enumerate(cards):
      result += "[" + str(ids[i]) + "] "
      result += card.format() + "\n"

    user.spend(g_pool[pool]["cost"])
    return result.rstrip("\n")

def try_newbee(user, pool):
    cards = []
    result = ""
    floored = False

    for i in range(6):
        card = g_pool["前锋"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    for i in range(6):
        card = g_pool["中场"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    for i in range(6):
        card = g_pool["后卫"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    for i in range(2):
        card = g_pool["门将"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    if not floored:
        card = g_pool["巅峰"]["pool"].choice(user)
        if card.player.Position in Const.FORWARD:
          index = random.randint(0, 5)
        elif card.player.Position in Const.MIDFIELD:
          index = random.randint(6, 11)
        elif card.player.Position in Const.GUARD:
          index = random.randint(12, 17)
        else:
          index = random.randint(18, 19)
        cards[index] = card

    ids = Bag.addToBagMany(user, cards)
    for i,card in enumerate(cards):
      result += "[" + str(ids[i]) + "] "
      result += card.format()
      result += '\n'
    result.rstrip("\n")
    user.spend(g_pool[pool]["cost"])
    user.setIsFirst("false")
    return result

def try_nb(user, pool):
    cards = []
    result = ""
    for i in range(10):
        card = g_pool["至尊"]["pool"].choice(user)
        cards.append(card)

    ids = Bag.addToBagMany(user, cards)
    for i,card in enumerate(cards):
      result += "[" + str(ids[i]) + "] "
      result += card.format() + "\n"
    result.rstrip("\n")
    user.spend(g_pool[pool]["cost"])
    user.setIsFirst("false")
    return result
    