"""Transfer service - market operations."""

import sys
import os
from dataclasses import dataclass
from typing import List

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)


class TransferError(Exception):
    pass


@dataclass
class TransferItem:
    card_id: int
    seller_qq: int
    player_name: str
    position: str
    overall: int
    star: int
    seller_name: str
    cost: int


class TransferService:
    def __init__(self, db):
        self.db = db

    def list_market(self, page: int = 1, page_size: int = 20) -> dict:
        rows = self.db.query_all(
            "SELECT t.Card, t.Cost, t.User, c.Player, c.Star, c.Style, p.Name, p.Position, p.Overall, u.Name "
            "FROM transfer t "
            "JOIN cards c ON t.Card = c.ID "
            "JOIN players p ON c.Player = p.ID "
            "JOIN users u ON t.User = u.QQ"
        )
        total = len(rows)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size

        from server.services._formations import STARS
        items = []
        for r in rows[start:start + page_size]:
            star_bonus = STARS.get(r[4], {}).get("ability", 0)
            items.append(TransferItem(
                card_id=r[0], seller_qq=r[2], cost=r[1], player_name=r[6], position=r[7],
                overall=r[8] + star_bonus, star=r[4], seller_name=r[9] or "",
            ))

        return {"items": [i.__dict__ for i in items], "total": total, "page": page, "total_pages": total_pages}

    def list_card(self, qq: int, card_id: int, price: int) -> dict:
        row = self.db.query_one("SELECT ID, User, Status, Locked FROM cards WHERE ID = ?", (card_id,))
        if row is None:
            raise TransferError("Card not found")
        if row[1] != qq:
            raise TransferError("Not your card")
        if row[2] != 0:
            raise TransferError("Card in use")
        if row[3]:
            raise TransferError("Card locked")
        if price <= 0:
            price_row = self.db.query_one(
                "SELECT c.Star, c.Breach, p.Overall FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
                (card_id,)
            )
            if price_row:
                from server.services._formations import STARS
                ovr = price_row[2]
                x = ovr - 74 if ovr >= 80 else 6
                base = int(0.0131*x**5 - 0.6118*x**4 + 11.189*x**3 - 55.238*x**2 + 123.16*x - 29.137)
                star_count = STARS.get(price_row[0], {}).get("count", 1)
                price = base * star_count + base * (price_row[1] or 0)
            else:
                price = 1000
        self.db.execute("INSERT INTO transfer (User, Card, Cost) VALUES (?, ?, ?)", (qq, card_id, price))
        self.db.execute("UPDATE cards SET Status = 1 WHERE ID = ?", (card_id,))
        return {"ok": True, "price": price}

    def buy_card(self, qq: int, card_id: int) -> dict:
        row = self.db.query_one("SELECT User, Card, Cost FROM transfer WHERE Card = ?", (card_id,))
        if row is None:
            raise TransferError("Card not on market")
        seller_qq, _, cost = row
        if seller_qq == qq:
            self.db.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
            self.db.execute("UPDATE cards SET Status = 0 WHERE ID = ?", (card_id,))
            return {"cancelled": True}
        buyer_money = self.db.query_one("SELECT Money FROM users WHERE QQ = ?", (qq,))
        if buyer_money[0] < cost:
            raise TransferError("Insufficient funds")
        self.db.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        self.db.execute("UPDATE cards SET Status = 0, User = ? WHERE ID = ?", (qq, card_id))
        self.db.execute("UPDATE users SET Money = Money - ? WHERE QQ = ?", (cost, qq))
        self.db.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (cost, seller_qq))
        return {"ok": True, "cost": cost}

    def cancel_listing(self, qq: int, card_id: int) -> dict:
        row = self.db.query_one("SELECT User FROM transfer WHERE Card = ?", (card_id,))
        if row is None:
            raise TransferError("Card not on market")
        if row[0] != qq:
            raise TransferError("Not your listing")
        self.db.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        self.db.execute("UPDATE cards SET Status = 0 WHERE ID = ?", (card_id,))
        return {"ok": True}
