import random
from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.utils.const import *
from game.kernel.pool import *
from game.kernel.account import check_account
from game.kernel.bag import *
from game.utils.text2image import toImage

return_text = '''所有卡包：
普通：一张任意位置球员卡
球星：一张任意位置球员卡（能力值84以上）
巨星：一张任意位置球员卡（能力值87以上）
前锋：一张前锋球员卡
中场：一张中场球员卡
后卫：一张后卫球员卡
门将：一张门将球员卡
十连：十张任意位置球员卡（至少一张能力值87以上）'''

try_lottery = on_startswith(msg="抽卡", rule=to_me(), priority=1)
#try_hundred = on_startswith(msg="百连", rule=to_me(), priority=1)

@try_lottery.handle()
async def try_lottery_handler(bot: Bot, event: Event, state: dict):
    user = check_account(event)
    args = str(event.message).split(" ")
    if len(args) > 1:
        pool = args[1]
        if pool not in g_pool.keys():
            await try_lottery.finish(toImage(return_text), **{'at_sender': True})
            return
        if (pool == "十连"):
          ret = try_ten(user, pool)
        else:
          ret = try_single(user, pool)
        await try_lottery.finish(toImage(ret), **{"at_sender": True})
    else:
        await try_lottery.finish("格式：抽卡 卡包\n" + toImage(return_text), **{'at_sender': True})

def try_single(user, pool):
  player = g_pool[pool].choice()
  Bag.add(user, player)
  return player.format()

def try_ten(user, pool):
    players = []
    result = ""
    floored = False
    for i in range(10):
        player = g_pool["普通"].choice()
        if i == 9 and not floored:
            player = g_pool["巨星"].choice()
        else:
            player = g_pool["普通"].choice()
        if player.Overall > 86:
            floored = True
        players.append(player)
        result += player.format()
        result += "\n"
    Bag.addMany(user, players)
    return result


def try_hundred(bot: Bot, event: Event, state: dict):
    user = check_account(event)
    arg = str(event.message)
    players = []
    result = ""
    for i in range(100):
        player = g_pool["normal"].choice()
        players.append(player)
        result += player.format()
        result += "\n"
    Bag.addMany(user, players)
    return result
