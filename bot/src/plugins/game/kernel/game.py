from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.kernel.account import check_account
from game.engine.game import Game
from game.model.user import User
from game.model.formation import Formation
from game.utils.database import *
game_matcher = on_startswith(msg="比赛", rule=to_me(), priority=1)

@game_matcher.handle()
async def game_matcher_handler(bot: Bot, event: Event, state: dict):
    await check_account(game_matcher, event)
    args = str(event.message).split(" ")
    if len(args) > 2:
      await game_matcher.finish("格式：比赛 ID", **{"at_sender": True})
      return
    if len(args) == 1:
      users = User.getAllUsers()
      ret = "请选择对手：\n"
      for user in users:
        if user.qq == event.user_id:
          continue
        ret += "[" + str(user.id) + "]\t" + user.name + "\n"
      ret += "输入“比赛 ID”挑战对手\n"
      ret += "输入“阵容 ID”查看对手阵容"
      await game_matcher.finish(toImage(ret), **{"at_sender": True})
      return
    if not args[1].isdecimal():
      await game_matcher.finish("格式：比赛 ID", **{"at_sender": True})
      return

    user1 = User.getUserByQQ(event.user_id)
    formation1 = Formation.getFormation(user1)
    if args[1] == str(user1.id):
      await game_matcher.finish("请不要挑战自己！", **{"at_sender": True})
      return
    if not formation1.isValid():
      await game_matcher.finish("阵容不完整！", **{"at_sender": True})
      return
    cursor = g_database.cursor()
    count = cursor.execute("select * from users where id = " + str(args[1]))
    if count == 0:
      await game_matcher.finish("找不到此对手", **{"at_sender": True})
      return
    
    user2 = User.getUserById(int(args[1]))
    formation2 = Formation.getFormation(user2)
    if not formation2.isValid():
      await game_matcher.finish("对手阵容不完整！", **{"at_sender": True})
      return
    game = Game(game_matcher, user1, user2)
    await game_matcher.send("开始比赛", **{"at_sender": True})
    await game.start()
  
