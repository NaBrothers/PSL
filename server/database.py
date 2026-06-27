import sqlite3
from server.config import DB_PATH


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
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

    @property
    def lastrowid(self):
        return self.db.execute("SELECT last_insert_rowid()").fetchone()[0]


db = Database()
