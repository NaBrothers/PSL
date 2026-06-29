from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.database import *
from model.player import *
from model.bag import *
from model.user import *
from model.transfer import *
from model.card import *
from kernel.account import *
from utils.image import toImage
from model.offline import *
import math
import json
from datetime import datetime, timezone

error_text = '''转会：查看当前转会市场
转会 页码：跳转到指定页
转会 购买 ID：购买指定球员卡
转会 出售 ID 价格：以指定价格出售球员卡
求购：查看求购大厅
求购 发布 球员名 最高价：发布求购单
求购 取消 ID：取消求购单
'''

transfer = on_startswith(msg="转会", rule=to_me(), priority=1)
bid_cmd = on_startswith(msg="求购", rule=to_me(), priority=1)


def _get_fee_percent():
    cursor = g_database.cursor()
    cursor.execute('SELECT Value FROM "global" WHERE Name = ?', ("config:transfer.fee_percent",))
    row = cursor.fetchone()
    cursor.close()
    if row:
        return json.loads(row[0])
    return 5


def _record_trade(card_id, player_id, star, seller_qq, buyer_qq, price, fee, source):
    now = datetime.now(timezone.utc).isoformat()
    cursor = g_database.cursor()
    cursor.execute(
        "INSERT INTO trade_history (CardID, PlayerID, Star, SellerQQ, BuyerQQ, Price, Fee, Source, CreatedAt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (card_id, player_id, star, seller_qq, buyer_qq, price, fee, source, now)
    )
    cursor.close()


def _try_match_listing(seller_qq, card_id, price):
    """Try to match a listing against active bid orders."""
    cursor = g_database.cursor()
    cursor.execute(
        "SELECT c.Star, c.Style, c.Player, p.Name, p.Position "
        "FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?", (card_id,)
    )
    card_row = cursor.fetchone()
    if not card_row:
        cursor.close()
        return None

    star, card_style, player_id, p_name, p_position = card_row
    first_pos = (p_position or "").split(",")[0].strip()

    from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER
    pos_groups = {"FWD": FORWARD, "MID": MIDFIELD, "DEF": GUARD, "GK": GOALKEEPER}

    cursor.execute(
        "SELECT ID, BuyerQQ, PlayerName, MinStar, Position, Style, MaxPrice "
        "FROM bid_orders WHERE Status = 0 AND MaxPrice >= ? "
        "ORDER BY MaxPrice DESC, CreatedAt ASC", (price,)
    )
    bids = cursor.fetchall()

    for bid in bids:
        bid_id, buyer_qq, bid_player, bid_min_star, bid_pos, bid_style, bid_max_price = bid
        if buyer_qq == seller_qq:
            continue
        if bid_player and bid_player.lower() != p_name.lower():
            continue
        if bid_min_star and star < bid_min_star:
            continue
        if bid_pos:
            allowed = pos_groups.get(bid_pos, [])
            if allowed and first_pos not in allowed:
                continue
        if bid_style and card_style != bid_style:
            continue

        cursor.execute("SELECT Money FROM users WHERE QQ = ?", (buyer_qq,))
        buyer_money = cursor.fetchone()
        if not buyer_money or buyer_money[0] < price:
            continue

        # Match! Execute trade
        fee_percent = _get_fee_percent()
        fee = int(price * fee_percent / 100)
        seller_income = price - fee

        cursor.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        cursor.execute("UPDATE cards SET Status = 0, User = ? WHERE ID = ?", (buyer_qq, card_id))
        cursor.execute("UPDATE users SET Money = Money - ? WHERE QQ = ?", (price, buyer_qq))
        cursor.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (seller_income, seller_qq))

        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE bid_orders SET Status = 1, MatchedAt = ?, MatchedCardID = ? WHERE ID = ?",
            (now, card_id, bid_id)
        )
        cursor.close()

        _record_trade(card_id, player_id, star, seller_qq, buyer_qq, price, fee, "bid_match")

        c2 = g_database.cursor()
        c2.execute("SELECT Name FROM users WHERE QQ = ?", (buyer_qq,))
        buyer_name_row = c2.fetchone()
        c2.close()
        buyer_name = buyer_name_row[0] if buyer_name_row else "某人"
        return {"buyer_name": buyer_name, "price": price, "fee": fee, "card_name": p_name}

    cursor.close()
    return None


