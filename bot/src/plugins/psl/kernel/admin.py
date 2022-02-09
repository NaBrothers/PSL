import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.image import toImage
from model import offline
from model.user import User
from kernel.account import check_account
from utils.database import *
from kernel.server import *

admin_test = on_startswith(msg="测试", rule=to_me(), priority=1)
admin_broadcast = on_startswith(msg="广播", rule=to_me(), priority=1)
admin_admin = on_startswith(msg="admin", rule=to_me(), priority=1)
admin_reset = on_startswith(msg="重启", rule=to_me(), priority=1)
admin_private = on_startswith(msg="私聊", rule=to_me(), priority=1)

@admin_reset.handle()
async def reset_handler(bot: Bot, event: Event):
    user = await check_account(admin_reset,event)
    if not user.isAdmin:
        await admin_reset.finish("没有管理员权限！",  **{'at_sender': True})
    g_server.set("in_game", False)
    await admin_reset.finish("重启成功！", **{'at_sender': True})

@admin_test.handle()
async def test_handler(bot: Bot, event: Event):
    user = await check_account(admin_test,event)
    if not user.isAdmin:
        await admin_test.finish("没有管理员权限！",  **{'at_sender': True})
    await admin_test.finish(toImage(str(event.message).lstrip("测试 ")), **{'at_sender': True})

@admin_broadcast.handle()
async def broadcast_handler(bot: Bot, event: Event):
    user = await check_account(admin_broadcast,event)
    # if not user.isAdmin:
    #   await admin_broadcast.finish("没有管理员权限！",  **{'at_sender': True})
    msg = str(event.message).split("广播", 1)[1]
    offline.Offline.broadcast(user, msg)
    await admin_broadcast.finish("发送成功！",  **{'at_sender': True})

@admin_private.handle()
async def private_handler(bot: Bot, event: Event):
    user = await check_account(admin_broadcast,event)
    args = str(event.message).split(" ", 3)
    if len(args) < 3 or not args[1].isdecimal():
          await private_handler.finish("格式错误：私聊 [ID] [消息] ",  **{'at_sender': True})
    print(args[1])
    target = User.getUserById(args[1])
    if target is None:
          await private_handler.finish("找不到该用户",  **{'at_sender': True})
    offline.Offline.send(target, "来自" + user.name + "的消息：" + args[2])
    await admin_broadcast.finish("发送成功！",  **{'at_sender': True})

@admin_admin.handle()
async def admin_handler(bot: Bot, event: Event):
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