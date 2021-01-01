import requests
from game.utils.database import *
from nonebot.log import logger
import os

def download_avatars():
  cursor = g_database.cursor()
  count = cursor.execute("select ID,Photo from players")
  urls = cursor.fetchall()
  path = PROJECT_DIR + "/assets/avatars/"
  if not os.path.exists(path):
    os.mkdir(path)
  else:
    return
  logger.info("开始下载头像")
  for url in urls:
    filename = str(url[0]) + ".png"
    if os.path.exists(path + filename):
      continue
    r = requests.get(url[1])
    if r.status_code == 200:
      open(path + filename, 'wb').write(r.content)
    else:
      logger.warning("下载头像失败：id = " + str(url[0]))
      r = requests.get("https://cdn.sofifa.com/players/notfound_0_60.png")
      open(path + filename, 'wb').write(r.content)
    del r