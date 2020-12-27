import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from . import data_base

positions = ["前锋", "中场", "后卫", "门将"]

stars = {80:"★",81:"★",
         82:"★★",83:"★★",
         84:"★★★",85:"★★★",86:"★★★",
         87:"★★★★",88:"★★★★",
         89:"★★★★★",90:"★★★★★",
         91:"★★★★★",92:"★★★★★",93:"★★★★★"}

test2 = on_startswith(msg="抽卡十连", rule=to_me(), priority=1)

@test2.handle()
async def handle_first_receive2(bot: Bot, event: Event, state: dict):
    arg = str(event.message)
    if arg=="抽卡十连":
        result = "十连结果：\n"
        floored = False
        for i in range(10):
            index = random.randint(0,3)
            if i==9 and not floored:
                tmp = data_base.getPlayer_external(positions[index],87)
            else:
                tmp = data_base.getPlayer_external(positions[index],80)
            name = tmp.split(",")[0]
            overall = int(tmp.split(",")[1])
            pos = tmp.split(",")[2]
            photo_url = tmp.split(",")[3]
            if overall>86:
                floored = True
            result += name
            result += " "
            result += str(overall)
            result += " "
            result += pos
            result += " "
            result += stars[overall]
            result += "\n"
        await test2.finish(result,**{'at_sender':True})
    else:
        await test2.finish(arg)

