import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.model import offline
from game.kernel.account import check_account
from game.utils.database import *
from game.kernel.server import *

admin_test = on_startswith(msg="测试", rule=to_me(), priority=1)
admin_broadcast = on_startswith(msg="广播", rule=to_me(), priority=1)
admin_admin = on_startswith(msg="admin", rule=to_me(), priority=1)
admin_reset = on_startswith(msg="重启", rule=to_me(), priority=1)

@admin_reset.handle()
async def reset_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(admin_reset,event)
    if not user.isAdmin:
        await admin_reset.finish("没有管理员权限！",  **{'at_sender': True})
    g_server.set("in_game", False)
    await admin_reset.finish("重启成功！", **{'at_sender': True})

@admin_test.handle()
async def test_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(admin_test,event)
    if not user.isAdmin:
        await admin_test.finish("没有管理员权限！",  **{'at_sender': True})
    await admin_test.finish(toImage(str(event.message).lstrip("测试 ")), **{'at_sender': True})

@admin_broadcast.handle()
async def broadcast_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(admin_broadcast,event)
    if not user.isAdmin:
      await admin_broadcast.finish("没有管理员权限！",  **{'at_sender': True})
    msg = str(event.message).split("广播")[1]
    offline.Offline.broadcast(user, msg)

@admin_admin.handle()
async def admin_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(admin_admin, event)
    if not user.isAdmin:
      await admin_admin.finish("没有管理员权限！",  **{'at_sender': True})
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
    await admin_admin.finish(ret, **{'at_sender': True})