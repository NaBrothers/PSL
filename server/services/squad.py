"""Squad service - formation/squad operations for web and bot."""

import json
from dataclasses import dataclass
from typing import List, Optional

from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER, FORMATION as FORMATIONS, STARS, POSITION_MAP
from psl_core.card import compute_overall, compute_real_overall, position_group
from psl_core.formation import compute_formation_abilities, position_fit_bonus


class SquadError(Exception):
    pass


class CardNotFound(SquadError):
    pass


class InvalidFormation(SquadError):
    pass


class CardNotOwned(SquadError):
    pass


@dataclass
class CardInfo:
    id: int
    player_id: int
    name: str
    position: str
    overall: int
    real_overall: int
    star: int
    style: str
    breach: int
    locked: bool
    status: int


@dataclass
class SquadData:
    formation: str
    total_ability: int
    forward_ability: int
    midfield_ability: int
    guard_ability: int
    positions: List[str]
    cards: List[Optional[CardInfo]]


@dataclass
class SwapResult:
    success: bool
    message: str


class SquadService:
    def __init__(self, db):
        self.db = db

    def get_squad(self, qq: int) -> SquadData:
        user_row = self.db.query_one("SELECT ID, QQ, Formation FROM users WHERE qq = ?", (qq,))
        if user_row is None:
            raise SquadError("User not found")
        formation = user_row[2] or "442"
        if formation not in FORMATIONS:
            formation = "442"
        positions = FORMATIONS[formation]["positions"]

        team_rows = self.db.query_all(
            "SELECT Card, Position FROM team WHERE user = ? ORDER BY position", (qq,)
        )
        if not team_rows:
            for i in range(11):
                self.db.execute(
                    "INSERT INTO team (user, card, position) VALUES (?, 0, ?)", (qq, i)
                )
            team_rows = self.db.query_all(
                "SELECT Card, Position FROM team WHERE user = ? ORDER BY position", (qq,)
            )

        cards: List[Optional[CardInfo]] = []
        for row in team_rows[:11]:
            card_id = row[0]
            slot_idx = row[1]
            if card_id == 0:
                cards.append(None)
            else:
                card_info = self._get_card_info(card_id, positions[slot_idx] if slot_idx < len(positions) else "CM")
                cards.append(card_info)

        real_overalls = [c.real_overall if c else None for c in cards]
        total, fwd, mid, grd = compute_formation_abilities(positions, real_overalls)
        return SquadData(
            formation=formation,
            total_ability=total,
            forward_ability=fwd,
            midfield_ability=mid,
            guard_ability=grd,
            positions=positions[:11],
            cards=cards,
        )

    def change_formation(self, qq: int, new_formation: str) -> str:
        if new_formation not in FORMATIONS:
            raise InvalidFormation(f"Unknown formation: {new_formation}")
        self.db.execute("UPDATE users SET formation = ? WHERE qq = ?", (new_formation, qq))
        return new_formation

    def swap_players(self, qq: int, card_id_1: int, card_id_2: int) -> SwapResult:
        team_rows = self.db.query_all(
            "SELECT Card FROM team WHERE user = ? ORDER BY position", (qq,)
        )
        team_ids = [r[0] for r in team_rows]

        bag_rows = self.db.query_all("SELECT ID FROM cards WHERE user = ?", (qq,))
        bag_ids = {r[0] for r in bag_rows}

        if card_id_1 not in bag_ids:
            raise CardNotFound("Card 1 not found in bag")
        if card_id_2 not in bag_ids:
            raise CardNotFound("Card 2 not found in bag")

        in_team_1 = card_id_1 in team_ids
        in_team_2 = card_id_2 in team_ids

        if not in_team_1 and not in_team_2:
            raise SquadError("At least one card must be in the squad")

        if in_team_1 and in_team_2:
            self.db.execute("UPDATE team SET card = -1 WHERE user = ? AND card = ?", (qq, card_id_1))
            self.db.execute("UPDATE team SET card = ? WHERE user = ? AND card = ?", (card_id_1, qq, card_id_2))
            self.db.execute("UPDATE team SET card = ? WHERE user = ? AND card = -1", (card_id_2, qq))
        elif in_team_1:
            status_row = self.db.query_one("SELECT Status FROM cards WHERE id = ?", (card_id_2,))
            if status_row and status_row[0] != 0:
                raise SquadError("Card 2 status invalid for squad")
            self.db.execute("UPDATE team SET card = ? WHERE user = ? AND card = ?", (card_id_2, qq, card_id_1))
            self.db.execute("UPDATE cards SET status = 0 WHERE id = ?", (card_id_1,))
            self.db.execute("UPDATE cards SET status = 2 WHERE id = ?", (card_id_2,))
        else:
            status_row = self.db.query_one("SELECT Status FROM cards WHERE id = ?", (card_id_1,))
            if status_row and status_row[0] != 0:
                raise SquadError("Card 1 status invalid for squad")
            self.db.execute("UPDATE team SET card = ? WHERE user = ? AND card = ?", (card_id_1, qq, card_id_2))
            self.db.execute("UPDATE cards SET status = 0 WHERE id = ?", (card_id_2,))
            self.db.execute("UPDATE cards SET status = 2 WHERE id = ?", (card_id_1,))

        return SwapResult(success=True, message="Swap successful")

    def assign_player(self, qq: int, slot: int, card_id: int) -> SwapResult:
        team_rows = self.db.query_all(
            "SELECT Card FROM team WHERE user = ? ORDER BY position", (qq,)
        )
        if slot < 0 or slot >= len(team_rows):
            raise SquadError("Invalid slot")
        existing_card_id = team_rows[slot][0]
        if existing_card_id != 0:
            existing = self.db.query_one("SELECT ID FROM cards WHERE id = ? AND user = ?", (existing_card_id, qq))
            if existing:
                raise SquadError("Slot is not empty, use swap instead")
            self.db.execute("UPDATE team SET card = 0 WHERE user = ? AND position = ?", (qq, slot))

        bag_rows = self.db.query_all("SELECT ID, Status FROM cards WHERE user = ? AND id = ?", (qq, card_id))
        if not bag_rows:
            raise CardNotFound("Card not found in bag")
        if bag_rows[0][1] != 0:
            raise SquadError("Card status invalid for squad")

        self.db.execute("UPDATE team SET card = ? WHERE user = ? AND position = ?", (card_id, qq, slot))
        self.db.execute("UPDATE cards SET status = 2 WHERE id = ?", (card_id,))
        return SwapResult(success=True, message="Assign successful")

    def auto_squad(self, qq: int) -> SquadData:
        user_row = self.db.query_one("SELECT Formation FROM users WHERE qq = ?", (qq,))
        formation = (user_row[0] if user_row else None) or "442"
        if formation not in FORMATIONS:
            formation = "442"
        positions = FORMATIONS[formation]["positions"]

        bag_rows = self.db.query_all(
            "SELECT ID, Player, Star, Style, Status, Ext_Abilities, Breach FROM cards WHERE user = ? AND (status = 0 OR status = 2)",
            (qq,)
        )

        self.db.execute("UPDATE cards SET status = 0 WHERE user = ? AND status = 2", (qq,))

        selected_players: set = set()
        result = [0] * 11

        slot_order = sorted(range(11), key=lambda idx: {"GK": 0, "D": 1, "F": 2, "M": 3}[position_group(positions[idx])])

        for slot_index in slot_order:
            slot = positions[slot_index]
            candidates = [r for r in bag_rows if r[1] not in selected_players]
            if not candidates:
                break
            best = max(candidates, key=lambda r: self._card_score_for_slot(r, slot))
            result[slot_index] = best[0]
            selected_players.add(best[1])

        for i in range(11):
            self.db.execute(
                "UPDATE team SET card = ? WHERE user = ? AND position = ?",
                (result[i], qq, i)
            )

        active_ids = [r for r in result if r != 0]
        if active_ids:
            placeholders = ",".join("?" * len(active_ids))
            self.db.execute(
                f"UPDATE cards SET status = 2 WHERE user = ? AND id IN ({placeholders})",
                (qq, *active_ids)
            )

        return self.get_squad(qq)

    def _card_score_for_slot(self, card_row, slot: str) -> int:
        card_id, player_id, star, style, status, ext_abilities, breach = card_row
        real_ov = self._compute_real_overall_for_card(card_id, slot)
        fit_bonus = self._get_position_fit_bonus(player_id, slot)
        return real_ov + fit_bonus

    def _get_position_fit_bonus(self, player_id: int, slot: str) -> int:
        row = self.db.query_one("SELECT Position FROM players WHERE ID = ?", (player_id,))
        if not row:
            return 0
        player_positions = [p.strip() for p in (row[0] or "").split(",")]
        return position_fit_bonus(player_positions, slot)

    def _get_card_info(self, card_id: int, slot_position: str) -> Optional[CardInfo]:
        row = self.db.query_one(
            "SELECT c.ID, c.Player, c.Star, c.Style, c.Status, c.Locked, c.Breach, "
            "c.Ext_Abilities, p.Name, p.Position, p.Overall "
            "FROM cards c JOIN players p ON c.Player = p.ID WHERE c.ID = ?",
            (card_id,)
        )
        if row is None:
            return None
        overall = compute_overall(row[10], row[2])
        real_overall = self._compute_real_overall_for_card(row[0], slot_position)
        return CardInfo(
            id=row[0],
            player_id=row[1],
            name=row[8],
            position=row[9],
            overall=overall,
            real_overall=real_overall,
            star=row[2],
            style=row[3],
            breach=row[6],
            locked=bool(row[5]),
            status=row[4] or 0,
        )

    def _compute_real_overall_for_card(self, card_id: int, slot: str) -> int:
        card_row = self.db.query_one("SELECT User FROM cards WHERE ID = ?", (card_id,))
        if not card_row:
            return 80
        from server.services.bag import BagService
        detail = BagService(self.db).get_card_detail(card_id, card_row[0])
        mapped = POSITION_MAP.get(slot, "CM")
        for item in detail.get("all_position_ratings", []):
            if item.get("position") == mapped:
                return item["rating"]
        return detail["overall"]

    def _compute_real_overall_for_player(self, player_id: int, star: int, style: str, ext_abilities, slot: str) -> int:
        card_row = self.db.query_one(
            "SELECT ID, User FROM cards WHERE Player = ? AND Star = ? AND Style = ? LIMIT 1",
            (player_id, star, style),
        )
        if not card_row:
            return 80
        return self._compute_real_overall_for_card(card_row[0], slot)
