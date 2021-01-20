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

return_text = '''抽卡 [卡包]：抽取一张球员卡
抽卡 十连 [卡包]：抽取十张球员卡
===== 初级卡包 =====
单抽 $400  十连 $3800  [初级]     初级球员卡包：随机获取一名球员
单抽 $750  十连 $7125  [初级前锋] 初级前锋卡包：随机获取一名前锋球员
单抽 $750  十连 $7125  [初级中场] 初级中场卡包：随机获取一名中场球员
单抽 $750  十连 $7125  [初级后卫] 初级后卫卡包：随机获取一名后卫球员
单抽 $750  十连 $7125  [初级门将] 初级门将卡包：随机获取一名门将球员
===== 中级卡包 =====
单抽 $1500 十连 $14250 [中级]     中级球员卡包：随机获取一名能力值84以上的球员
单抽 $2800             [中级前锋] 中级前锋卡包：随机获取一名能力值84以上的前锋球员
单抽 $2800             [中级中场] 中级中场卡包：随机获取一名能力值84以上的中场球员
单抽 $2800             [中级后卫] 中级后卫卡包：随机获取一名能力值84以上的后卫球员
单抽 $2800             [中级门将] 中级门将卡包：随机获取一名能力值84以上的门将球员
===== 特殊卡包 =====
单抽 $0 [新手] 新手限定卡包：二十张球员卡（前锋*6，中场*6，后卫*6，门将*2，至少一张能力值89以上）
'''

try_lottery = on_startswith(msg="抽卡", rule=to_me(), priority=1)

@try_lottery.handle()
async def try_lottery_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(try_lottery,event)
    args = str(event.message).split(" ")
    if len(args) == 1:
      await try_lottery.finish(toImage(return_text), **{'at_sender': True})
    elif len(args) == 2:
        if args[1] == "新手":
          await try_newbee(user, args[1])
        else:
          await try_single(user, args[1])
    elif len(args) == 3 and args[1] == "十连":
        await try_ten(user, args[2])
    else:
        await try_lottery.finish("格式错误！\n" + toImage(return_text), **{'at_sender': True})


async def try_single(user, pool):
  if pool not in g_pool.keys() or g_pool[pool]["visible"] == False:
      await try_lottery.finish("卡包不存在！\n" + toImage(return_text), **{'at_sender': True})
  
  if user.money < g_pool[pool]["cost"]:
      ret = "余额不足\n"
      ret += "需要球币：" + str(g_pool[pool]["cost"]) + "\n"
      ret += "剩余球币：" + str(user.money)
      await try_lottery.finish(toImage(ret), **{"at_sender": True})

  ret = g_pool[pool]["name"] + "：\n"
  card = g_pool[pool]["pool"].choice(user)
  id = Bag.addToBag(user, card)
  user.spend(g_pool[pool]["cost"])
  ret += "[" + str(id) + "] " + card.format() + "\n"
  ret += "剩余球币：" + str(user.money)
  await try_lottery.finish(toImage(ret), **{"at_sender": True})

async def try_ten(user, pool):
    if pool not in g_pool.keys() or g_pool[pool]["visible"] == False:
      await try_lottery.finish("卡包不存在！\n" + toImage(return_text), **{'at_sender': True})
    if "ten_cost" not in g_pool[pool].keys():
      await try_lottery.finish("卡包不支持十连！\n" + toImage(return_text), **{'at_sender': True})
    
    if user.money < g_pool[pool]["ten_cost"]:
      ret = "余额不足\n"
      ret += "需要球币：" + str(g_pool[pool]["ten_cost"]) + "\n"
      ret += "剩余球币：" + str(user.money)
      await try_lottery.finish(toImage(ret), **{"at_sender": True})

    cards = []
    ret = g_pool[pool]["name"] + "：\n"
    for i in range(10):
        card = g_pool[pool]["pool"].choice(user)
        cards.append(card)

    ids = Bag.addToBagMany(user, cards)
    for i,card in enumerate(cards):
      ret += "[" + str(ids[i]) + "] "
      ret += card.format() + "\n"
    ret.rstrip("\n")
    user.spend(g_pool[pool]["ten_cost"])
    ret += "剩余球币：" + str(user.money)
    await try_lottery.finish(toImage(ret), **{"at_sender": True})

async def try_newbee(user, pool):
    if not user.isFirst:
        await try_lottery.finish("你不是新手，抽nm呢", **{"at_sender": True})
    cards = []
    result = g_pool[pool]["name"] + "：\n"
    floored = False

    for i in range(6):
        card = g_pool["初级前锋"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    for i in range(6):
        card = g_pool["初级中场"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    for i in range(6):
        card = g_pool["初级后卫"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    for i in range(2):
        card = g_pool["初级门将"]["pool"].choice(user)
        if card.player.Overall > 88:
            floored = True
        cards.append(card)

    if not floored:
        card = g_pool["高级"]["pool"].choice(user)
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
    result += "剩余球币：" + str(user.money)
    await try_lottery.send(toImage(result), **{"at_sender": True})
    await try_lottery.finish("输入“背包”查看球员卡", **{"at_sender": True})

    