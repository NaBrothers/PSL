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

from .utils import database,const,pool
from .kernel import server,lottery
from .model import player,user

# 部署服务器
server.g_server.start()