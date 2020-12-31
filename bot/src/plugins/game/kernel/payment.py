from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.utils.text2image import toImage
from game.kernel.account import *
payment = on_startswith(msg="充值", rule=to_me(), priority=1)  
  
@payment.handle()
async def payment_handler(bot: Bot, event: Event, state: dict):
  user = await check_account(user_profile,event)
  args = str(event.message).split(" ")
  if len(args) > 1:
    if args[1].isdecimal() and int(args[1]) > 0:
      user.earn(int(args[1]))
      ret = "充值成功！\n剩余球币：" + str(user.money)
      await payment.finish(toImage(ret), **{"at_sender": True})
    else:
      await payment.finish("格式：充值 金额", **{"at_sender": True})
  else:
    await payment.finish("格式：充值 金额", **{"at_sender": True})