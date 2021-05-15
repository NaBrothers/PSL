from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.kernel.account import check_account
from game.engine.game import Game
from game.model.user import User
from game.model.formation import Formation
from game.utils.database import *
from game.kernel.server import *
game_matcher = on_startswith(msg="比赛", rule=to_me(), priority=1)

return_text = '''比赛 ID：挑战对手
比赛 快速 ID：只显示比赛结果
比赛 十连 ID：挑战十次对手
比赛 赔率 ID：计算与对手的比赛的赔率
阵容 ID：查看对手阵容
'''


@game_matcher.handle()
async def game_matcher_handler(bot: Bot, event: Event, state: dict):
    mode = 0
    if g_server.get("in_game") == True:
        await game_matcher.finish("比赛正在进行中！", **{"at_sender": True})
    await check_account(game_matcher, event)
    args = str(event.message).split(" ")
    if len(args) == 1:
        users = User.getAllUsers()
        ret = "请选择对手：\n"
        for user in users:
            if user.qq == event.user_id:
                continue
            ret += "[" + str(user.id) + "]\t" + user.name + "\n"
        ret += return_text
        await game_matcher.finish(toImage(ret), **{"at_sender": True})
        return


    if len(args) == 3 and args[1] == "快速" and args[2].isdecimal():
        mode = 1
        str_id = args[2]
    elif len(args) == 3 and args[1] == "十连" and args[2].isdecimal():
        mode = 3
        str_id = args[2]
    elif len(args) == 3 and (args[1] == "赔率" or args[1] == "pl") and args[2].isdecimal():
        mode = 4
        str_id = args[2]
    elif len(args) == 2 and args[1].isdecimal():
        str_id = args[1]
    else:
        await game_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return

    user1 = User.getUserByQQ(event.user_id)
    formation1 = Formation.getFormation(user1)
    # if str_id == str(user1.id):
    #     await game_matcher.finish("请不要挑战自己！", **{"at_sender": True})
    #     return
    if not formation1.isValid():
        await game_matcher.finish("阵容不完整！", **{"at_sender": True})
        return
    cursor = g_database.cursor()
    count = cursor.execute("select * from users where id = " + str_id)
    if count == 0:
        await game_matcher.finish("找不到此对手", **{"at_sender": True})
        return

    user2 = User.getUserById(int(str_id))
    formation2 = Formation.getFormation(user2)
    if not formation2.isValid():
        await game_matcher.finish("对手阵容不完整！", **{"at_sender": True})
        return

    

    if mode == 3:
      g_server.set("in_game", True)
      ret = "[十连结果]\n"
      home_goal = 0
      away_goal = 0
      win = 0
      tie = 0
      lose = 0
      for i in range(10):
        game = Game(game_matcher, user1, user2)
        await game.start(mode)
        ret += "主 " + game.home.coach.name + " " + str(game.home.goals) + ":" + str(game.away.goals) + " " + game.away.coach.name + " 客\n"
        home_goal += game.home.goals
        away_goal += game.away.goals
        if game.home.goals > game.away.goals:
          win += 1
        elif game.home.goals < game.away.goals:
          lose += 1
        else:
          tie += 1
      ret += "[数据统计]\n"
      ret += "总比分："  + str(home_goal) + ":" + str(away_goal) + "\n"
      ret += "赛果：" + str(win) + "胜" + str(tie) + "平" + str(lose) + "负\n"
      ret += "胜率：" + str(round(win*100/10, 1)) + "%:" + str(round(lose*100/10, 1)) + "%\n"
      g_server.set("in_game", False)
      await game_matcher.finish(toImage(ret), **{"at_sender": True})

    if mode == 4:
      g_server.set("in_game", True)
      ret = "[赔率]\n"
    #   home_goal = 0
    #   away_goal = 0
      win = 1
      tie = 1
      lose = 1
      for i in range(20):
        game = Game(game_matcher, user1, user2)
        await game.start(3)
        # home_goal += game.home.goals
        # away_goal += game.away.goals
        if game.home.goals > game.away.goals:
          win += 1
        elif game.home.goals < game.away.goals:
          lose += 1
        else:
          tie += 1
      ret += "主胜" + str(format(23/win,'.2f')) + " "
      ret += "平局" + str(format(23/tie,'.2f')) + " "
      ret += "客胜" + str(format(23/lose,'.2f')) + " "
      g_server.set("in_game", False)
      await game_matcher.finish(toImage(ret), **{"at_sender": True})

    game = Game(game_matcher, user1, user2)

    g_server.set("in_game", True)
    try:
        await game.start(mode)
    except Exception as e:
        print(e)
    finally:
        g_server.set("in_game", False)