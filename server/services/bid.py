"""Bid service - buy orders and matching logic."""

from datetime import datetime, timezone
from typing import List, Optional

from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER


class BidError(Exception):
    pass


POS_GROUPS = {"FWD": FORWARD, "MID": MIDFIELD, "DEF": GUARD, "GK": GOALKEEPER}


class BidService:
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

    def _notify(self, user_qq: int, msg_type: str, title: str, content: str, data: dict = None):
        from server.services.inbox import InboxService
        inbox = InboxService(self.db)
        inbox.send(user_qq, msg_type, title, content, data)

    def _card_matches_bid(self, card_id: int, bid: dict) -> bool:
        """Check if a card satisfies a bid order's conditions."""
        row = self.db.query_one(
            "SELECT c.Star, c.Style, p.Name, p.Position FROM cards c "
            "JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
            (card_id,)
        )
        if not row:
            return False
        star, style, player_name, position = row
        first_pos = (position or "").split(",")[0].strip()

        if bid["player_name"] and bid["player_name"].lower() != player_name.lower():
            return False
        if bid["min_star"] and star < bid["min_star"]:
            return False
        if bid["position"]:
            allowed = POS_GROUPS.get(bid["position"], [])
            if allowed and first_pos not in allowed:
                return False
        if bid["style"] and style != bid["style"]:
            return False
        return True

    def create_bid(self, buyer_qq: int, player_name: Optional[str], min_star: int,
                   position: Optional[str], style: Optional[str], max_price: int) -> dict:
        if max_price <= 0:
            raise BidError("Price must be positive")

        # Validate position
        if position and position not in POS_GROUPS:
            raise BidError(f"Invalid position: {position}")

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO bid_orders (BuyerQQ, PlayerName, MinStar, Position, Style, MaxPrice, Status, CreatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (buyer_qq, player_name or None, min_star or 1, position or None, style or None, max_price, now)
        )
        bid_id = self.db.query_one("SELECT last_insert_rowid()")[0]

        # Try to match against current market listings
        match_result = self._match_bid_to_market(bid_id, buyer_qq, player_name, min_star, position, style, max_price)
        if match_result:
            return {"ok": True, "bid_id": bid_id, "matched": True, "match_detail": match_result}
        return {"ok": True, "bid_id": bid_id, "matched": False}

    def _match_bid_to_market(self, bid_id: int, buyer_qq: int, player_name: Optional[str],
                             min_star: int, position: Optional[str], style: Optional[str],
                             max_price: int) -> Optional[dict]:
        """Try to match a new bid against existing market listings. Lowest price first."""
        rows = self.db.query_all(
            "SELECT t.Card, t.Cost, t.User, c.Star, c.Style, p.Name, p.Position, c.Player, t.CreatedAt "
            "FROM transfer t "
            "JOIN cards c ON t.Card = c.ID "
            "JOIN players p ON c.Player = p.ID "
            "WHERE t.Cost <= ? "
            "ORDER BY t.Cost ASC, t.CreatedAt ASC",
            (max_price,)
        )

        for r in rows:
            card_id, cost, seller_qq, star, card_style, p_name, p_position, player_id, _ = r
            if seller_qq == buyer_qq:
                continue
            first_pos = (p_position or "").split(",")[0].strip()

            if player_name and player_name.lower() != p_name.lower():
                continue
            if min_star and star < min_star:
                continue
            if position:
                allowed = POS_GROUPS.get(position, [])
                if allowed and first_pos not in allowed:
                    continue
            if style and card_style != style:
                continue

            # Check buyer balance
            buyer_money = self.db.query_one("SELECT Money FROM users WHERE QQ = ?", (buyer_qq,))
            if not buyer_money or buyer_money[0] < cost:
                return None  # Not enough money, keep bid active

            # Match found! Execute trade
            return self._execute_trade(bid_id, card_id, player_id, star, seller_qq, buyer_qq, cost, "bid_match")

        return None

    def match_listing(self, seller_qq: int, card_id: int, price: int) -> Optional[dict]:
        """Called when a card is listed. Try to match against active bid orders.
        Highest MaxPrice first, then earliest CreatedAt."""
        card_row = self.db.query_one(
            "SELECT c.Star, c.Style, c.Player, p.Name, p.Position "
            "FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
            (card_id,)
        )
        if not card_row:
            return None
        star, card_style, player_id, p_name, p_position = card_row
        first_pos = (p_position or "").split(",")[0].strip()

        bids = self.db.query_all(
            "SELECT ID, BuyerQQ, PlayerName, MinStar, Position, Style, MaxPrice "
            "FROM bid_orders WHERE Status = 0 AND MaxPrice >= ? "
            "ORDER BY MaxPrice DESC, CreatedAt ASC",
            (price,)
        )

        for bid in bids:
            bid_id, buyer_qq, bid_player, bid_min_star, bid_pos, bid_style, bid_max_price = bid
            if buyer_qq == seller_qq:
                continue

            if bid_player and bid_player.lower() != p_name.lower():
                continue
            if bid_min_star and star < bid_min_star:
                continue
            if bid_pos:
                allowed = POS_GROUPS.get(bid_pos, [])
                if allowed and first_pos not in allowed:
                    continue
            if bid_style and card_style != bid_style:
                continue

            # Check buyer balance
            buyer_money = self.db.query_one("SELECT Money FROM users WHERE QQ = ?", (buyer_qq,))
            if not buyer_money or buyer_money[0] < price:
                continue  # Skip this bid, try next

            # Match! Execute at seller's price
            return self._execute_trade(bid_id, card_id, player_id, star, seller_qq, buyer_qq, price, "bid_match")

        return None

    def _execute_trade(self, bid_id: int, card_id: int, player_id: int, star: int,
                       seller_qq: int, buyer_qq: int, price: int, source: str) -> dict:
        """Execute a matched trade between bid order and listing."""
        fee_percent = self._get_fee_percent()
        fee = int(price * fee_percent / 100)
        seller_income = price - fee

        # Remove from market
        self.db.execute("DELETE FROM transfer WHERE Card = ?", (card_id,))
        # Transfer card
        self.db.execute("UPDATE cards SET Status = 0, User = ? WHERE ID = ?", (buyer_qq, card_id))
        # Move money
        self.db.execute("UPDATE users SET Money = Money - ? WHERE QQ = ?", (price, buyer_qq))
        self.db.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (seller_income, seller_qq))

        # Update bid order
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE bid_orders SET Status = 1, MatchedAt = ?, MatchedCardID = ? WHERE ID = ?",
            (now, card_id, bid_id)
        )

        # Record trade
        self._record_trade(card_id, player_id, star, seller_qq, buyer_qq, price, fee, source)

        # Notify both parties
        card_row = self.db.query_one(
            "SELECT p.Name FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?", (card_id,))
        card_name = card_row[0] if card_row else "球员"
        buyer_row = self.db.query_one("SELECT Name FROM users WHERE QQ = ?", (buyer_qq,))
        buyer_name = buyer_row[0] if buyer_row else "某人"
        seller_row = self.db.query_one("SELECT Name FROM users WHERE QQ = ?", (seller_qq,))
        seller_name = seller_row[0] if seller_row else "某人"

        if fee > 0:
            self._notify(seller_qq, "transfer_sold", f"{card_name} 已售出（自动撮合）",
                f"你的 {card_name} 被 {buyer_name} 以 ${price} 购买（税 ${fee}，实收 ${seller_income}）",
                {"card_id": card_id, "cost": price, "fee": fee, "source": source})
        else:
            self._notify(seller_qq, "transfer_sold", f"{card_name} 已售出（自动撮合）",
                f"你的 {card_name} 被 {buyer_name} 以 ${price} 购买",
                {"card_id": card_id, "cost": price, "source": source})

        self._notify(buyer_qq, "bid_matched", f"求购成交：{card_name}",
            f"你的求购已成交：{card_name} ★{star}，成交价 ${price}，卖家 {seller_name}",
            {"card_id": card_id, "cost": price, "bid_id": bid_id})

        return {"card_id": card_id, "price": price, "fee": fee, "card_name": card_name}

    def supply_card(self, seller_qq: int, bid_id: int, card_id: int) -> dict:
        """A seller supplies a card to fulfill a bid order directly."""
        bid = self.db.query_one(
            "SELECT ID, BuyerQQ, PlayerName, MinStar, Position, Style, MaxPrice, Status "
            "FROM bid_orders WHERE ID = ?",
            (bid_id,)
        )
        if not bid:
            raise BidError("Bid order not found")
        if bid[7] != 0:
            raise BidError("Bid order already fulfilled or cancelled")
        buyer_qq = bid[1]
        max_price = bid[6]

        if buyer_qq == seller_qq:
            raise BidError("Cannot supply to your own bid")

        # Validate card ownership and status
        card_row = self.db.query_one(
            "SELECT c.ID, c.User, c.Status, c.Locked, c.Star, c.Style, c.Player, p.Name, p.Position "
            "FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
            (card_id,)
        )
        if not card_row:
            raise BidError("Card not found")
        if card_row[1] != seller_qq:
            raise BidError("Not your card")
        if card_row[2] != 0:
            raise BidError("Card in use or listed")
        if card_row[3]:
            raise BidError("Card locked")

        # Verify card matches bid conditions
        bid_dict = {
            "player_name": bid[2],
            "min_star": bid[3],
            "position": bid[4],
            "style": bid[5],
        }
        star = card_row[4]
        card_style = card_row[5]
        player_id = card_row[6]
        p_name = card_row[7]
        first_pos = (card_row[8] or "").split(",")[0].strip()

        if bid_dict["player_name"] and bid_dict["player_name"].lower() != p_name.lower():
            raise BidError("Card does not match bid: player name mismatch")
        if bid_dict["min_star"] and star < bid_dict["min_star"]:
            raise BidError("Card does not match bid: star too low")
        if bid_dict["position"]:
            allowed = POS_GROUPS.get(bid_dict["position"], [])
            if allowed and first_pos not in allowed:
                raise BidError("Card does not match bid: position mismatch")
        if bid_dict["style"] and card_style != bid_dict["style"]:
            raise BidError("Card does not match bid: style mismatch")

        # Check buyer balance
        buyer_money = self.db.query_one("SELECT Money FROM users WHERE QQ = ?", (buyer_qq,))
        if not buyer_money or buyer_money[0] < max_price:
            raise BidError("Buyer has insufficient funds")

        # Execute at bid's max_price
        fee_percent = self._get_fee_percent()
        fee = int(max_price * fee_percent / 100)
        seller_income = max_price - fee

        self.db.execute("UPDATE cards SET User = ? WHERE ID = ?", (buyer_qq, card_id))
        self.db.execute("UPDATE users SET Money = Money - ? WHERE QQ = ?", (max_price, buyer_qq))
        self.db.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (seller_income, seller_qq))

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE bid_orders SET Status = 1, MatchedAt = ?, MatchedCardID = ? WHERE ID = ?",
            (now, card_id, bid_id)
        )

        self._record_trade(card_id, player_id, star, seller_qq, buyer_qq, max_price, fee, "bid_supply")

        # Notifications
        card_name = p_name
        buyer_row = self.db.query_one("SELECT Name FROM users WHERE QQ = ?", (buyer_qq,))
        buyer_name = buyer_row[0] if buyer_row else "某人"
        seller_row = self.db.query_one("SELECT Name FROM users WHERE QQ = ?", (seller_qq,))
        seller_name = seller_row[0] if seller_row else "某人"

        self._notify(buyer_qq, "bid_matched", f"求购成交：{card_name}",
            f"你的求购已成交：{card_name} ★{star}，{seller_name} 以 ${max_price} 供货",
            {"card_id": card_id, "cost": max_price, "bid_id": bid_id})

        return {"ok": True, "price": max_price, "fee": fee, "card_name": card_name}

    def cancel_bid(self, buyer_qq: int, bid_id: int) -> dict:
        bid = self.db.query_one(
            "SELECT ID, BuyerQQ, Status FROM bid_orders WHERE ID = ?", (bid_id,)
        )
        if not bid:
            raise BidError("Bid order not found")
        if bid[1] != buyer_qq:
            raise BidError("Not your bid order")
        if bid[2] != 0:
            raise BidError("Bid order already fulfilled or cancelled")

        self.db.execute("UPDATE bid_orders SET Status = 2 WHERE ID = ?", (bid_id,))
        return {"ok": True}

    def list_bids(self, page: int = 1, page_size: int = 20, my_qq: int = 0) -> dict:
        """List active bid orders."""
        rows = self.db.query_all(
            "SELECT b.ID, b.BuyerQQ, b.PlayerName, b.MinStar, b.Position, b.Style, "
            "b.MaxPrice, b.CreatedAt, u.Name "
            "FROM bid_orders b JOIN users u ON b.BuyerQQ = u.QQ "
            "WHERE b.Status = 0 ORDER BY b.MaxPrice DESC, b.CreatedAt ASC"
        )

        items = []
        for r in rows:
            items.append({
                "bid_id": r[0],
                "buyer_qq": r[1],
                "player_name": r[2] or "",
                "min_star": r[3] or 1,
                "position": r[4] or "",
                "style": r[5] or "",
                "max_price": r[6],
                "created_at": r[7],
                "buyer_name": r[8] or "",
                "is_mine": r[1] == my_qq,
            })

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        page_items = items[start:start + page_size]

        return {"items": page_items, "total": total, "page": page, "total_pages": total_pages}

    def get_supply_candidates(self, seller_qq: int, bid_id: int, page: int = 1, page_size: int = 20) -> dict:
        """Get cards from seller's bag that satisfy the bid conditions."""
        bid = self.db.query_one(
            "SELECT PlayerName, MinStar, Position, Style FROM bid_orders WHERE ID = ? AND Status = 0",
            (bid_id,)
        )
        if not bid:
            raise BidError("Bid order not found or not active")

        player_name, min_star, position, style = bid

        # Query seller's available cards
        rows = self.db.query_all(
            "SELECT c.ID, c.Star, c.Style, c.Breach, p.Name, p.Position, p.Overall "
            "FROM cards c JOIN players p ON c.Player = p.ID "
            "WHERE c.User = ? AND c.Status = 0 AND c.Locked = 0",
            (seller_qq,)
        )

        candidates = []
        for r in rows:
            card_id, star, card_style, breach, p_name, p_pos, overall = r
            first_pos = (p_pos or "").split(",")[0].strip()

            if player_name and player_name.lower() != p_name.lower():
                continue
            if min_star and star < min_star:
                continue
            if position:
                allowed = POS_GROUPS.get(position, [])
                if allowed and first_pos not in allowed:
                    continue
            if style and card_style != style:
                continue

            from psl_core.card import compute_overall, get_style_name
            candidates.append({
                "card_id": card_id,
                "player_name": p_name,
                "position": first_pos,
                "star": star,
                "style": card_style,
                "style_name": get_style_name(card_style, first_pos),
                "overall": compute_overall(overall, star),
                "breach": breach,
            })

        candidates.sort(key=lambda x: -x["overall"])
        total = len(candidates)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size

        return {"items": candidates[start:start + page_size], "total": total, "page": page, "total_pages": total_pages}
