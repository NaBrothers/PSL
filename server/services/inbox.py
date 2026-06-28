"""Inbox service - message center for game events."""

import json
from datetime import datetime, timezone
from typing import Optional


class InboxService:
    def __init__(self, db):
        self.db = db

    def send(self, user_qq: int, msg_type: str, title: str, content: str = "", data: Optional[dict] = None):
        now = datetime.now(timezone.utc).isoformat()
        data_str = json.dumps(data, ensure_ascii=False) if data else None
        self.db.execute(
            "INSERT INTO inbox (User, Type, Title, Content, Data, CreatedAt) VALUES (?, ?, ?, ?, ?, ?)",
            (user_qq, msg_type, title, content, data_str, now)
        )

    def broadcast(self, msg_type: str, title: str, content: str = "", data: Optional[dict] = None):
        self.send(0, msg_type, title, content, data)

    def get_messages(self, user_qq: int, page: int = 1, page_size: int = 20):
        offset = (page - 1) * page_size
        rows = self.db.query_all(
            "SELECT ID, Type, Title, Content, Data, Read, CreatedAt FROM inbox "
            "WHERE User = ? OR User = 0 ORDER BY CreatedAt DESC LIMIT ? OFFSET ?",
            (user_qq, page_size, offset)
        )
        return [
            {
                "id": r[0],
                "type": r[1],
                "title": r[2],
                "content": r[3] or "",
                "data": json.loads(r[4]) if r[4] else None,
                "read": bool(r[5]),
                "created_at": r[6],
            }
            for r in rows
        ]

    def get_unread_count(self, user_qq: int) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) FROM inbox WHERE (User = ? OR User = 0) AND Read = 0",
            (user_qq,)
        )
        return row[0] if row else 0

    def mark_read(self, user_qq: int, message_id: Optional[int] = None):
        if message_id:
            self.db.execute(
                "UPDATE inbox SET Read = 1 WHERE ID = ? AND (User = ? OR User = 0)",
                (message_id, user_qq)
            )
        else:
            self.db.execute(
                "UPDATE inbox SET Read = 1 WHERE (User = ? OR User = 0) AND Read = 0",
                (user_qq,)
            )

    def delete_read(self, user_qq: int):
        self.db.execute(
            "DELETE FROM inbox WHERE (User = ? OR User = 0) AND Read = 1",
            (user_qq,)
        )