@transfer.handle()
async def transfer_handler(bot: Bot, event: Event):
    user = await check_account(transfer, event)
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
        await transfer.finish("找不到该球员！", **{'at_sender': True})
        return
    card = Card.getCardByID(id)
    if card.status != 0:
        await transfer.finish("出售球员失败！状态：" + Const.STATUS[card.status], **{'at_sender': True})
        return
    if card.locked:
        await transfer.finish("出售球员失败！状态：已锁定", **{'at_sender': True})

    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("INSERT INTO transfer (User, Card, Cost, CreatedAt) VALUES (?, ?, ?, ?)",
                   (user.qq, int(id), int(cost), now))
    cursor.execute("UPDATE cards SET Status = 1 WHERE ID = ?", (int(id),))
    cursor.close()

    # Try matching against bid orders
    match = _try_match_listing(user.qq, int(id), int(cost))
    if match:
        fee_msg = f"（税${match['fee']}）" if match['fee'] > 0 else ""
        await transfer.finish(
            f"出售成功！已自动撮合：{match['buyer_name']} 以 ${match['price']} 购买{fee_msg}",
            **{'at_sender': True}
        )
    else:
        await transfer.finish("出售成功！", **{'at_sender': True})


async def buy_card(user, id):
    if not id.isdecimal():
        await transfer.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
        return

    cursor = g_database.cursor()
    count = cursor.execute("select * from transfer where card = " + id)
    if count == 0:
        await transfer.finish("找不到该球员！", **{'at_sender': True})
        return
    trans = Transfer(cursor.fetchone())
    if trans.user.qq == user.qq:
        cursor.execute("delete from transfer where card = " + id)
        cursor.execute("update cards set status = 0 where id = " + id)
        cursor.close()
        await transfer.finish("球员已回收", **{'at_sender': True})
        return
    if user.money < trans.cost:
        await transfer.finish(toImage("余额不足\n剩余球币：" + str(user.money)), **{"at_sender": True})
        return

    fee_percent = _get_fee_percent()
    fee = int(trans.cost * fee_percent / 100)
    seller_income = trans.cost - fee

    cursor.execute("delete from transfer where card = " + id)
    cursor.execute("update cards set status = 0, user = " + str(user.qq) + " where id = " + id)
    trans.card.status = 0
    cursor.close()
    user.spend(trans.cost)
    trans.user.earn(seller_income)

    # Record trade
    c3 = g_database.cursor()
    c3.execute("SELECT c.Player, c.Star FROM cards c WHERE c.ID = ?", (int(id),))
    card_info = c3.fetchone()
    c3.close()
    if card_info:
        _record_trade(int(id), card_info[0], card_info[1], trans.user.qq, user.qq, trans.cost, fee, "market")

    fee_msg = f"\n交易税：${fee}" if fee > 0 else ""
    ret = f"剩余球币：{user.money}{fee_msg}"

    msg = str(user.name) + "购买了你的球员\n" + trans.card.format() + "\n价格" + str(trans.cost) + "球币"
    if fee > 0:
        msg += f"\n交易税${fee}，实收${seller_income}球币"
    Offline.send(trans.user, toImage(msg, True))

    await transfer.finish("购买成功！\n" + toImage(ret), **{'at_sender': True})


@bid_cmd.handle()
async def bid_handler(bot: Bot, event: Event):
    user = await check_account(bid_cmd, event)
    args = str(event.message).split(" ")

    if len(args) == 1:
        await show_bid_list()
    elif len(args) >= 2:
        if args[1] == "发布" and len(args) == 4:
            await create_bid(user, args[2], args[3])
        elif args[1] == "取消" and len(args) == 3:
            await cancel_bid(user, args[2])
        else:
            await bid_cmd.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})
    else:
        await bid_cmd.finish("格式错误！\n" + toImage(error_text), **{'at_sender': True})


async def show_bid_list():
    cursor = g_database.cursor()
    rows = cursor.execute(
        "SELECT b.ID, b.BuyerQQ, b.PlayerName, b.MinStar, b.Position, b.Style, b.MaxPrice, u.Name "
        "FROM bid_orders b JOIN users u ON b.BuyerQQ = u.QQ WHERE b.Status = 0 "
        "ORDER BY b.MaxPrice DESC, b.CreatedAt ASC LIMIT 20"
    ).fetchall()
    cursor.close()

    if not rows:
        await bid_cmd.finish("求购大厅：暂无求购单\n" + toImage(error_text), **{'at_sender': True})
        return

    ret = ""
    for r in rows:
        bid_id, buyer_qq, player_name, min_star, position, style, max_price, buyer_name = r
        conditions = []
        if player_name:
            conditions.append(player_name)
        if min_star and min_star > 1:
            conditions.append(f"≥{min_star}★")
        if position:
            pos_map = {"FWD": "前锋", "MID": "中场", "DEF": "后卫", "GK": "门将"}
            conditions.append(pos_map.get(position, position))
        if not conditions:
            conditions.append("不限")
        ret += f"[{bid_id}] {buyer_name} 求购：{'·'.join(conditions)} 出价${max_price}\n"

    ret += error_text
    await bid_cmd.finish("求购大厅：\n" + toImage(ret), **{'at_sender': True})


