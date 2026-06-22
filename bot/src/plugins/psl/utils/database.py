import sqlite3
import os
from config import *
from utils.const import Const


class SQLiteCursor:
    """Wrapper around sqlite3.Cursor that mimics pymysql cursor behavior.
    
    pymysql: execute() returns row count, then fetchone/fetchall retrieves rows.
    sqlite3: execute() doesn't return count; need to buffer results for SELECTs.
    """

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor()
        self._rows = None
        self._index = 0

    def execute(self, sql):
        self._cursor.execute(sql)
        if sql.strip().upper().startswith("SELECT"):
            self._rows = self._cursor.fetchall()
            self._index = 0
            return len(self._rows)
        self._rows = None
        self._index = 0
        return self._cursor.rowcount

    def fetchone(self):
        if self._rows is None:
            return self._cursor.fetchone()
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    def fetchall(self):
        if self._rows is None:
            return self._cursor.fetchall()
        remaining = self._rows[self._index:]
        self._index = len(self._rows)
        return remaining

    def close(self):
        self._cursor.close()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid


class Database:

    def __init__(self):
        self.db_path = os.environ.get("PSL_DB_PATH", os.path.join(PROJECT_DIR, "psl.db"))
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.isolation_level = None

    def __del__(self):
        self.db.close()

    def cursor(self):
        return SQLiteCursor(self.db)

    def update(self, sql: str):
        self.db.execute(sql)


g_database = Database()
