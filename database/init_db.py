#!/usr/bin/env python3
"""Initialize the SQLite database for PSL bot."""

import sqlite3
import os
import re
import sys

DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "psl.db")
SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))


SCHEMAS = """
CREATE TABLE IF NOT EXISTS users (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  QQ INTEGER NOT NULL UNIQUE,
  Name TEXT DEFAULT NULL,
  Level INTEGER DEFAULT NULL,
  Money INTEGER DEFAULT NULL,
  Formation TEXT DEFAULT '442',
  isAdmin INTEGER DEFAULT 0,
  WebPinHash TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS players (
  PrimaryID INTEGER PRIMARY KEY,
  ID INTEGER DEFAULT NULL,
  Name TEXT DEFAULT NULL,
  Age INTEGER DEFAULT NULL,
  Photo TEXT DEFAULT NULL,
  Nationality TEXT DEFAULT NULL,
  Flag TEXT DEFAULT NULL,
  Overall INTEGER DEFAULT NULL,
  Potential INTEGER DEFAULT NULL,
  Club TEXT DEFAULT NULL,
  Club_Logo TEXT DEFAULT NULL,
  Value TEXT DEFAULT NULL,
  Wage TEXT DEFAULT NULL,
  Special INTEGER DEFAULT NULL,
  Preferred_Foot TEXT DEFAULT NULL,
  Weak_Foot TEXT DEFAULT NULL,
  Skill_Moves TEXT DEFAULT NULL,
  International_Reputation TEXT DEFAULT NULL,
  Work_Rate TEXT DEFAULT NULL,
  Body_Type TEXT DEFAULT NULL,
  Real_Face TEXT DEFAULT NULL,
  Release_Clause TEXT DEFAULT NULL,
  Position TEXT DEFAULT NULL,
  Jersey_Number INTEGER DEFAULT NULL,
  Height TEXT DEFAULT NULL,
  Weight TEXT DEFAULT NULL,
  LS TEXT DEFAULT NULL,
  ST TEXT DEFAULT NULL,
  RS TEXT DEFAULT NULL,
  LW TEXT DEFAULT NULL,
  LF TEXT DEFAULT NULL,
  CF TEXT DEFAULT NULL,
  RF TEXT DEFAULT NULL,
  RW TEXT DEFAULT NULL,
  LAM TEXT DEFAULT NULL,
  CAM TEXT DEFAULT NULL,
  RAM TEXT DEFAULT NULL,
  LM TEXT DEFAULT NULL,
  LCM TEXT DEFAULT NULL,
  CM TEXT DEFAULT NULL,
  RCM TEXT DEFAULT NULL,
  RM TEXT DEFAULT NULL,
  LWB TEXT DEFAULT NULL,
  LDM TEXT DEFAULT NULL,
  CDM TEXT DEFAULT NULL,
  RDM TEXT DEFAULT NULL,
  RWB TEXT DEFAULT NULL,
  LB TEXT DEFAULT NULL,
  LCB TEXT DEFAULT NULL,
  CB TEXT DEFAULT NULL,
  RCB TEXT DEFAULT NULL,
  RB TEXT DEFAULT NULL,
  GK TEXT DEFAULT NULL,
  Likes INTEGER DEFAULT NULL,
  Dislikes INTEGER DEFAULT NULL,
  Following INTEGER DEFAULT NULL,
  Crossing INTEGER DEFAULT NULL,
  Finishing INTEGER DEFAULT NULL,
  Heading_Accuracy INTEGER DEFAULT NULL,
  Short_Passing INTEGER DEFAULT NULL,
  Volleys INTEGER DEFAULT NULL,
  Dribbling INTEGER DEFAULT NULL,
  Curve INTEGER DEFAULT NULL,
  FK_Accuracy INTEGER DEFAULT NULL,
  Long_Passing INTEGER DEFAULT NULL,
  Ball_Control INTEGER DEFAULT NULL,
  Acceleration INTEGER DEFAULT NULL,
  Sprint_Speed INTEGER DEFAULT NULL,
  Agility INTEGER DEFAULT NULL,
  Reactions INTEGER DEFAULT NULL,
  Balance INTEGER DEFAULT NULL,
  Shot_Power INTEGER DEFAULT NULL,
  Jumping INTEGER DEFAULT NULL,
  Stamina INTEGER DEFAULT NULL,
  Strength INTEGER DEFAULT NULL,
  Long_Shots INTEGER DEFAULT NULL,
  Aggression INTEGER DEFAULT NULL,
  Interceptions INTEGER DEFAULT NULL,
  Positioning INTEGER DEFAULT NULL,
  Vision INTEGER DEFAULT NULL,
  Penalties INTEGER DEFAULT NULL,
  Composure INTEGER DEFAULT NULL,
  Defensive_Awareness INTEGER DEFAULT NULL,
  Standing_Tackle INTEGER DEFAULT NULL,
  Sliding_Tackle INTEGER DEFAULT NULL,
  GK_Diving INTEGER DEFAULT NULL,
  GK_Handling INTEGER DEFAULT NULL,
  GK_Kicking INTEGER DEFAULT NULL,
  GK_Positioning INTEGER DEFAULT NULL,
  GK_Reflexes INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS cards (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  Player INTEGER NOT NULL,
  User INTEGER NOT NULL,
  Star INTEGER NOT NULL,
  Style TEXT NOT NULL,
  Status INTEGER DEFAULT 0,
  Appearance INTEGER DEFAULT 0,
  Goal INTEGER DEFAULT 0,
  Assist INTEGER DEFAULT 0,
  Tackle INTEGER DEFAULT 0,
  Save INTEGER DEFAULT 0,
  Total_Appearance INTEGER DEFAULT 0,
  Total_Goal INTEGER DEFAULT 0,
  Total_Assist INTEGER DEFAULT 0,
  Total_Tackle INTEGER DEFAULT 0,
  Total_Save INTEGER DEFAULT 0,
  Locked INTEGER DEFAULT 0,
  Ext_Abilities TEXT DEFAULT NULL,
  Breach INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transfer (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  User INTEGER NOT NULL,
  Card INTEGER NOT NULL,
  Cost INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS challenge_times (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  User INTEGER NOT NULL UNIQUE,
  TimesLeft INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS offline (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  User INTEGER NOT NULL,
  Message TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS "global" (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  Name TEXT NOT NULL,
  Value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  User INTEGER NOT NULL,
  Type INTEGER DEFAULT NULL,
  Item INTEGER DEFAULT NULL,
  Count INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS league (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  User INTEGER NOT NULL,
  Appearance INTEGER DEFAULT 0,
  Score INTEGER DEFAULT 0,
  Win INTEGER DEFAULT 0,
  Tie INTEGER DEFAULT 0,
  Lose INTEGER DEFAULT 0,
  Goal INTEGER DEFAULT 0,
  Lost_Goal INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS team (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  User INTEGER NOT NULL,
  Card INTEGER NOT NULL,
  Position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule (
  ID INTEGER PRIMARY KEY,
  Round INTEGER NOT NULL,
  Home INTEGER NOT NULL,
  Away INTEGER NOT NULL,
  Finished INTEGER DEFAULT 0,
  Home_Goal INTEGER DEFAULT 0,
  Away_Goal INTEGER DEFAULT 0
);
"""


