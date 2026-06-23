"""User repository - parameterized SQL queries."""

from domain.user import UserData
from repository.base import Database


def _row_to_user(row) -> UserData:
    return UserData(
        id=row[0],
        qq=row[1],
        name=row[2] or "",
        level=row[3] or 0,
        money=row[4] or 0,
        formation=row[5] or "442",
        is_admin=bool(row[6]) if row[6] else False,
    )


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_qq(self, qq: int):
        row = self.db.query_one("SELECT * FROM users WHERE qq = ?", (qq,))
        if row is None:
            return None
        return _row_to_user(row)

    def get_by_id(self, user_id: int):
        row = self.db.query_one("SELECT * FROM users WHERE ID = ?", (user_id,))
        if row is None:
            return None
        return _row_to_user(row)

    def create(self, qq: int, name: str) -> UserData:
        self.db.execute(
            "INSERT INTO users (qq, name, level, money) VALUES (?, ?, 0, 0)",
            (qq, name)
        )
        return self.get_by_qq(qq)

    def update_money(self, qq: int, delta: int):
        self.db.execute("UPDATE users SET money = money + ? WHERE qq = ?", (delta, qq))

    def set_formation(self, qq: int, formation: str):
        self.db.execute("UPDATE users SET formation = ? WHERE qq = ?", (formation, qq))

    def get_all(self):
        rows = self.db.query_all("SELECT * FROM users")
        return [_row_to_user(r) for r in rows]
