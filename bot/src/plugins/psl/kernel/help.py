from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.image import toImage
from kernel.account import check_account

help_menu = on_startswith(msg="帮助", rule=to_me(), priority=1)

@help_menu.handle()
async def help_menu_handler(bot: Bot, event: Event):
    await check_account(help_menu, event)
    ret = '''| 比赛 | 联赛 | 挑战 |
| 背包 | 阵容 | 球员 |
| 抽卡 | 转会 | 账号 |
| 查询 | 充值 |
'''
    await help_menu.finish("游戏菜单："+toImage(ret), **{'at_sender': True})