def import_players(conn):
    """Parse the MySQL dump and import player data."""
    players_sql = os.path.join(SQL_DIR, "players_26.sql")
    if not os.path.exists(players_sql):
        print("Warning: players_26.sql not found, skipping player import")
        return

    with open(players_sql, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r"DROP TABLE IF EXISTS `players`;\s*", "", content)
    content = re.sub(r"CREATE TABLE `players` \(.+?\);\s*", "", content, flags=re.DOTALL)

    match = re.search(r"INSERT INTO `players` VALUES\s*(.+?);", content, re.DOTALL)
    if not match:
        print("Warning: no INSERT statement found in players.sql")
        return

    values_str = match.group(1)

    def split_rows(s):
        """Split MySQL VALUES into individual row strings, handling parens in quotes."""
        rows = []
        i = 0
        while i < len(s):
            if s[i] == '(':
                i += 1
                start = i
                in_q = False
                esc = False
                while i < len(s):
                    ch = s[i]
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == "'" and not in_q:
                        in_q = True
                    elif ch == "'" and in_q:
                        in_q = False
                    elif ch == ')' and not in_q:
                        break
                    i += 1
                rows.append(s[start:i])
                i += 1
            else:
                i += 1
        return rows

    rows = split_rows(values_str)

    print(f"Importing {len(rows)} players...")
    cursor = conn.cursor()

    for row in rows:
        values = []
        in_quote = False
        escaped = False
        current = ""
        for ch in row:
            if escaped:
                current += ch
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                current += ch
                continue
            if ch == "'" and not in_quote:
                in_quote = True
                current += ch
            elif ch == "'" and in_quote:
                in_quote = False
                current += ch
            elif ch == "," and not in_quote:
                values.append(current.strip())
                current = ""
            else:
                current += ch
        values.append(current.strip())

        processed = []
        for v in values:
            if v == "NULL":
                processed.append(None)
            elif v.startswith("'") and v.endswith("'"):
                processed.append(v[1:-1].replace("\\'", "'"))
            else:
                try:
                    processed.append(int(v))
                except ValueError:
                    try:
                        processed.append(float(v))
                    except ValueError:
                        processed.append(v)

        placeholders = ",".join(["?" for _ in processed])
        cursor.execute(f"INSERT OR IGNORE INTO players VALUES ({placeholders})", processed)

    conn.commit()
    print(f"Imported {len(rows)} players successfully")


def initialize_database(conn):
    conn.executescript(SCHEMAS)
    import_players(conn)


def main():
    if os.path.exists(DB_PATH):
        if "--force" not in sys.argv:
            print(f"Database already exists at {DB_PATH}")
            print("Use --force to recreate")
            return
        os.remove(DB_PATH)

    print(f"Creating database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    initialize_database(conn)
    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
