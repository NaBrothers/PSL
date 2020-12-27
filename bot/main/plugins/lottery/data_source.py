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

test = on_startswith(msg="抽卡", rule=to_me(), priority=2)

@test.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    args = str(event.message).split(" ")
    if len(args)>1 and args[0]=="抽卡":
        state["pool"] = args[1]
        if state["pool"] not in positions:
            await test.finish("位置：前锋，中场，后卫，门将")
        
        result = data_base.getPlayer_external(state["pool"],80)
        name = result.split(",")[0]
        overall = int(result.split(",")[1])
        pos = result.split(",")[2]
        photo_url = result.split(",")[3]
        
        await test.finish(name+" "+str(overall)+" "+pos+" "+stars[overall],**{"at_sender":True})

    elif args[0]=="抽卡":
        await test.finish("抽卡格式：抽卡 位置")

