import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.model import offline
from game.kernel.account import check_account
from game.utils.database import *

test_test = on_startswith(msg="测试", rule=to_me(), priority=1)
test_broadcast = on_startswith(msg="广播", rule=to_me(), priority=1)
test_admin = on_startswith(msg="admin", rule=to_me(), priority=1)

@test_test.handle()
async def test_handler(bot: Bot, event: Event, state: dict):
    await test_test.finish(toImage(str(event.message).lstrip("测试 ")), **{'at_sender': True})

@test_broadcast.handle()
async def broadcast_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(test_broadcast,event)
    msg = str(event.message).split("广播")[1]
    offline.Offline.broadcast(user, msg)

@test_admin.handle()
async def admin_handler(bot: Bot, event: Event, state: dict):
    cursor = g_database.cursor()
    msg = str(event.message).split("admin")[1]
    try:
      count = cursor.execute(msg)
      ret = "执行成功\n"
      result = ""
      items = cursor.fetchall()
      for item in items:
        result += str(item) + "\n"
      ret += toImage(result)
    except Exception as e:
      ret = "执行失败\n" + toImage(str(e))
    finally:
      cursor.close()
    await test_test.finish(ret, **{'at_sender': True})