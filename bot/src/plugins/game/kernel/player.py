from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.card import *
from game.utils.image import *
from game.kernel.account import check_account

player_detail = on_startswith(msg="球员", rule=to_me(), priority=1)  
  
@player_detail.handle()
async def player_detailt_handler(bot: Bot, event: Event, state: dict):
  user = await check_account(player_detail,event)
  args = str(event.message).split(" ")
  if len(args) == 2 and args[1].isdecimal():
    card = Card.getCardByID(args[1])
    if card == None:
      await player_detail.finish("找不到该球员！输入\"背包\"查看拥有的球员卡", **{"at_sender": True})
      return
    img = getImage("/avatars/" + str(card.player.ID) + ".png")
    await player_detail.finish(img, **{"at_sender": True})
  else:
    await player_detail.finish("格式：球员 ID", **{"at_sender": True})