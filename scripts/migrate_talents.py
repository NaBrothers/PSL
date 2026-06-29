#!/usr/bin/env python3
"""Migration: add Talents column to cards table for existing databases."""

import sqlite3
import os
import sys

DB_PATH = os.environ.get("PSL_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "psl.db"))


def migrate(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(cards)")
    columns = [row[1] for row in cursor.fetchall()]
    if "Talents" not in columns:
        cursor.execute("ALTER TABLE cards ADD COLUMN Talents TEXT DEFAULT NULL")
        conn.commit()
        print(f"Added Talents column to cards table in {db_path}")
    else:
        print("Talents column already exists, skipping")
    conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    migrate(path)
