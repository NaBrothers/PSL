import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
import data_base

positions = ["前锋", "中场", "后卫", "门将"]

result = "十连结果：\n"
for i in range(10):
    index = random.randint(0,3)
    result += data_base.getPlayer_external(positions[index],80)
    result += "\n"
print(result)
