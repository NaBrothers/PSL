from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.player import *
from game.model.bag import *
from game.model.user import *
from game.utils.text2image import toImage

transfer = on_startswith(msg="转会", rule=to_me(), priority=1)

@transfer.handle()
async def transfer_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(try_lottery,event)
    args = str(event.message).split(" ")
    if len(args) <= 1:
      await show_transfer_window()

async def show_transfer_window:
    ret = "转会窗口：\n"