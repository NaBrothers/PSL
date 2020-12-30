import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event

test_test = on_startswith(msg="测试", rule=to_me(), priority=1)

@test_test.handle()
async def test_handler(bot: Bot, event: Event, state: dict):
    await test_test.finish("test", **{'at_sender': True})