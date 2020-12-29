import pymysql
import random
from game.config import *
from game.utils.const import Const

class Database:

    def __init__(self):
      # 打开数据库连接
      self.db = pymysql.connect(HOSTNAME, USERNAME,
                         PASSWORD, DBNAME)
      self.db.autocommit(True)
      

    def __del__(self):
      self.db.close()

    # 获取一个游标
    def cursor(self):
      return self.db.cursor()

    # 更新数据库
    def update(self, sql :str):
      cursor = self.db.cursor()
      cursor.execute(sql)
      cursor.close()

# 全局数据库
g_database = Database()