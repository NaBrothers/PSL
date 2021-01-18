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

in_game = False

return_text = '''比赛 ID：挑战对手
比赛 快速 ID：只显示比赛结果
阵容 ID：查看对手阵容"
'''


@game_matcher.handle()
async def game_matcher_handler(bot: Bot, event: Event, state: dict):
    global in_game
    quick_flag = False
    if in_game:
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
        quick_flag = True
        str_id = args[2]
    elif len(args) == 2 and args[1].isdecimal():
        str_id = args[1]
    else:
        await game_matcher.finish("格式错误！" + toImage(return_text), **{"at_sender": True})
        return

    user1 = User.getUserByQQ(event.user_id)
    formation1 = Formation.getFormation(user1)
    if str_id == str(user1.id):
        await game_matcher.finish("请不要挑战自己！", **{"at_sender": True})
        return
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
    game = Game(game_matcher, user1, user2)
    if not quick_flag:
        await game_matcher.send("开始比赛", **{"at_sender": True})
    in_game = True
    await game.start(quick_flag)
    in_game = False
