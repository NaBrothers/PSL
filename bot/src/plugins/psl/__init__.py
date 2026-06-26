# import nonebot

from nonebot import get_driver

from .config import *

import sys
sys.path.append(PROJECT_DIR + "/bot/src/plugins/psl")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

global_config = get_driver().config
config = Config(**global_config.dict())

# Export something for other plugin
# export = nonebot.export()
# export.foo = "bar"

# @export.xxx
# def some_function():
#     pass

# 添加一个新的功能（监听事件），在此处import
from kernel import server,lottery,query,account,bag,admin,payment,transfer,help,player,game,formation,league,challenge

from utils.replay_server import start_replay_server

start_replay_server(8888)
