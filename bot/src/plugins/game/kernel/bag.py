import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.player import *
from game.model.bag import *
from game.kernel.account import check_account
from game.utils.text2image import toImage

user_bag = on_startswith(msg="背包", rule=to_me(), priority=1)

@user_bag.handle()
async def user_bag_handler(bot: Bot, event: Event, state: dict):
  user = check_account(event)
  bag = Bag.getBagByUser(user)
  ret = ""
  if (bag != None):
    for (id, player) in bag.players:
      ret += "[" + str(id) + "]\t"
      ret += player.format()
      ret += "\n"
  await user_bag.finish("当前背包：\n" + toImage(ret), **{"at_sender": True})