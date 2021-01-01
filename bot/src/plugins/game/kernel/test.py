import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.model import offline
from game.kernel.account import check_account

test_test = on_startswith(msg="测试", rule=to_me(), priority=1)
test_broadcast = on_startswith(msg="广播", rule=to_me(), priority=1)


@test_test.handle()
async def test_handler(bot: Bot, event: Event, state: dict):
    await test_test.finish(toImage(str(event.message).lstrip("测试 ")), **{'at_sender': True})

@test_broadcast.handle()
async def broadcast_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(test_broadcast,event)
    msg = str(event.message).split("广播")[1]
    offline.Offline.broadcast(user, msg)