# import nonebot
from nonebot import get_driver

from .config import Config

global_config = get_driver().config
config = Config(**global_config.dict())

# Export something for other plugin
# export = nonebot.export()
# export.foo = "bar"

# @export.xxx
# def some_function():
#     pass

# 添加一个新的功能（监听事件），在此处import
from .kernel import server,lottery,query,account,bag,admin,payment,transfer,help,player,game,formation,league,challenge