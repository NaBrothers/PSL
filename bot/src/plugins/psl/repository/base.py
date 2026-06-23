"""Database connection management - parameterized queries only."""

import sqlite3
import os

from config import PROJECT_DIR


class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.environ.get("PSL_DB_PATH", os.path.join(PROJECT_DIR, "psl.db"))
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.isolation_level = None

    def close(self):
        self.db.close()

    def execute(self, sql, params=()):
        cursor = self.db.cursor()
        cursor.execute(sql, params)
        return cursor

    def query_one(self, sql, params=()):
        cursor = self.db.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()

    def query_all(self, sql, params=()):
        cursor = self.db.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()

    def query_count(self, sql, params=()):
        cursor = self.db.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return len(rows)

    @property
    def lastrowid(self):
        return self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
