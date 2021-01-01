from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.player import *
from game.utils.text2image import toImage
from game.kernel.account import check_account

query_player = on_startswith(msg="查询", rule=to_me(), priority=1)


@query_player.handle()
async def query_player_handler(bot: Bot, event: Event, state: dict):
    await check_account(query_player, event)
    args = str(event.message).split(" ", 1)
    if len(args) > 1:
        cursor = g_database.cursor()
        try:
            count = cursor.execute(
                "select * from players where " + args[1])
        except Exception as e:
            await query_player.finish("格式错误", **{"at_sender": True})
            return
        if (count == 0):
            await query_player.finish("没有查询到任何信息", **{"at_sender": True})
            return
        result = cursor.fetchall()
        cursor.close()

        ret = ""
        for i in range(min(20, count)):
            ret += Player(result[i]).format()
            ret += "\n"
        if (count > 20):
            ret += "共查询到"+str(count)+"个结果，只显示前20条"

        await query_player.finish("查询到以下球员：\n" + toImage(ret), **{"at_sender": True})
    else:
        await query_player.finish("格式：查询 代码", **{'at_sender': True})
