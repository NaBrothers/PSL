from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.database import *
from model.user import *
from model.item import Item
from utils.image import toImage
from model.offline import *


user_profile = on_startswith(msg="账号", rule=to_me(), priority=1)

async def check_account(matcher, event):
  qq = event.sender.user_id
  name = event.sender.nickname.replace("'", "''")
  user = User.getUserByQQ(qq)
  if (user == None):
    # 第一次登陆
    await matcher.send("欢迎加入游戏！送你一发新手卡包，输入\"抽卡 奖励 新手\"获取", **{"at_sender": True})
    await matcher.send("输入\"帮助\"获取游戏菜单", **{"at_sender": True})
    user = User.addUser(qq, name)
    Item.addItem(user, 0, 0, 1)

  # 查询离线消息
  message = Offline.get(user)
  for msg in message:
    await matcher.send(msg, **{"at_sender" : True})
  Offline.remove(user)
  return user
  
  
@user_profile.handle()
async def user_profile_handler(bot: Bot, event: Event):
  user = await check_account(user_profile,event)
  ret = str(user.qq) + " " + user.name + " " + str(user.level) + "级\n" + "球币：" + str(user.money)
  await user_profile.finish(toImage(ret), **{"at_sender": True})


