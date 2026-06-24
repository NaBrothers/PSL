"""Card repository - parameterized SQL queries."""

import json
from typing import List, Optional

from domain.card import CardData
from domain.player import PlayerData
from repository.base import Database
from repository.player_repo import PlayerRepository
from repository.user_repo import UserRepository


class CardRepository:
    def __init__(self, db: Database):
        self.db = db
        self._player_repo = PlayerRepository(db)

    def get_by_id(self, card_id: int) -> Optional[CardData]:
        row = self.db.query_one("SELECT * FROM cards WHERE id = ?", (card_id,))
        if row is None:
            return None
        return self._row_to_card(row)

    def get_by_ids(self, card_ids: List[int]) -> List[CardData]:
        if not card_ids:
            return []
        placeholders = ",".join("?" for _ in card_ids)
        rows = self.db.query_all(
            f"SELECT * FROM cards WHERE id IN ({placeholders})", tuple(card_ids)
        )
        return [self._row_to_card(r) for r in rows]

    def get_by_user(self, qq: int) -> List[CardData]:
        rows = self.db.query_all("SELECT * FROM cards WHERE User = ?", (qq,))
        return [self._row_to_card(r) for r in rows]

    def create(self, player_id: int, user_qq: int, star: int, style: str) -> int:
        self.db.execute(
            "INSERT INTO cards (Player, User, Star, Style) VALUES (?, ?, ?, ?)",
            (player_id, user_qq, star, style)
        )
        return self.db.lastrowid

    def update(self, card_id: int, **fields):
        if not fields:
            return
        set_clauses = []
        values = []
        for key, val in fields.items():
            set_clauses.append(f"{key} = ?")
            values.append(val)
        values.append(card_id)
        sql = f"UPDATE cards SET {', '.join(set_clauses)} WHERE id = ?"
        self.db.execute(sql, tuple(values))

    def delete(self, card_id: int):
        self.db.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    def _row_to_card(self, row) -> CardData:
        player = self._player_repo.get_by_id(row[1])
        ext = json.loads(row[17]) if row[17] else {}
        return CardData(
            id=row[0],
            player=player,
            user_qq=row[2],
            star=row[3],
            style=row[4],
            status=row[5] or 0,
            appearance=row[6] or 0,
            goal=row[7] or 0,
            assist=row[8] or 0,
            tackle=row[9] or 0,
            save=row[10] or 0,
            total_appearance=row[11] or 0,
            total_goal=row[12] or 0,
            total_assist=row[13] or 0,
            total_tackle=row[14] or 0,
            total_save=row[15] or 0,
            locked=bool(row[16]),
            ext_abilities=ext,
            breach=row[18] or 0,
        )
