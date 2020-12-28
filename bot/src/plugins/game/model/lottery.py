import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils import database

positions = ["前锋", "中场", "后卫", "门将"]

stars = {80:"★",81:"★",
         82:"★★",83:"★★",
         84:"★★★",85:"★★★",86:"★★★",
         87:"★★★★",88:"★★★★",
         89:"★★★★★",90:"★★★★★",
         91:"★★★★★",92:"★★★★★",93:"★★★★★"}

         
try_single = on_startswith(msg="抽卡", rule=to_me(), priority=2)
try_ten = on_startswith(msg="抽卡十连", rule=to_me(), priority=1)
try_hundred = on_startswith(msg="抽卡百连", rule=to_me(), priority=1)

@try_single.handle()
async def try_single_handler(bot: Bot, event: Event, state: dict):
    args = str(event.message).split(" ")
    if len(args)>1 and args[0]=="抽卡":
        state["pool"] = args[1]
        if state["pool"] not in positions:
            await test.finish("位置：前锋，中场，后卫，门将",**{'at_sender':True})
        
        result = database.getPlayer_external(state["pool"],80)
        name = result.split(",")[0]
        overall = int(result.split(",")[1])
        pos = result.split(",")[2]
        photo_url = result.split(",")[3]
        
        await try_single.finish(name+" "+str(overall)+" "+pos+" "+stars[overall],**{"at_sender":True})

    elif args[0]=="抽卡":
        await try_single.finish("抽卡格式：抽卡 位置",**{'at_sender':True})



@try_ten.handle()
async def try_ten_handler(bot: Bot, event: Event, state: dict):
    arg = str(event.message)
    if arg=="抽卡十连":
        result = "十连结果：\n"
        floored = False
        for i in range(10):
            index = random.randint(0,3)
            if i==9 and not floored:
                tmp = database.getPlayer_external(positions[index],87)
            else:
                tmp = database.getPlayer_external(positions[index],80)
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
        await try_ten.finish(result,**{'at_sender':True})
    else:
        await try_ten.finish(arg)

@try_hundred.handle()
async def try_hundred_handler(bot: Bot, event: Event, state: dict):
    arg = str(event.message)
    if arg=="抽卡百连":
        result = "百连结果：\n"
        floored = False
        for i in range(100):
            index = random.randint(0,3)
            tmp = database.getPlayer_external(positions[index],80)
            name = tmp.split(",")[0]
            overall = int(tmp.split(",")[1])
            pos = tmp.split(",")[2]
            photo_url = tmp.split(",")[3]
            result += name
            result += " "
            result += str(overall)
            result += " "
            result += pos
            result += " "
            result += stars[overall]
            result += "\n"
        await try_hundred.finish(result,**{'at_sender':True})
    else:
        await try_hundred.finish(arg)