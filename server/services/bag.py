"""Bag service - card inventory operations."""

import json
from dataclasses import dataclass
from typing import List, Optional

from psl_core.constants import (
    FORWARD, MIDFIELD, GUARD, GOALKEEPER,
    ABILITIES, GK_ABILITIES,
)
from psl_core.card import (
    compute_abilities, compute_all_position_ratings, compute_overall,
    compute_price, get_style_name,
)


class BagError(Exception):
    pass


class CardNotFound(BagError):
    pass


class CardNotOwned(BagError):
    pass


class CardLocked(BagError):
    pass


@dataclass
class BagCardInfo:
    id: int
    player_id: int
    name: str
    position: str
    overall: int
    star: int
    style: str
    breach: int
    locked: bool
    status: int
    status_text: str
    real_overall: Optional[int] = None


@dataclass
class BagPage:
    cards: List[BagCardInfo]
    total: int
    page: int
    total_pages: int


@dataclass
class RecycleResult:
    recycled: List[str]
    failed: List[str]
    earned: int
    remaining_money: int


class BagService:
    def __init__(self, db):
        self.db = db

    def get_bag(self, qq: int, page: int = 1, query: str = "", page_size: int = 20,
                sort: str = "overall", position: str = "", color: str = "") -> BagPage:
        rows = self.db.query_all(
            "SELECT c.ID, c.Player, c.Star, c.Style, c.Status, c.Locked, c.Breach, "
            "p.Name, p.Position, p.Overall "
            "FROM cards c JOIN players p ON c.Player = p.ID "
            "WHERE c.User = ?",
            (qq,)
        )

        STATUS_TEXT = {0: "", 1: "转会中", 2: "首发"}

        cards = []
        for r in rows:
            ov = compute_overall(r[9], r[2])
            cards.append(BagCardInfo(
                id=r[0], player_id=r[1], name=r[7], position=r[8],
                overall=ov, real_overall=ov, star=r[2], style=r[3],
                breach=r[6], locked=bool(r[5]), status=r[4] or 0,
                status_text=STATUS_TEXT.get(r[4] or 0, ""),
            ))

        if query:
            cards = [c for c in cards if query.lower() in c.name.lower()]

        if position:
            pos_groups = {
                "GK": GOALKEEPER, "DEF": GUARD, "MID": MIDFIELD, "FWD": FORWARD
            }
            allowed = pos_groups.get(position, [])
            if allowed:
                cards = [c for c in cards if c.position in allowed]

        if color:
            color_ranges = {
                "white": (0, 82), "green": (82, 84), "blue": (84, 87),
                "purple": (87, 89), "orange": (89, 92), "red": (92, 94),
                "pink": (94, 200),
            }
            lo, hi = color_ranges.get(color, (0, 200))
            cards = [c for c in cards if lo <= c.overall < hi]

        if sort == "name":
            cards.sort(key=lambda c: (c.name, -c.overall, -c.star))
        elif sort == "star":
            cards.sort(key=lambda c: (-c.star, -c.overall, c.name))
        else:
            cards.sort(key=lambda c: (-c.overall, -c.star, c.name))

        total = len(cards)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        page_cards = cards[start:start + page_size]

        return BagPage(cards=page_cards, total=total, page=page, total_pages=total_pages)

    def get_card_detail(self, card_id: int, qq: int) -> dict:
        row = self.db.query_one(
            "SELECT c.ID, c.Player, c.Star, c.Style, c.Status, c.Locked, c.Breach, "
            "c.Appearance, c.Goal, c.Assist, c.Tackle, c.Save, "
            "c.Total_Appearance, c.Total_Goal, c.Total_Assist, c.Total_Tackle, c.Total_Save, "
            "c.Ext_Abilities, "
            "p.Name, p.Position, p.Overall, p.Age, p.Height, p.Weight, p.Nationality, "
            "p.Crossing, p.Finishing, p.Heading_Accuracy, p.Short_Passing, p.Volleys, "
            "p.Dribbling, p.Curve, p.FK_Accuracy, p.Long_Passing, p.Ball_Control, "
            "p.Acceleration, p.Sprint_Speed, p.Agility, p.Reactions, p.Balance, "
            "p.Shot_Power, p.Jumping, p.Stamina, p.Strength, p.Long_Shots, "
            "p.Aggression, p.Interceptions, p.Positioning, p.Vision, p.Penalties, "
            "p.Composure, p.Defensive_Awareness, p.Standing_Tackle, p.Sliding_Tackle, "
            "p.GK_Diving, p.GK_Handling, p.GK_Kicking, p.GK_Positioning, p.GK_Reflexes "
            "FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
            (card_id,)
        )
        if row is None:
            raise CardNotFound(f"Card {card_id} not found")

        star = row[2]
        style = row[3]
        ext = json.loads(row[17]) if row[17] else {}
        position = row[19]
        base_overall = row[20]
        height_str = row[22] or "180"
        height_val = int(height_str) if str(height_str).isdigit() else 180

        abilities = compute_abilities(
            star=star,
            style=style,
            position=position,
            height=height_val,
            heading_accuracy=row[27] or 0,
            jumping=row[41] or 0,
            strength=row[43] or 0,
            long_shots=row[44] or 0,
            shot_power=row[40] or 0,
            finishing=row[26] or 0,
            long_passing=row[33] or 0,
            short_passing=row[28] or 0,
            dribbling=row[30] or 0,
            ball_control=row[34] or 0,
            balance=row[39] or 0,
            sliding_tackle=row[53] or 0,
            standing_tackle=row[52] or 0,
            defensive_awareness=row[51] or 0,
            aggression=row[45] or 0,
            interceptions=row[46] or 0,
            sprint_speed=row[36] or 0,
            acceleration=row[35] or 0,
            composure=row[50] or 0,
            gk_handling=row[55] or 0,
            gk_diving=row[54] or 0,
            gk_positioning=row[57] or 0,
            gk_reflexes=row[58] or 0,
            reactions=row[38] or 0,
            ext_abilities=ext,
        )

        ABILITY_NAMES = {**ABILITIES, **GK_ABILITIES, "IQ": "球商"}

        position_ratings = compute_all_position_ratings(abilities)
        overall_with_star = compute_overall(base_overall, star)

        for item in position_ratings:
            item["diff"] = item["rating"] - overall_with_star

        price = compute_price(base_overall, star, row[6] or 0)

        return {
            "id": row[0], "player_id": row[1], "star": star, "style": style,
            "style_name": get_style_name(style, position),
            "status": row[4] or 0, "locked": bool(row[5]), "breach": row[6] or 0,
            "overall": overall_with_star,
            "name": row[18], "position": position, "age": row[21],
            "height": row[22], "weight": row[23], "nationality": row[24],
            "price": price,
            "abilities": {k: {"value": v, "name": ABILITY_NAMES.get(k, k), "ext": ext.get(k, 0)} for k, v in abilities.items()},
            "position_ratings": position_ratings[:3],
            "all_position_ratings": position_ratings,
            "season": {"appearance": row[7], "goal": row[8], "assist": row[9], "tackle": row[10], "save": row[11]},
            "career": {"appearance": row[12], "goal": row[13], "assist": row[14], "tackle": row[15], "save": row[16]},
            "ext_abilities": ext,
        }

    def lock_card(self, card_id: int, qq: int) -> bool:
        row = self.db.query_one("SELECT Locked, User FROM cards WHERE ID = ?", (card_id,))
        if row is None:
            raise CardNotFound(f"Card {card_id} not found")
        if row[1] != qq:
            raise CardNotOwned("Not your card")
        new_locked = 0 if row[0] else 1
        self.db.execute("UPDATE cards SET Locked = ? WHERE ID = ?", (new_locked, card_id))
        return bool(new_locked)

    def recycle_cards(self, qq: int, card_ids: List[int]) -> RecycleResult:
        recycled = []
        failed = []
        money = 0

        for cid in card_ids:
            row = self.db.query_one(
                "SELECT c.ID, c.User, c.Status, c.Locked, c.Star, p.Overall "
                "FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
                (cid,)
            )
            if row is None:
                failed.append(f"ID {cid} not found")
                continue
            if row[1] != qq:
                failed.append(f"ID {cid} not yours")
                continue
            if row[2] != 0:
                failed.append(f"ID {cid} in use")
                continue
            if row[3]:
                failed.append(f"ID {cid} locked")
                continue

            price = compute_price(row[5], row[4], 0)
            sell_price = price // 2
            money += sell_price
            self.db.execute("DELETE FROM cards WHERE ID = ?", (cid,))
            recycled.append(f"ID {cid}")

        if money > 0:
            self.db.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (money, qq))

        remaining = self.db.query_one("SELECT Money FROM users WHERE QQ = ?", (qq,))
        return RecycleResult(
            recycled=recycled, failed=failed, earned=money,
            remaining_money=remaining[0] if remaining else 0
        )
