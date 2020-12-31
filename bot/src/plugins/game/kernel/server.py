from nonebot.log import logger
from game.utils.database import *
from game.config import *
# 服务器类
class Server:
  def __init__(self):
    self.start()

  # 服务器启动逻辑
  def start(self):
    logger.info("PSL启动!")
    if PICTURE_MODE:
      logger.info("当前模式：图片模式")
    else:
      logger.info("当前模式：文字模式")

  def close(self):
    logger.info("PSL关闭!")

# 全局服务器
g_server = Server()