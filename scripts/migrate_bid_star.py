#!/usr/bin/env python3
"""Rename MinStar to Star in bid_orders table."""
import sqlite3, os

DB_PATH = os.environ.get("PSL_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "psl.db"))

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(bid_orders)")
    cols = [row[1] for row in cursor.fetchall()]
    if "MinStar" in cols and "Star" not in cols:
        cursor.execute("ALTER TABLE bid_orders RENAME COLUMN MinStar TO Star")
        print("Renamed MinStar to Star")
    elif "Star" in cols:
        print("Star column already exists")
    else:
        cursor.execute("ALTER TABLE bid_orders ADD COLUMN Star INTEGER DEFAULT 0")
        print("Added Star column")
    conn.commit()
    conn.close()
    print("Done!")

if __name__ == "__main__":
    migrate()
