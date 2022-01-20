import pymysql
import random
from config import *
from utils.const import Const

class Database:

    def __init__(self):
      # 打开数据库连接
      self.db = pymysql.connect(host=HOSTNAME, user=USERNAME,
                         password=PASSWORD, db=DBNAME)
      self.db.autocommit(True)
      

    def __del__(self):
      self.db.close()

    # 获取一个游标
    def cursor(self):
      self.db.ping(reconnect=True)
      return self.db.cursor()

    # 更新数据库
    def update(self, sql :str):
      cursor = self.db.cursor()
      cursor.execute(sql)
      cursor.close()

# 全局数据库
g_database = Database()
