"""Transfer service - market operations."""

from datetime import datetime, timezone
from typing import List

from psl_core.constants import STARS, FORWARD, MIDFIELD, GUARD, GOALKEEPER, STYLE, GK_STYLE
from psl_core.card import compute_overall, compute_price, compute_abilities, get_style_name


class TransferError(Exception):
    pass


class TransferService:
    def __init__(self, db):
        self.db = db

    def _get_fee_percent(self) -> float:
        from server.services.game_config import GameConfigService
        cfg = GameConfigService(self.db)
        return cfg.get("transfer.fee_percent")

    def _record_trade(self, card_id: int, player_id: int, star: int,
                      seller_qq: int, buyer_qq: int, price: int, fee: int, source: str):
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO trade_history (CardID, PlayerID, Star, SellerQQ, BuyerQQ, Price, Fee, Source, CreatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (card_id, player_id, star, seller_qq, buyer_qq, price, fee, source, now)
        )

    def get_reference_price(self, player_id: int, star: int) -> dict:
        from server.services.game_config import GameConfigService
        cfg = GameConfigService(self.db)
        n = int(cfg.get("transfer.reference_count"))
        rows = self.db.query_all(
            "SELECT Price FROM trade_history WHERE PlayerID = ? AND Star = ? ORDER BY CreatedAt DESC LIMIT ?",
            (player_id, star, n)
        )
        if not rows:
            return {"has_data": False, "price": 0, "count": 0}
        prices = [r[0] for r in rows]
        avg = sum(prices) // len(prices)
        return {"has_data": True, "price": avg, "count": len(prices)}

    def list_market_players(self, query: str = "", position: str = "", min_star: int = 0, style: str = "") -> dict:
        """Group market listings by player for the first-level view."""
        where_clauses = []
        params = []
        if min_star > 0:
            where_clauses.append("c.Star >= ?")
            params.append(min_star)
        if style:
            where_clauses.append("c.Style = ?")
            params.append(style)
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        rows = self.db.query_all(
            "SELECT c.Player, p.Name, p.Position, p.Overall, "
            "COUNT(*) as listing_count, MIN(t.Cost) as min_price, "
            "MAX(c.Star) as max_star "
            "FROM transfer t "
            "JOIN cards c ON t.Card = c.ID "
            "JOIN players p ON c.Player = p.ID"
            + where_sql +
            " GROUP BY c.Player "
            "ORDER BY p.Overall DESC",
            tuple(params)
        )
        items = []
        for r in rows:
            p_name = r[1] or ""
            p_pos = (r[2] or "").split(",")[0].strip()
            if query and query.lower() not in p_name.lower():
                continue
            if position:
                from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER
                pos_groups = {"FWD": FORWARD, "MID": MIDFIELD, "DEF": GUARD, "GK": GOALKEEPER}
                allowed = pos_groups.get(position, [])
                if allowed and p_pos not in allowed:
                    continue
            items.append({
                "player_id": r[0],
                "name": p_name,
                "position": p_pos,
                "overall": r[3],
                "listing_count": r[4],
                "min_price": r[5],
                "max_star": r[6],
            })
        return {"players": items}

    def list_market(self, page: int = 1, page_size: int = 20, query: str = "",
                    position: str = "", min_star: int = 0, style: str = "",
                    sort_by: str = "overall", player_id: int = 0, star: int = 0) -> dict:
        rows = self.db.query_all(
            "SELECT t.Card, t.Cost, t.User, c.Player, c.Star, c.Style, c.Breach, "
            "p.Name, p.Position, p.Overall, u.Name, p.Height, "
            "p.Heading_Accuracy, p.Jumping, p.Strength, p.Long_Shots, p.Shot_Power, "
            "p.Finishing, p.Long_Passing, p.Short_Passing, p.Dribbling, p.Ball_Control, "
            "p.Balance, p.Sliding_Tackle, p.Standing_Tackle, p.Defensive_Awareness, "
            "p.Aggression, p.Interceptions, p.Sprint_Speed, p.Acceleration, "
            "p.Composure, p.GK_Handling, p.GK_Diving, p.GK_Positioning, p.GK_Reflexes, p.Reactions "
            "FROM transfer t "
            "JOIN cards c ON t.Card = c.ID "
            "JOIN players p ON c.Player = p.ID "
            "JOIN users u ON t.User = u.QQ"
        )

        items = []
        for r in rows:
            if player_id and r[3] != player_id:
                continue
            if star and r[4] != star:
                continue
            first_pos = (r[8] or "").split(",")[0].strip()
            card_star = r[4]
            style_key = r[5]
            overall = compute_overall(r[9], card_star)
            height_val = int(r[11]) if r[11] and str(r[11]).isdigit() else 180

            abilities = compute_abilities(
                star=card_star, style=style_key, position=first_pos, height=height_val,
                heading_accuracy=r[12] or 0, jumping=r[13] or 0, strength=r[14] or 0,
                long_shots=r[15] or 0, shot_power=r[16] or 0, finishing=r[17] or 0,
                long_passing=r[18] or 0, short_passing=r[19] or 0, dribbling=r[20] or 0,
                ball_control=r[21] or 0, balance=r[22] or 0, sliding_tackle=r[23] or 0,
                standing_tackle=r[24] or 0, defensive_awareness=r[25] or 0,
                aggression=r[26] or 0, interceptions=r[27] or 0, sprint_speed=r[28] or 0,
                acceleration=r[29] or 0, composure=r[30] or 0, gk_handling=r[31] or 0,
                gk_diving=r[32] or 0, gk_positioning=r[33] or 0, gk_reflexes=r[34] or 0,
                reactions=r[35] or 0,
            )

            items.append({
                "card_id": r[0], "cost": r[1], "seller_qq": r[2], "seller_name": r[10] or "",
                "player_name": r[7], "position": first_pos, "overall": overall,
                "star": card_star, "style": style_key, "style_name": get_style_name(style_key, first_pos),
                "breach": r[6] or 0, "abilities": abilities,
            })

        if query:
            q = query.lower()
            items = [i for i in items if q in i["player_name"].lower()]
        if position:
            pos_groups = {"FWD": FORWARD, "MID": MIDFIELD, "DEF": GUARD, "GK": GOALKEEPER}
            allowed = pos_groups.get(position, [])
            if allowed:
                items = [i for i in items if i["position"] in allowed]
        if min_star > 0:
            items = [i for i in items if i["star"] >= min_star]
        if style:
            items = [i for i in items if i["style"] == style]

        sort_key = {
            "overall": lambda i: -i["overall"],
            "price_asc": lambda i: i["cost"],
            "price_desc": lambda i: -i["cost"],
            "star": lambda i: -i["star"],
        }
        if sort_by in sort_key:
            items.sort(key=sort_key[sort_by])
        elif sort_by in ("Speed", "Finishing", "Dribbling", "Defence", "Tackling",
                         "Short_Passing", "Long_Passing", "Heading", "Long_Shot"):
            items.sort(key=lambda i: -i["abilities"].get(sort_by, 0))
        else:
            items.sort(key=lambda i: -i["overall"])

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        page_items = items[start:start + page_size]

        for item in page_items:
            del item["abilities"]

        return {"items": page_items, "total": total, "page": page, "total_pages": total_pages}

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
                price = compute_price(price_row[2], price_row[0], price_row[1] or 0)
            else:
                price = 1000

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT INTO transfer (User, Card, Cost, CreatedAt) VALUES (?, ?, ?, ?)",
                        (qq, card_id, price, now))
        self.db.execute("UPDATE cards SET Status = 1 WHERE ID = ?", (card_id,))

        # Try to match against active bid orders
        match_result = self._match_listing_to_bids(qq, card_id, price)
        if match_result:
            return {"ok": True, "price": price, "matched": True, "match_detail": match_result}
        return {"ok": True, "price": price, "matched": False}

    def _match_listing_to_bids(self, seller_qq: int, card_id: int, price: int) -> dict:
        """Try to match a newly listed card against active bid orders."""
        from server.services.bid import BidService
        bid_svc = BidService(self.db)
        return bid_svc.match_listing(seller_qq, card_id, price)

    def batch_list(self, qq: int, cards: List[dict]) -> dict:
        results = []
        for item in cards:
            card_id = item.get("card_id", 0)
            price = item.get("price", 0)
            try:
                res = self.list_card(qq, card_id, price)
                results.append({"card_id": card_id, "ok": True, "price": res["price"],
                                "matched": res.get("matched", False)})
            except TransferError as e:
                results.append({"card_id": card_id, "ok": False, "error": str(e)})
        return {"results": results}

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

        fee_percent = self._get_fee_percent()
        fee = int(cost * fee_percent / 100)
        seller_income = cost - fee

        self.db.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        self.db.execute("UPDATE cards SET Status = 0, User = ? WHERE ID = ?", (qq, card_id))
        self.db.execute("UPDATE users SET Money = Money - ? WHERE QQ = ?", (cost, qq))
        self.db.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (seller_income, seller_qq))

        # Record trade history
        card_info = self.db.query_one(
            "SELECT c.Player, c.Star, p.Name FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
            (card_id,)
        )
        player_id = card_info[0] if card_info else 0
        star = card_info[1] if card_info else 1
        card_name = card_info[2] if card_info else "球员"
        self._record_trade(card_id, player_id, star, seller_qq, qq, cost, fee, "market")

        # Notify seller
        from server.services.inbox import InboxService
        inbox = InboxService(self.db)
        buyer_row = self.db.query_one("SELECT Name FROM users WHERE QQ = ?", (qq,))
        buyer_name = buyer_row[0] if buyer_row else "某人"
        if fee > 0:
            inbox.send(seller_qq, "transfer_sold", f"{card_name} 已售出",
                f"你的 {card_name} 被 {buyer_name} 以 ${cost} 购买（税 ${fee}，实收 ${seller_income}）",
                {"card_id": card_id, "cost": cost, "fee": fee})
        else:
            inbox.send(seller_qq, "transfer_sold", f"{card_name} 已售出",
                f"你的 {card_name} 被 {buyer_name} 以 ${cost} 购买",
                {"card_id": card_id, "cost": cost})

        return {"ok": True, "cost": cost, "fee": fee}

    def batch_buy(self, qq: int, card_ids: List[int]) -> dict:
        results = []
        for card_id in card_ids:
            try:
                res = self.buy_card(qq, card_id)
                results.append({"card_id": card_id, **res})
            except TransferError as e:
                results.append({"card_id": card_id, "ok": False, "error": str(e)})
        return {"results": results}

    def cancel_listing(self, qq: int, card_id: int) -> dict:
        row = self.db.query_one("SELECT User FROM transfer WHERE Card = ?", (card_id,))
        if row is None:
            raise TransferError("Card not on market")
        if row[0] != qq:
            raise TransferError("Not your listing")
        self.db.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        self.db.execute("UPDATE cards SET Status = 0 WHERE ID = ?", (card_id,))
        return {"ok": True}
