import sqlite3
import threading
from server.config import DB_PATH


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self._local = threading.local()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.isolation_level = None
            self._local.conn = conn
        return self._local.conn

    @property
    def db(self):
        return self._get_conn()

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def execute(self, sql, params=()):
        cursor = self._get_conn().cursor()
        cursor.execute(sql, params)
        return cursor

    def query_one(self, sql, params=()):
        cursor = self._get_conn().cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()

    def query_all(self, sql, params=()):
        cursor = self._get_conn().cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()

    @property
    def lastrowid(self):
        return self._get_conn().execute("SELECT last_insert_rowid()").fetchone()[0]


db = Database()
