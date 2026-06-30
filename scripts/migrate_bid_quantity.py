#!/usr/bin/env python3
"""Add Quantity and Filled columns to bid_orders table."""
import sqlite3
import sys
import os

DB_PATH = os.environ.get("PSL_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "psl.db"))

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(bid_orders)")
    cols = [row[1] for row in cursor.fetchall()]
    
    if "Quantity" not in cols:
        cursor.execute("ALTER TABLE bid_orders ADD COLUMN Quantity INTEGER DEFAULT 1")
        print("Added Quantity column")
    else:
        print("Quantity column already exists")
    
    if "Filled" not in cols:
        cursor.execute("ALTER TABLE bid_orders ADD COLUMN Filled INTEGER DEFAULT 0")
        print("Added Filled column")
    else:
        print("Filled column already exists")
    
    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
