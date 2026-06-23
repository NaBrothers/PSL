"""Player repository - parameterized SQL queries for FIFA player data."""

from domain.player import PlayerData
from repository.base import Database


def _row_to_player(row) -> PlayerData:
    return PlayerData(
        id=row[0],
        name=row[2],
        age=row[3] or 0,
        overall=row[7] or 0,
        position=row[22] or "",
        height=row[24] or "175",
        weight=row[25] or "150lbs",
        nationality=row[5] or "",
        club=row[9] or "",
        crossing=row[55] or 0,
        finishing=row[56] or 0,
        heading_accuracy=row[57] or 0,
        short_passing=row[58] or 0,
        volleys=row[59] or 0,
        dribbling=row[60] or 0,
        curve=row[61] or 0,
        fk_accuracy=row[62] or 0,
        long_passing=row[63] or 0,
        ball_control=row[64] or 0,
        acceleration=row[65] or 0,
        sprint_speed=row[66] or 0,
        agility=row[67] or 0,
        reactions=row[68] or 0,
        balance=row[69] or 0,
        shot_power=row[70] or 0,
        jumping=row[71] or 0,
        stamina=row[72] or 0,
        strength=row[73] or 0,
        long_shots=row[74] or 0,
        aggression=row[75] or 0,
        interceptions=row[76] or 0,
        positioning=row[77] or 0,
        vision=row[78] or 0,
        penalties=row[79] or 0,
        composure=row[80] or 0,
        defensive_awareness=row[81] or 0,
        standing_tackle=row[82] or 0,
        sliding_tackle=row[83] or 0,
        gk_diving=row[84] or 0,
        gk_handling=row[85] or 0,
        gk_kicking=row[86] or 0,
        gk_positioning=row[87] or 0,
        gk_reflexes=row[88] or 0,
    )


class PlayerRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_id(self, player_id: int):
        row = self.db.query_one("SELECT * FROM players WHERE id = ?", (player_id,))
        if row is None:
            return None
        return _row_to_player(row)

    def get_by_ids(self, player_ids: list):
        if not player_ids:
            return []
        placeholders = ",".join("?" for _ in player_ids)
        rows = self.db.query_all(
            f"SELECT * FROM players WHERE id IN ({placeholders})", tuple(player_ids)
        )
        return [_row_to_player(r) for r in rows]

    def get_all(self):
        rows = self.db.query_all("SELECT * FROM players")
        return [_row_to_player(r) for r in rows]

    def get_by_position(self, position: str):
        rows = self.db.query_all("SELECT * FROM players WHERE Position = ?", (position,))
        return [_row_to_player(r) for r in rows]

    def get_by_overall_range(self, min_overall: int, max_overall: int):
        rows = self.db.query_all(
            "SELECT * FROM players WHERE Overall >= ? AND Overall <= ?",
            (min_overall, max_overall)
        )
        return [_row_to_player(r) for r in rows]

    def search_by_name(self, name: str):
        rows = self.db.query_all(
            "SELECT * FROM players WHERE Name LIKE ?", (f"%{name}%",)
        )
        return [_row_to_player(r) for r in rows]
