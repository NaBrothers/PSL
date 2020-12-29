import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.utils.const import *
from game.utils.pool import *
from game.kernel.account import check_account
from game.kernel.bag import *

try_single = on_startswith(msg="抽卡", rule=to_me(), priority=1)
try_ten = on_startswith(msg="十连", rule=to_me(), priority=1)
try_hundred = on_startswith(msg="百连", rule=to_me(), priority=1)


@try_single.handle()
async def try_single_handler(bot: Bot, event: Event, state: dict):
    user = check_account(event)
    args = str(event.message).split(" ")
    if len(args) > 1:
        pos = state["pool"] = args[1]
        if state["pool"] not in Const.POSITIONS:
            await try_single.finish("位置：前锋，中场，后卫，门将", **{'at_sender': True})
            return
        if (pos == "前锋"):
          player = random.choice(g_pool.forward)
        elif (pos == "中场"):
          player = random.choice(g_pool.midfield)
        elif (pos == "后卫"):
          player = random.choice(g_pool.guard)
        elif (pos == "门将"):
          player = random.choice(g_pool.goalkeeper)
        Bag.add(user, player)
        await try_single.finish(player.format(), **{"at_sender": True})
    else:
        await try_single.finish("抽卡格式：抽卡 位置", **{'at_sender': True})


@try_ten.handle()
async def try_ten_handler(bot: Bot, event: Event, state: dict):
    check_account(event)
    arg = str(event.message)
    if arg == "十连":
        result = "十连结果：\n"
        floored = False
        for i in range(10):
            player = random.choice(g_pool.normal)
            if i == 9 and not floored:
                player = random.choice(g_pool.vip)
            else:
                player = random.choice(g_pool.normal)
            if player.Overall > 86:
                floored = True
            result += player.format()
            result += "\n"
        await try_ten.finish(result, **{'at_sender': True})
    else:
        await try_ten.finish(arg)


@try_hundred.handle()
async def try_hundred_handler(bot: Bot, event: Event, state: dict):
    check_account(event)
    arg = str(event.message)
    if arg == "百连":
        result = "百连结果：\n"
        for i in range(100):
            player = random.choice(g_pool.normal)
            result += player.format()
            result += "\n"
        await try_hundred.finish(result, **{'at_sender': True})
    else:
        await try_hundred.finish(arg)
