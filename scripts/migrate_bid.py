#!/usr/bin/env python3
"""Migration: add bid_orders, trade_history tables and transfer.CreatedAt column."""

import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "psl.db")


def migrate(db_path: str = DB_PATH):
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add CreatedAt to transfer table if missing
    cursor.execute("PRAGMA table_info(transfer)")
    cols = [row[1] for row in cursor.fetchall()]
    if "CreatedAt" not in cols:
        cursor.execute("ALTER TABLE transfer ADD COLUMN CreatedAt TEXT DEFAULT ''")
        cursor.execute("UPDATE transfer SET CreatedAt = datetime('now') WHERE CreatedAt = ''")
        print("Added CreatedAt to transfer table")

    # Create bid_orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bid_orders (
          ID INTEGER PRIMARY KEY AUTOINCREMENT,
          BuyerQQ INTEGER NOT NULL,
          PlayerName TEXT,
          MinStar INTEGER DEFAULT 1,
          Position TEXT,
          Style TEXT,
          MaxPrice INTEGER NOT NULL,
          Status INTEGER DEFAULT 0,
          CreatedAt TEXT NOT NULL DEFAULT (datetime('now')),
          MatchedAt TEXT,
          MatchedCardID INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bid_orders_status ON bid_orders(Status, CreatedAt)")
    print("Created bid_orders table")

    # Create trade_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
          ID INTEGER PRIMARY KEY AUTOINCREMENT,
          CardID INTEGER NOT NULL,
          PlayerID INTEGER NOT NULL,
          Star INTEGER NOT NULL,
          SellerQQ INTEGER NOT NULL,
          BuyerQQ INTEGER NOT NULL,
          Price INTEGER NOT NULL,
          Fee INTEGER NOT NULL,
          Source TEXT NOT NULL,
          CreatedAt TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_player ON trade_history(PlayerID, Star, CreatedAt DESC)")
    print("Created trade_history table")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
