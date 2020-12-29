from nonebot.log import logger
from game.utils.database import *

# 服务器类
class Server:
  # 服务器启动逻辑
  def start(self):
    logger.info("PSL启动!")

  def close(self):
    logger.info("PSL关闭!")

# 全局服务器
g_server = Server()