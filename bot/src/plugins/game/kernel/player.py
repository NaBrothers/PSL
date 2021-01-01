from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.utils.text2image import toImage
from game.kernel.account import check_account

player_detail = on_startswith(msg="球员", rule=to_me(), priority=1)  
  
@player_detail.handle()
async def player_detailt_handler(bot: Bot, event: Event, state: dict):
  user = await check_account(user_profile,event)
  args = str(event.message).split(" ")
  if len(args) == 2 and args[1].isdecimal():
    pass
  else:
    await player_detail.finish("格式：球员 ID", **{"at_sender": True})