#!/usr/bin/env python3
"""Generate database/players.sql from an FC/Sofifa CSV export."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("/Users/bytedance/Downloads/FC26_20250921.csv")
DEFAULT_OUTPUT = ROOT / "database" / "players_26.sql"

POSITION_COLUMNS = [
    "ls",
    "st",
    "rs",
    "lw",
    "lf",
    "cf",
    "rf",
    "rw",
    "lam",
    "cam",
    "ram",
    "lm",
    "lcm",
    "cm",
    "rcm",
    "rm",
    "lwb",
    "ldm",
    "cdm",
    "rdm",
    "rwb",
    "lb",
    "lcb",
    "cb",
    "rcb",
    "rb",
    "gk",
]

ABILITY_COLUMNS = [
    "attacking_crossing",
    "attacking_finishing",
    "attacking_heading_accuracy",
    "attacking_short_passing",
    "attacking_volleys",
    "skill_dribbling",
    "skill_curve",
    "skill_fk_accuracy",
    "skill_long_passing",
    "skill_ball_control",
    "movement_acceleration",
    "movement_sprint_speed",
    "movement_agility",
    "movement_reactions",
    "movement_balance",
    "power_shot_power",
    "power_jumping",
    "power_stamina",
    "power_strength",
    "power_long_shots",
    "mentality_aggression",
    "mentality_interceptions",
    "mentality_positioning",
    "mentality_vision",
    "mentality_penalties",
    "mentality_composure",
    "defending_marking_awareness",
    "defending_standing_tackle",
    "defending_sliding_tackle",
    "goalkeeping_diving",
    "goalkeeping_handling",
    "goalkeeping_kicking",
    "goalkeeping_positioning",
    "goalkeeping_reflexes",
]


def text(row: dict[str, str], key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def integer(row: dict[str, str], key: str) -> int | None:
    value = text(row, key)
    if value is None:
        return None
    return int(float(value))


def club_logo(row: dict[str, str]) -> str | None:
    team_id = text(row, "club_team_id")
    if team_id is None:
        return None
    return f"https://cdn.sofifa.net/teams/{team_id}/60.png"


def player_row(primary_id: int, row: dict[str, str]) -> list[Any]:
    return [
        primary_id,
        integer(row, "player_id"),
        text(row, "short_name"),
        integer(row, "age"),
        text(row, "player_face_url"),
        text(row, "nationality_name"),
        None,
        integer(row, "overall"),
        integer(row, "potential"),
        text(row, "club_name"),
        club_logo(row),
        text(row, "value_eur"),
        text(row, "wage_eur"),
        None,
        text(row, "preferred_foot"),
        text(row, "weak_foot"),
        text(row, "skill_moves"),
        text(row, "international_reputation"),
        text(row, "work_rate"),
        text(row, "body_type"),
        text(row, "real_face"),
        text(row, "release_clause_eur"),
        text(row, "player_positions"),
        integer(row, "club_jersey_number"),
        text(row, "height_cm"),
        text(row, "weight_kg"),
        *[text(row, column) for column in POSITION_COLUMNS],
        None,
        None,
        None,
        *[integer(row, column) for column in ABILITY_COLUMNS],
    ]


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def row_sql(values: list[Any]) -> str:
    return "(" + ",".join(sql_value(value) for value in values) + ")"


def generate(input_path: Path, output_path: Path, min_overall: int) -> int:
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if integer(row, "overall") is not None and integer(row, "overall") >= min_overall
        ]

    rows.sort(key=lambda row: (-integer(row, "overall"), text(row, "short_name") or ""))
    sql_rows = [row_sql(player_row(index + 1, row)) for index, row in enumerate(rows)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(
            [
                "-- Generated from FC/Sofifa CSV. Do not edit player rows manually.",
                f"-- Source: {input_path}",
                f"-- Filter: overall >= {min_overall}",
                "",
                "DROP TABLE IF EXISTS `players`;",
                "CREATE TABLE `players` (",
                "  `PrimaryID` smallint(6) NOT NULL,",
                "  `ID` int(11) DEFAULT NULL,",
                "  `Name` varchar(50) DEFAULT NULL,",
                "  `Age` int(11) DEFAULT NULL,",
                "  `Photo` varchar(255) DEFAULT NULL,",
                "  `Nationality` varchar(50) DEFAULT NULL,",
                "  `Flag` varchar(255) DEFAULT NULL,",
                "  `Overall` int(11) DEFAULT NULL,",
                "  `Potential` int(11) DEFAULT NULL,",
                "  `Club` varchar(80) DEFAULT NULL,",
                "  `Club_Logo` varchar(255) DEFAULT NULL,",
                "  `Value` varchar(50) DEFAULT NULL,",
                "  `Wage` varchar(50) DEFAULT NULL,",
                "  `Special` int(11) DEFAULT NULL,",
                "  `Preferred_Foot` varchar(50) DEFAULT NULL,",
                "  `Weak_Foot` varchar(50) DEFAULT NULL,",
                "  `Skill_Moves` varchar(50) DEFAULT NULL,",
                "  `International_Reputation` varchar(50) DEFAULT NULL,",
                "  `Work_Rate` varchar(50) DEFAULT NULL,",
                "  `Body_Type` varchar(50) DEFAULT NULL,",
                "  `Real_Face` varchar(50) DEFAULT NULL,",
                "  `Release_Clause` varchar(50) DEFAULT NULL,",
                "  `Position` varchar(50) DEFAULT NULL,",
                "  `Jersey_Number` int(11) DEFAULT NULL,",
                "  `Height` varchar(50) DEFAULT NULL,",
                "  `Weight` varchar(50) DEFAULT NULL,",
                "  `LS` varchar(50) DEFAULT NULL,",
                "  `ST` varchar(50) DEFAULT NULL,",
                "  `RS` varchar(50) DEFAULT NULL,",
                "  `LW` varchar(50) DEFAULT NULL,",
                "  `LF` varchar(50) DEFAULT NULL,",
                "  `CF` varchar(50) DEFAULT NULL,",
                "  `RF` varchar(50) DEFAULT NULL,",
                "  `RW` varchar(50) DEFAULT NULL,",
                "  `LAM` varchar(50) DEFAULT NULL,",
                "  `CAM` varchar(50) DEFAULT NULL,",
                "  `RAM` varchar(50) DEFAULT NULL,",
                "  `LM` varchar(50) DEFAULT NULL,",
                "  `LCM` varchar(50) DEFAULT NULL,",
                "  `CM` varchar(50) DEFAULT NULL,",
                "  `RCM` varchar(50) DEFAULT NULL,",
                "  `RM` varchar(50) DEFAULT NULL,",
                "  `LWB` varchar(50) DEFAULT NULL,",
                "  `LDM` varchar(50) DEFAULT NULL,",
                "  `CDM` varchar(50) DEFAULT NULL,",
                "  `RDM` varchar(50) DEFAULT NULL,",
                "  `RWB` varchar(50) DEFAULT NULL,",
                "  `LB` varchar(50) DEFAULT NULL,",
                "  `LCB` varchar(50) DEFAULT NULL,",
                "  `CB` varchar(50) DEFAULT NULL,",
                "  `RCB` varchar(50) DEFAULT NULL,",
                "  `RB` varchar(50) DEFAULT NULL,",
                "  `GK` varchar(50) DEFAULT NULL,",
                "  `Likes` int(11) DEFAULT NULL,",
                "  `Dislikes` int(11) DEFAULT NULL,",
                "  `Following` int(11) DEFAULT NULL,",
                "  `Crossing` int(11) DEFAULT NULL,",
                "  `Finishing` int(11) DEFAULT NULL,",
                "  `Heading_Accuracy` int(11) DEFAULT NULL,",
                "  `Short_Passing` int(11) DEFAULT NULL,",
                "  `Volleys` int(11) DEFAULT NULL,",
                "  `Dribbling` int(11) DEFAULT NULL,",
                "  `Curve` int(11) DEFAULT NULL,",
                "  `FK_Accuracy` int(11) DEFAULT NULL,",
                "  `Long_Passing` int(11) DEFAULT NULL,",
                "  `Ball_Control` int(11) DEFAULT NULL,",
                "  `Acceleration` int(11) DEFAULT NULL,",
                "  `Sprint_Speed` int(11) DEFAULT NULL,",
                "  `Agility` int(11) DEFAULT NULL,",
                "  `Reactions` int(11) DEFAULT NULL,",
                "  `Balance` int(11) DEFAULT NULL,",
                "  `Shot_Power` int(11) DEFAULT NULL,",
                "  `Jumping` int(11) DEFAULT NULL,",
                "  `Stamina` int(11) DEFAULT NULL,",
                "  `Strength` int(11) DEFAULT NULL,",
                "  `Long_Shots` int(11) DEFAULT NULL,",
                "  `Aggression` int(11) DEFAULT NULL,",
                "  `Interceptions` int(11) DEFAULT NULL,",
                "  `Positioning` int(11) DEFAULT NULL,",
                "  `Vision` int(11) DEFAULT NULL,",
                "  `Penalties` int(11) DEFAULT NULL,",
                "  `Composure` int(11) DEFAULT NULL,",
                "  `Defensive_Awareness` int(11) DEFAULT NULL,",
                "  `Standing_Tackle` int(11) DEFAULT NULL,",
                "  `Sliding_Tackle` int(11) DEFAULT NULL,",
                "  `GK_Diving` int(11) DEFAULT NULL,",
                "  `GK_Handling` int(11) DEFAULT NULL,",
                "  `GK_Kicking` int(11) DEFAULT NULL,",
                "  `GK_Positioning` int(11) DEFAULT NULL,",
                "  `GK_Reflexes` int(11) DEFAULT NULL,",
                "  PRIMARY KEY (`PrimaryID`)",
                ");",
                "",
                "INSERT INTO `players` VALUES",
                ",\n".join(sql_rows) + ";",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-overall", type=int, default=80)
    args = parser.parse_args()

    count = generate(args.input, args.output, args.min_overall)
    print(f"Wrote {count} players to {args.output}")


if __name__ == "__main__":
    main()
