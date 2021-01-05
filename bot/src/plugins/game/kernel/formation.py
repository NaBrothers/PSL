from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.card import *
from game.kernel.account import *
from game.model.formation import *
from game.utils.image import toImage

get_team = on_startswith(msg="阵容", rule=to_me(), priority=1)

error_text = '''
'''

@get_team.handle()
async def get_team_handler(bot: Bot, event: Event, state: dict):
  user = await check_account(get_team, event)
  args = str(event.message).split(" ")
  if len(args) == 1:
    await show_team(user)
  else:
    await get_team.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})

async def show_team(user):
  team = Formation.getFormation(user)
  ret = ""  
  ret += "教练：" + user.name + "\n"
  ret += "阵容：" + team.formation + "\n"
  ret += "===== 主力 =====\n"
  for i,card in enumerate(team.cards):
    ret += str(i).ljust(2) + "  "
    if i <= 10:
      ret += Const.FORMATION[team.formation][i].ljust(3) + "  "
    else:
      if card == None:
        ret += "无" + "   "
      else:
        ret += card.player.Position.ljust(3) + " "
    if card == None:
      ret += "空缺"
    else:
      ret += "[" + str(card.id) + "] " + card.format()
    ret += "\n"
    if i == 10:
      ret += "===== 替补 =====\n"
  await get_team.finish("当前阵容：\n" + toImage(ret), **{'at_sender': True})
