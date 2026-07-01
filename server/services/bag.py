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
    top_abilities: list = None
    can_upgrade: bool = False
    can_breach: bool = False


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
                sort: str = "overall", position: str = "", color: str = "", upgradable: bool = False) -> BagPage:
        rows = self.db.query_all(
            "SELECT c.ID, c.Player, c.Star, c.Style, c.Status, c.Locked, c.Breach, "
            "c.Ext_Abilities, "
            "p.Name, p.Position, p.Overall, p.Height, "
            "p.Heading_Accuracy, p.Jumping, p.Strength, p.Long_Shots, p.Shot_Power, "
            "p.Finishing, p.Long_Passing, p.Short_Passing, p.Dribbling, p.Ball_Control, "
            "p.Balance, p.Sliding_Tackle, p.Standing_Tackle, p.Defensive_Awareness, "
            "p.Aggression, p.Interceptions, p.Sprint_Speed, p.Acceleration, "
            "p.Composure, p.GK_Handling, p.GK_Diving, p.GK_Positioning, p.GK_Reflexes, p.Reactions, "
            "c.Talents "
            "FROM cards c JOIN players p ON c.Player = p.ID "
            "WHERE c.User = ?",
            (qq,)
        )

        import json as _json
        from psl_core.talent import generate_talents
        ABILITY_NAMES = {"Heading": "头球", "Finishing": "终结", "Short_Passing": "短传",
            "Dribbling": "盘带", "Tackling": "抢断", "Defence": "防守", "Speed": "速度",
            "Long_Shot": "远射", "Long_Passing": "长传", "IQ": "球商",
            "GK_Saving": "扑救", "GK_Positioning": "站位", "GK_Reaction": "反应"}

        team_slots = self.db.query_all("SELECT card, position FROM team WHERE user = ?", (qq,))
        card_slot_map = {r[0]: r[1] for r in team_slots if r[0] != 0}

        cards = []
        for r in rows:
            ov = compute_overall(r[10], r[2])
            pos = (r[9] or "").split(",")[0].strip()
            ext = _json.loads(r[7]) if r[7] else {}
            talents_raw = r[36] if len(r) > 36 else None
            talents_data = _json.loads(talents_raw) if talents_raw else None
            if talents_data is None:
                talents_data = generate_talents()
                self.db.execute("UPDATE cards SET Talents = ? WHERE ID = ?", (_json.dumps(talents_data), r[0]))
            height_str = r[11] or "180"
            height_val = int(height_str) if str(height_str).isdigit() else 180
            abilities = compute_abilities(
                star=r[2], style=r[3], position=pos, height=height_val,
                heading_accuracy=r[12] or 0, jumping=r[13] or 0, strength=r[14] or 0,
                long_shots=r[15] or 0, shot_power=r[16] or 0, finishing=r[17] or 0,
                long_passing=r[18] or 0, short_passing=r[19] or 0, dribbling=r[20] or 0,
                ball_control=r[21] or 0, balance=r[22] or 0, sliding_tackle=r[23] or 0,
                standing_tackle=r[24] or 0, defensive_awareness=r[25] or 0,
                aggression=r[26] or 0, interceptions=r[27] or 0, sprint_speed=r[28] or 0,
                acceleration=r[29] or 0, composure=r[30] or 0, gk_handling=r[31] or 0,
                gk_diving=r[32] or 0, gk_positioning=r[33] or 0, gk_reflexes=r[34] or 0,
                reactions=r[35] or 0, ext_abilities=ext,
                talents=talents_data, talent_mode='display',
            )
            # Get top 3 abilities (exclude GK stats for non-GK)
            exclude = {"GK_Saving", "GK_Positioning", "GK_Reaction"} if pos not in GOALKEEPER else {"Heading", "Finishing", "Long_Shot", "Tackling"}
            ability_list = [(ABILITY_NAMES.get(k, k), v) for k, v in abilities.items() if k not in exclude]
            ability_list.sort(key=lambda x: -x[1])
            top3 = [{"name": a[0], "value": a[1]} for a in ability_list[:3]]
            card_status = r[4] or 0
            if card_status == 2:
                slot = card_slot_map.get(r[0])
                status_text = "替补" if slot is not None and slot >= 11 else "首发"
            elif card_status == 1:
                status_text = "转会中"
            else:
                status_text = ""
            cards.append(BagCardInfo(
                id=r[0], player_id=r[1], name=r[8], position=pos,
                overall=ov, real_overall=ov, star=r[2], style=r[3],
                breach=r[6], locked=bool(r[5]), status=card_status,
                status_text=status_text,
                top_abilities=top3,
            ))

        # Compute red dot flags
        from collections import defaultdict
        by_player: dict = defaultdict(list)
        for c in cards:
            by_player[c.player_id].append(c)
        for group in by_player.values():
            if len(group) < 2:
                continue
            for c in group:
                # Can breach: same player, different card exists
                c.can_breach = True
                # Can upgrade: same player + star diff == 1 (or both star 1)
                for other in group:
                    if other.id == c.id:
                        continue
                    if (c.star == 1 and other.star == 1) or abs(c.star - other.star) == 1:
                        c.can_upgrade = True
                        break

        if upgradable:
            cards = [c for c in cards if c.can_upgrade]

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
            "p.GK_Diving, p.GK_Handling, p.GK_Kicking, p.GK_Positioning, p.GK_Reflexes, "
            "c.Talents "
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

        from psl_core.talent import generate_talents, get_talent_display
        from psl_core.constants import GOALKEEPER as _GOALKEEPER
        talents_raw = row[59] if len(row) > 59 else None
        talents_data = json.loads(talents_raw) if talents_raw else None
        if talents_data is None:
            talents_data = generate_talents()
            self.db.execute("UPDATE cards SET Talents = ? WHERE ID = ?", (json.dumps(talents_data), card_id))

        is_gk = position in _GOALKEEPER

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
            talents=talents_data,
            talent_mode="display",
        )

        ABILITY_NAMES = {**ABILITIES, **GK_ABILITIES, "IQ": "球商"}

        from psl_core.constants import STYLE as _STYLE, GK_STYLE as _GK_STYLE, GOALKEEPER as _GK
        _sd = _GK_STYLE.get(style) if position in _GK else _STYLE.get(style)
        style_keys = set(k for k in (_sd or {}) if k != "name")
        position_ratings = compute_all_position_ratings(abilities)
        overall_with_star = compute_overall(base_overall, star)

        for item in position_ratings:
            item["diff"] = item["rating"] - overall_with_star

        price = compute_price(base_overall, star, row[6] or 0)

        talent_display = get_talent_display(talents_data, is_gk, star)

        owner_qq_row = self.db.query_one("SELECT User FROM cards WHERE ID = ?", (card_id,))
        can_upgrade = False
        can_breach = False
        if owner_qq_row:
            dupes = self.db.query_one(
                "SELECT COUNT(*) FROM cards WHERE Player = ? AND User = ? AND ID != ? AND Status = 0 AND Locked = 0",
                (row[1], owner_qq_row[0], card_id)
            )
            if dupes and dupes[0] > 0:
                can_breach = True
                # can_upgrade requires star diff == 1 or both star 1
                upgrade_check = self.db.query_one(
                    "SELECT COUNT(*) FROM cards WHERE Player = ? AND User = ? AND ID != ? AND Status = 0 AND Locked = 0 "
                    "AND (ABS(Star - ?) = 1 OR (Star = 1 AND ? = 1))",
                    (row[1], owner_qq_row[0], card_id, star, star)
                )
                if upgrade_check and upgrade_check[0] > 0:
                    can_upgrade = True


        return {
            "id": row[0], "player_id": row[1], "star": star, "style": style,
            "style_name": get_style_name(style, position),
            "status": row[4] or 0, "locked": bool(row[5]), "breach": row[6] or 0,
            "overall": overall_with_star,
            "name": row[18], "position": position, "age": row[21],
            "height": row[22], "weight": row[23], "nationality": row[24],
            "price": price,
            "can_upgrade": can_upgrade, "can_breach": can_breach, "owner_qq": owner_qq_row[0] if owner_qq_row else 0,
            "abilities": {k: {"value": v, "name": ABILITY_NAMES.get(k, k), "ext": ext.get(k, 0), "style_boosted": k in style_keys} for k, v in abilities.items()},
            "position_ratings": position_ratings[:3],
            "all_position_ratings": position_ratings,
            "season": {"appearance": row[7], "goal": row[8], "assist": row[9], "tackle": row[10], "save": row[11]},
            "career": {"appearance": row[12], "goal": row[13], "assist": row[14], "tackle": row[15], "save": row[16]},
            "ext_abilities": ext,
            "talents": {
                "dimensions": talent_display,
                "revealed_count": min(star, 6),
                "total": 6,
                "reroll_count": talents_data.get("rc", 0),
                "reroll_max": 2,
            },
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
