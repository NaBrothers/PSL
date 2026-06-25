"""Bag service - card inventory operations."""

from dataclasses import dataclass
from typing import List, Optional


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

        from server.services._formations import STARS, FORWARD, MIDFIELD, GUARD, GOALKEEPER
        STATUS_TEXT = {0: "", 1: "转会中", 2: "首发"}

        cards = []
        for r in rows:
            star_bonus = STARS.get(r[2], {}).get("ability", 0)
            ov = r[9] + star_bonus
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

        from server.services._formations import STARS, FORWARD, MIDFIELD, GUARD, GOALKEEPER
        import json
        star = row[2]
        style = row[3]
        star_bonus = STARS.get(star, {}).get("ability", 0)
        ext = json.loads(row[17]) if row[17] else {}
        position = row[19]
        base_overall = row[20]

        p = {
            "Heading_Accuracy": row[27] or 0, "Short_Passing": row[28] or 0,
            "Dribbling": row[30] or 0, "Long_Passing": row[33] or 0,
            "Ball_Control": row[34] or 0, "Acceleration": row[35] or 0,
            "Sprint_Speed": row[36] or 0, "Balance": row[39] or 0,
            "Shot_Power": row[40] or 0, "Jumping": row[41] or 0,
            "Strength": row[43] or 0, "Long_Shots": row[44] or 0,
            "Aggression": row[45] or 0, "Interceptions": row[46] or 0,
            "Composure": row[50] or 0, "Defensive_Awareness": row[51] or 0,
            "Standing_Tackle": row[52] or 0, "Sliding_Tackle": row[53] or 0,
            "GK_Diving": row[54] or 0, "GK_Handling": row[55] or 0,
            "GK_Positioning": row[57] or 0, "GK_Reflexes": row[58] or 0,
            "Reactions": row[38] or 0, "Finishing": row[26] or 0,
            "Height": row[22] or "180",
        }

        height_val = int(p["Height"]) if str(p["Height"]).isdigit() else 180
        abilities = {
            "Heading": star_bonus + int((p["Heading_Accuracy"] + p["Jumping"] + p["Strength"] + height_val - 100) / 4),
            "Long_Shot": star_bonus + int((p["Long_Shots"] + p["Shot_Power"]) / 2),
            "Finishing": star_bonus + int((p["Finishing"] * 2 + p["Shot_Power"]) / 3),
            "Long_Passing": star_bonus + int(p["Long_Passing"]),
            "Short_Passing": star_bonus + int(p["Short_Passing"]),
            "Dribbling": star_bonus + int((p["Dribbling"] * 2 + p["Ball_Control"] * 2 + p["Balance"]) / 5),
            "Tackling": star_bonus + int((p["Sliding_Tackle"] + p["Standing_Tackle"]) / 2),
            "Defence": star_bonus + int((p["Defensive_Awareness"] * 2 + p["Aggression"] + p["Interceptions"] * 2) / 5),
            "Speed": star_bonus + int((p["Sprint_Speed"] + p["Acceleration"]) / 2),
            "IQ": star_bonus + int(p["Composure"]),
            "GK_Saving": star_bonus + int((p["GK_Handling"] + p["GK_Diving"]) / 2),
            "GK_Positioning": star_bonus + int(p["GK_Positioning"]),
            "GK_Reaction": star_bonus + int((p["GK_Reflexes"] * 2 + p["Reactions"]) / 3),
        }

        for key, val in ext.items():
            if key in abilities:
                abilities[key] += int(val)

        STYLE_DATA = {
            'sniper': {'name': '狙击手', 'Dribbling': 3, 'Finishing': 3},
            'finisher': {'name': '终结者', 'Finishing': 3, 'Heading': 3},
            'deadeye': {'name': '恶魔眼', 'Short_Passing': 3, 'Long_Passing': 3, 'Finishing': 3},
            'marksman': {'name': '神枪手', 'Dribbling': 2, 'Finishing': 2, 'Heading': 2},
            'hawk': {'name': '凤头鹰', 'Speed': 2, 'Finishing': 2, 'Heading': 2},
            'artist': {'name': '艺术家', 'Long_Passing': 3, 'Dribbling': 3},
            'architect': {'name': '建筑师', 'Short_Passing': 3, 'Long_Passing': 3},
            'powerhous': {'name': '抢球机器', 'Tackling': 3, 'Long_Passing': 3},
            'maestro': {'name': '大师', 'Dribbling': 2, 'Short_Passing': 2, 'Long_Shot': 2},
            'engine': {'name': '发动机', 'Speed': 2, 'Short_Passing': 2, 'Dribbling': 2},
            'sentinal': {'name': '哨兵', 'Tackling': 3, 'Defence': 3},
            'guardian': {'name': '护卫', 'Dribbling': 3, 'Defence': 3},
            'gladiator': {'name': '斗士', 'Shooting': 3, 'Defence': 3},
            'backbone': {'name': '骨干', 'Long_Passing': 2, 'Tackling': 2, 'Defence': 2},
            'anchor': {'name': '铁锚', 'Speed': 2, 'Tackling': 2, 'Defence': 2},
            'hunter': {'name': '狩猎者', 'Finishing': 3, 'Speed': 3},
            'catalyst': {'name': '催化剂', 'Speed': 3, 'Long_Passing': 3},
            'shadow': {'name': '暗影', 'Speed': 3, 'Tackling': 3},
            'speedster': {'name': '疾速魔', 'Speed': 3, 'Dribbling': 3},
            'slugger': {'name': '重炮手', 'Long_Shot': 3, 'Heading': 3},
            'bronzewall': {'name': '铜墙', 'GK_Saving': 3, 'Long_Passing': 3},
            'ironwall': {'name': '铁壁', 'GK_Reaction': 2, 'Speed': 2, 'Long_Passing': 2},
            'agilecat': {'name': '灵猫', 'GK_Reaction': 2, 'Speed': 2, 'GK_Positioning': 2},
            'gloves': {'name': '手套', 'GK_Reaction': 2, 'GK_Saving': 2, 'Speed': 2},
        }
        style_data = STYLE_DATA.get(style, {})
        for ability, bonus in style_data.items():
            if ability != "name" and ability in abilities:
                abilities[ability] += bonus * star

        ABILITY_NAMES = {
            "Heading": "头球", "Long_Shot": "远射", "Finishing": "终结",
            "Long_Passing": "长传", "Short_Passing": "短传", "Dribbling": "盘带",
            "Tackling": "抢断", "Defence": "防守", "Speed": "速度", "IQ": "球商",
            "GK_Saving": "GK扑救", "GK_Positioning": "GK站位", "GK_Reaction": "GK反应",
        }

        REAL_ABILITY = {
            "ST": {"Heading": 0.18, "Long_Shot": 0.1, "Finishing": 0.30, "Long_Passing": 0, "Short_Passing": 0.05, "Dribbling": 0.27, "Tackling": 0, "Defence": 0, "Speed": 0.1},
            "CF": {"Heading": 0.03, "Long_Shot": 0.06, "Finishing": 0.17, "Long_Passing": 0, "Short_Passing": 0.14, "Dribbling": 0.45, "Tackling": 0, "Defence": 0, "Speed": 0.15},
            "LRW": {"Heading": 0, "Long_Shot": 0.06, "Finishing": 0.15, "Long_Passing": 0, "Short_Passing": 0.14, "Dribbling": 0.45, "Tackling": 0, "Defence": 0, "Speed": 0.2},
            "LRM": {"Heading": 0, "Long_Shot": 0.07, "Finishing": 0.125, "Long_Passing": 0.03, "Short_Passing": 0.19, "Dribbling": 0.435, "Tackling": 0, "Defence": 0, "Speed": 0.15},
            "AM": {"Heading": 0, "Long_Shot": 0.08, "Finishing": 0.1, "Long_Passing": 0.06, "Short_Passing": 0.24, "Dribbling": 0.42, "Tackling": 0, "Defence": 0, "Speed": 0.1},
            "CM": {"Heading": 0, "Long_Shot": 0.06, "Finishing": 0.03, "Long_Passing": 0.19, "Short_Passing": 0.25, "Dribbling": 0.31, "Tackling": 0.07, "Defence": 0.07, "Speed": 0},
            "DM": {"Heading": 0, "Long_Shot": 0, "Finishing": 0, "Long_Passing": 0.13, "Short_Passing": 0.18, "Dribbling": 0.13, "Tackling": 0.22, "Defence": 0.35, "Speed": 0},
            "CB": {"Heading": 0.12, "Long_Shot": 0, "Finishing": 0, "Long_Passing": 0, "Short_Passing": 0.06, "Dribbling": 0.05, "Tackling": 0.33, "Defence": 0.41, "Speed": 0.02},
            "LRB": {"Heading": 0.05, "Long_Shot": 0, "Finishing": 0, "Long_Passing": 0, "Short_Passing": 0.09, "Dribbling": 0.09, "Tackling": 0.33, "Defence": 0.27, "Speed": 0.16},
            "GK": {"GK_Saving": 0.33, "GK_Reaction": 0.33, "GK_Positioning": 0.33},
        }

        position_ratings = {}
        for pos_key, weights in REAL_ABILITY.items():
            total = 0
            for attr, weight in weights.items():
                total += weight * abilities.get(attr, 0)
            position_ratings[pos_key] = int(total)

        overall_with_star = base_overall + star_bonus
        sorted_positions = sorted(
            [
                {"position": pos, "rating": rating, "diff": rating - overall_with_star}
                for pos, rating in position_ratings.items()
            ],
            key=lambda x: x["rating"],
            reverse=True,
        )

        x = base_overall - 74 if base_overall >= 80 else 6
        base_price = int(0.0131*x**5 - 0.6118*x**4 + 11.189*x**3 - 55.238*x**2 + 123.16*x - 29.137)
        star_count = STARS.get(star, {}).get("count", 1)
        price = base_price * star_count + base_price * (row[6] or 0)

        return {
            "id": row[0], "player_id": row[1], "star": star, "style": style,
            "style_name": style_data.get("name", style),
            "status": row[4] or 0, "locked": bool(row[5]), "breach": row[6] or 0,
            "overall": overall_with_star,
            "name": row[18], "position": position, "age": row[21],
            "height": row[22], "weight": row[23], "nationality": row[24],
            "price": price,
            "abilities": {k: {"value": v, "name": ABILITY_NAMES.get(k, k), "ext": ext.get(k, 0)} for k, v in abilities.items()},
            "position_ratings": sorted_positions[:3],
            "all_position_ratings": sorted_positions,
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

            from server.services._formations import STARS
            star_data = STARS.get(row[4], {"count": 1})
            overall = row[5]
            x = overall - 74 if overall >= 80 else 6
            base_price = int(0.0131*x**5 - 0.6118*x**4 + 11.189*x**3 - 55.238*x**2 + 123.16*x - 29.137)
            price = base_price * star_data["count"] + base_price * 0
            sell_price = int(price) // 2
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
