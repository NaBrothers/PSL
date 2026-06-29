from utils.database import *
from model.user import *
from model.globalAttr import Global
from utils.date import Date
import json

def _get_daily_attempts():
    try:
        cursor = g_database.cursor()
        cursor.execute('SELECT Value FROM "global" WHERE Name = ?', ("config:challenge.daily_attempts",))
        row = cursor.fetchone()
        cursor.close()
        if row:
            return json.loads(row[0])
    except:
        pass
    return Const.TIMES_EVERYDAY

class ChallengeTimes:
    def __init__(self, data):
        self.id = data[0]
        self.user = User.getUserByQQ(data[1])
        self.times = data[2]

    def getTimes(user):
        cursor = g_database.cursor()
        old_date = Global.get("date")
        cur_date = Date.getCurrentDate()
        if cur_date != old_date:
          Global.set("date", cur_date)
          cursor.execute("update challenge_times set timesleft = " + str(_get_daily_attempts()))
        count = cursor.execute("select * from challenge_times where User = " + str(user.qq))
        if count == 0:
          cursor.execute("insert into challenge_times (User, TimesLeft) values (" + str(user.qq) + "," + str(_get_daily_attempts()) + ")")
          cursor.execute("select * from challenge_times where User = " + str(user.qq))
        cursor.close()
        return ChallengeTimes(cursor.fetchone())

    def setTimes(self, times):
        cursor = g_database.cursor()
        count = cursor.execute("update challenge_times set timesleft = " + str(times) + " where id = " + str(self.id))
        cursor.close()
