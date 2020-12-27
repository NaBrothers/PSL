from nonebot import on_command, on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event

test = on_startswith(msg="抽卡", rule=to_me(), priority=2)

@test.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    args = str(event.message).split(" ")
    if len(args)>1 and args[0]=="抽卡":
        state["pool"] = args[1]
        if state["pool"] not in ["前锋", "中场", "后卫", "门将"]:
            await test.finish("位置：前锋，中场，后卫，门将")
        await test.finish("抽到了一个屁")

    elif args[0]=="抽卡":
        await test.finish("抽卡格式：抽卡 位置")
    
