from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.player import *
from game.model.bag import *
from game.model.user import *
from game.model.transfer import *
from game.model.card import *
from game.kernel.account import *
from game.utils.image import toImage
from game.model.offline import *
import math

error_text = '''转会：查看当前转会市场
转会 页码：跳转到指定页
转会 购买 ID：购买指定球员卡
转会 出售 ID 价格：以指定价格出售球员卡
'''

transfer = on_startswith(msg="转会", rule=to_me(), priority=1)

@transfer.handle()
async def transfer_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(transfer,event)
    args = str(event.message).split(" ")
    if len(args) == 1:
      await show_transfer_window(1)
    if len(args) == 2:
      if (args[1].isdecimal()):
        await show_transfer_window(args[1])
    elif len(args) == 4:
      if (args[1] == "出售"):
        await sell_card(user, args[2], args[3])
    elif len(args) == 3:
      if (args[1] == "购买"):
        await buy_card(user, args[2])
      
    await transfer.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})


async def show_transfer_window(page):
    ret = ""
    cursor = g_database.cursor()
    count = cursor.execute("select * from transfer;")
    if count == 0:
      ret += "无\n" + error_text
      await transfer.finish("转会市场:" + toImage(ret), **{'at_sender': True})
      return

    items = [Transfer(cursor.fetchone()) for i in range(count)]
    cursor.close()    

    total_page = math.ceil(count / 20)
    page = int(page)
    if page > total_page or page <= 0:
        await transfer.finish("页码错误", **{"at_sender": True})
        return
    
    for i in range(20):
      index = (page - 1) * 20 + i
      if index >= count:
          break
      item = items[index]
      ret += item.format()
      ret += "\n"
      
    ret += "第" + str(page) + "页 共" + str(total_page) + "页\n"
    ret += error_text
    await transfer.finish("转会市场:" + toImage(ret), **{'at_sender': True})

async def sell_card(user, id, cost):
    if not id.isdecimal() or not cost.isdecimal():
      await transfer.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
      return

    cursor = g_database.cursor()
    count = cursor.execute("select * from cards where id = " + id + " and user = " + str(user.qq))
    if count == 0:
      await transfer.finish("找不到该球员！" ,**{'at_sender': True})
      return
    card = Card.getCardByID(id)
    if card.status != 0:
      await transfer.finish("出售球员失败！状态：" + Const.STATUS[card.status], **{'at_sender': True})
      return
    if card.locked:
      await transfer.finish("出售球员失败！状态：已锁定", **{'at_sender': True})
    count = cursor.execute("insert into transfer (user, card, cost) values ( " + str(user.qq) + ", " + str(card.id) + ", " + str(cost) + ");")
    count = cursor.execute("update cards set status = 1 where id = " + str(card.id))
    cursor.close()
    await transfer.finish("出售成功！", **{'at_sender': True})

async def buy_card(user, id):
    if not id.isdecimal():
      await transfer.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
      return

    cursor = g_database.cursor()
    count = cursor.execute("select * from transfer where card = " + id)
    if count == 0:
      await transfer.finish("找不到该球员！" ,**{'at_sender': True})
      return
    trans = Transfer(cursor.fetchone())
    if trans.user.qq == user.qq:
      count = cursor.execute("delete from transfer where card = " + id)
      count = cursor.execute("update cards set status = 0 where id = " + id)
      await transfer.finish("球员已回收" ,**{'at_sender': True})
      return
    if user.money < trans.cost:
      await transfer.finish(toImage("余额不足\n剩余球币：" + str(user.money)), **{"at_sender": True})
      return
    count = cursor.execute("delete from transfer where card = " + id)
    count = cursor.execute("update cards set status = 0, user = " + str(user.qq) + " where id = " + id)
    trans.card.status = 0
    cursor.close()
    user.spend(trans.cost)
    trans.user.earn(trans.cost)
    ret = "剩余球币：" + str(user.money)

    msg = str(user.name) + "购买了你的球员\n" + trans.card.format() + "\n价格" + str(trans.cost) + "球币"
    Offline.send(trans.user, toImage(msg))

    await transfer.finish("购买成功！\n" + toImage(ret), **{'at_sender': True})