import random
import math
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.player import *
from game.model.bag import *
from game.kernel.account import check_account
from game.utils.image import toImage

user_bag = on_startswith(msg="背包", rule=to_me(), priority=1)

return_text = '''背包 页码：跳转到指定页
背包 查询 球员名：查找同名球员卡
背包 回收 ID：按身价一半出售给系统，可以同时指明多个ID
球员 ID：查看详细信息
'''

@user_bag.handle()
async def user_bag_handler(bot: Bot, event: Event, state: dict):
    arg = str(event.message).split(" ")
    user = await check_account(user_bag, event)
    bag = Bag.getBag(user)
    if (len(arg) == 1):
        await get_bag_by_page(bag, "1")
    elif len(arg) == 3 and arg[1] == "查询":
        await query_bag(bag, arg[2])
    elif len(arg) == 2:
        if arg[1].isdecimal():
            await get_bag_by_page(bag, arg[1])
        else:
            await user_bag.finish("格式错误！"+toImage(return_text), **{"at_sender": True})
            return
    elif arg[1] == "回收":
        await recycle_cards(user,bag, arg[2:])
    else:
        await user_bag.finish("格式错误！"+toImage(return_text), **{"at_sender": True})
        
async def recycle_cards(user,bag, card_ids):
    for id in card_ids:
      if not id.isdecimal():
        await user_bag.finish("格式错误！"+toImage(return_text), **{"at_sender": True})
    cards = Card.getCardByIDMany(card_ids)
    money = 0
    success = []
    failed = []
    failed_str = []
    for card in cards:
      if card.status != 0:
        failed.append(str(card.id))
        failed_str.append(Const.STATUS[card.status] + "：" + card.format() + "\n")
        continue
      money += card.price // 2
      card.remove()
      success.append(str(card.id))
    for id in card_ids:
      if id not in success and id not in failed:
        failed_str.append("找不到ID：" + id + "\n")
    ret = "成功回收" + str(len(success)) + "个球员:\n"
    for s in success:
      ret += s
    if len(failed_str):
      ret += str(len(failed_str)) + "个球员回收失败：\n"
    for f in failed_str:
      ret += f
    ret += "获得球币：" + str(money) + "\n"
    user.earn(money)
    ret += "剩余球币：" + str(user.money)
    await user_bag.finish(toImage(ret), **{"at_sender": True})

async def get_bag_by_page(bag: Bag, page: str):
    if bag == None:
      await user_bag.finish("当前背包为空", **{"at_sender":True})
    total_page = math.ceil(len(bag.cards) / 20)
    page = int(page)
    if page > total_page or page <= 0:
        await user_bag.finish("页码错误", **{"at_sender": True})
        return

    ret = ""
    if (bag != None):
        for i in range(20):
            index = (page - 1) * 20 + i
            if index >= len(bag.cards):
                break
            card = bag.cards[index]
            ret += "[" + str(card.id) + "]\t"
            ret += card.format()
            ret += "\n"
    foot = "第" + str(page) + "页 共" + str(total_page) + "页\n"
    await user_bag.finish("当前背包：\n" + toImage(ret+foot+return_text), **{"at_sender": True})

async def query_bag(bag, name):
    ret = ""
    if bag != None:
      for card in bag.cards:
        if name.lower() in card.player.Name.lower():
          ret += "[" + str(card.id) + "]\t"
          ret += card.format()
          ret += "\n"
    await user_bag.finish("当前背包：\n" + toImage(ret+return_text), **{"at_sender": True})