from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.utils.text2image import toImage

user_profile = on_startswith(msg="账号", rule=to_me(), priority=1)



def check_account(event):
  qq = event.sender["user_id"]
  name = event.sender["nickname"].replace("'", "''")
  user = User.getUserByQQ(qq)
  if (user == None):
    # 第一次登陆
    sql = "insert into users (qq, name, level, money) values (" + str(qq) + ",'" + name + "',0, 0)"
    cursor = g_database.cursor()
    cursor.execute(sql)
    cursor.execute("select * from users where qq = " + str(qq))
    user = User(cursor.fetchone())
    cursor.close()

  return user
  
  
@user_profile.handle()
async def user_profile_handler(bot: Bot, event: Event, state: dict):
  user = check_account(event)
  await user_profile.finish(toImage(user.format()), **{"at_sender": True})

