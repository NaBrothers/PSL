from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.text2image import toImage
from game.kernel.account import check_account

help_menu = on_startswith(msg="帮助", rule=to_me(), priority=1)

@help_menu.handle()
async def help_menu_handler(bot: Bot, event: Event, state: dict):
    await check_account(help_menu, event)
    ret = '''| 账号 | 背包 | 转会 |
| 抽卡 | 查询 | 充值 |
'''
    await help_menu.finish("游戏菜单："+toImage(ret), **{'at_sender': True})