async def create_bid(user, player_name, max_price_str):
    if not max_price_str.isdecimal():
        await bid_cmd.finish("价格格式错误！", **{'at_sender': True})
        return
    max_price = int(max_price_str)
    if max_price <= 0:
        await bid_cmd.finish("价格必须大于0！", **{'at_sender': True})
        return

    now = datetime.now(timezone.utc).isoformat()
    cursor = g_database.cursor()
    cursor.execute(
        "INSERT INTO bid_orders (BuyerQQ, PlayerName, MinStar, Position, Style, MaxPrice, Status, CreatedAt) "
        "VALUES (?, ?, 1, NULL, NULL, ?, 0, ?)",
        (user.qq, player_name if player_name != "不限" else None, max_price, now)
    )

    # Try matching against market
    cursor.execute("SELECT last_insert_rowid()")
    bid_id = cursor.fetchone()[0]
    cursor.close()

    # Simple match attempt against market
    from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER
    cursor2 = g_database.cursor()
    cursor2.execute(
        "SELECT t.Card, t.Cost, t.User, c.Star, c.Style, p.Name, p.Position, c.Player "
        "FROM transfer t JOIN cards c ON t.Card = c.ID JOIN players p ON c.Player = p.ID "
        "WHERE t.Cost <= ? ORDER BY t.Cost ASC, t.CreatedAt ASC", (max_price,)
    )
    listings = cursor2.fetchall()

    matched = False
    for row in listings:
        card_id, cost, seller_qq, star, card_style, p_name, p_position, player_id = row
        if seller_qq == user.qq:
            continue
        if player_name and player_name != "不限" and player_name.lower() != p_name.lower():
            continue

        # Check buyer balance
        cursor2.execute("SELECT Money FROM users WHERE QQ = ?", (user.qq,))
        buyer_money = cursor2.fetchone()
        if not buyer_money or buyer_money[0] < cost:
            break

        # Match!
        fee_percent = _get_fee_percent()
        fee = int(cost * fee_percent / 100)
        seller_income = cost - fee

        cursor2.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        cursor2.execute("UPDATE cards SET Status = 0, User = ? WHERE ID = ?", (user.qq, card_id))
        cursor2.execute("UPDATE users SET Money = Money - ? WHERE QQ = ?", (cost, user.qq))
        cursor2.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (seller_income, seller_qq))

        now2 = datetime.now(timezone.utc).isoformat()
        cursor2.execute(
            "UPDATE bid_orders SET Status = 1, MatchedAt = ?, MatchedCardID = ? WHERE ID = ?",
            (now2, card_id, bid_id)
        )
        cursor2.close()

        _record_trade(card_id, player_id, star, seller_qq, user.qq, cost, fee, "bid_match")

        fee_msg = f"（税${fee}）" if fee > 0 else ""
        await bid_cmd.finish(f"求购已自动成交！{p_name} ★{star} · ${cost}{fee_msg}", **{'at_sender': True})
        matched = True
        break

    if not matched:
        cursor2.close()
        await bid_cmd.finish(f"求购单已发布：{player_name} 最高${max_price}", **{'at_sender': True})


async def cancel_bid(user, bid_id_str):
    if not bid_id_str.isdecimal():
        await bid_cmd.finish("ID格式错误！", **{'at_sender': True})
        return

    bid_id = int(bid_id_str)
    cursor = g_database.cursor()
    cursor.execute("SELECT BuyerQQ, Status FROM bid_orders WHERE ID = ?", (bid_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        await bid_cmd.finish("求购单不存在！", **{'at_sender': True})
        return
    if row[0] != user.qq:
        cursor.close()
        await bid_cmd.finish("不是你的求购单！", **{'at_sender': True})
        return
    if row[1] != 0:
        cursor.close()
        await bid_cmd.finish("求购单已完成或已取消！", **{'at_sender': True})
        return

    cursor.execute("UPDATE bid_orders SET Status = 2 WHERE ID = ?", (bid_id,))
    cursor.close()
    await bid_cmd.finish("已取消求购单", **{'at_sender': True})
