from game.model.user import *
from game.utils.database import *
class Offline:
  def get(user):
    ret = []
    cursor = g_database.cursor()
    count = cursor.execute("select message from offline where user = " + str(user.qq))
    cursor.close()
    for i in range(count):
      ret.append(cursor.fetchone()[0])
    return ret

  def send(user, msg):
    msg = msg.replace("\\", "\\\\")
    msg = msg.replace("\n", "\\n")
    msg = msg.replace("\t", "\\t")
    msg = msg.replace("'", "''")
    msg = "'" + msg + "'"
    cursor = g_database.cursor()
    count = cursor.execute("insert into offline (user, message) values (" + str(user.qq) + ", " + msg + ")")
    cursor.close()

  def remove(user):
    cursor = g_database.cursor()
    count = cursor.execute("delete from offline where user = " + str(user.qq))
    cursor.close()

  def broadcast(user, msg):
    msg = msg.replace("\\", "\\\\")
    msg = msg.replace("\n", "\\n")
    msg = msg.replace("\t", "\\t")
    msg = "'来自" + user.name + "的广播：" + msg + "'"
    cursor = g_database.cursor()
    count = cursor.execute("select qq from users")
    qqs = cursor.fetchall()
    for qq in qqs:
      if qq[0] == user.qq:
        continue
      count = cursor.execute("insert into offline (user, message) values (" +  str(qq[0]) + "," + msg + ")")
    cursor.close()

