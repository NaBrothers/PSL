#!/usr/bin/env python3
"""Micro-structure diagnostics for PSL engine_v2.

This script complements the macro benchmark by aggregating per-player behavior
by role group. It is intentionally read-only and deterministic for a given seed.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.card import compute_abilities, compute_real_overall
from psl_core.constants import FORMATION, GOALKEEPER, NPC, NPC_STYLE, POSITION_MAP
from scripts.benchmark_engine_v2 import ABILITY_KEYS, POSITIONS_BY_FORMATION, generate_random_team


ROLE_GROUPS = {
    "GK": {"GK"},
    "CB": {"CB", "LCB", "RCB"},
    "FB": {"LB", "RB", "LWB", "RWB"},
    "DM": {"CDM", "LDM", "RDM"},
    "CM": {"CM", "LCM", "RCM"},
    "WM": {"LM", "RM"},
    "AM": {"CAM", "LAM", "RAM"},
    "W": {"LW", "RW", "LF", "RF"},
    "FW": {"ST", "CF", "LS", "RS"},
}


PASS_ACTIONS = {"pass", "short_pass", "long_pass", "pass_to_space"}


METRICS = [
    "shots",
    "xg",
    "passes",
    "completed_passes",
    "key_passes",
    "passes_into_box",
    "crosses",
    "carries",
    "carries_into_box",
    "take_ons",
    "tackles_attempted",
    "tackles_won",
    "interceptions",
    "pressures",
    "successful_pressures",
]


def _progress(x: float, attacking_right: bool, pitch_length: float) -> float:
    return x / pitch_length if attacking_right else (pitch_length - x) / pitch_length


def _attacking_right_for_frame(side: str, half: int) -> bool:
    first_half_home_right = side == "home"
    return first_half_home_right if half == 1 else not first_half_home_right


def _xy_from_frame_coord(coord):
    y, x = coord
    return (x, y)


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def role_group(position: str) -> str:
    for group, positions in ROLE_GROUPS.items():
        if position in positions:
            return group
    return "OTHER"


def target_zone(progress: float, width: float) -> str:
    if progress >= 0.84 and width <= 0.34:
        return "box_center"
    if progress >= 0.84:
        return "box_wide"
    if 0.70 <= progress < 0.84 and width <= 0.34:
        return "arc_center"
    if 0.70 <= progress < 0.84:
        return "final_wide"
    if progress >= 0.58 and width <= 0.34:
        return "middle_center"
    if progress >= 0.58:
        return "middle_wide"
    return "recycle"


def formation_positions(formation: str) -> list[str]:
    if formation in FORMATION:
        return FORMATION[formation]["positions"]
    return POSITIONS_BY_FORMATION[formation]


def first_position(position: str) -> str:
    return (position or "").split(",")[0].strip()


def all_positions(position: str) -> list[str]:
    return [p.strip() for p in (position or "").split(",") if p.strip()]


def _parse_int(value, default: int = 0) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return default


def build_db_squad(db_path: str, qq: int):
    from server.database import Database
    from server.services.bag import BagService
    from server.services.squad import SquadService

    db = Database(db_path)
    squad = SquadService(db).get_squad(qq)
    bag = BagService(db)
    cards = []
    for card_info in squad.cards:
        detail = bag.get_card_detail(card_info.id, qq)
        abilities = {key: value["value"] for key, value in detail["abilities"].items()}
        cards.append({
            "name": card_info.name,
            "player_id": card_info.player_id,
            "position": card_info.position,
            "color": "gold" if card_info.star >= 7 else "silver" if card_info.star >= 4 else "bronze",
            "overall": card_info.real_overall,
            "abilities": abilities,
        })
    return squad.formation, cards


PLAYER_COLUMNS = [
    "PrimaryID", "ID", "Name", "Position", "Overall", "Height",
    "Heading_Accuracy", "Jumping", "Strength", "Long_Shots", "Shot_Power",
    "Finishing", "Long_Passing", "Short_Passing", "Dribbling", "Ball_Control",
    "Balance", "Sliding_Tackle", "Standing_Tackle", "Defensive_Awareness",
    "Aggression", "Interceptions", "Sprint_Speed", "Acceleration",
    "Composure", "GK_Handling", "GK_Diving", "GK_Positioning",
    "GK_Reflexes", "Reactions",
]


def load_real_player_pool(db_path: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            f"SELECT {', '.join(PLAYER_COLUMNS)} FROM players WHERE Overall >= 80"
        ).fetchall()
    finally:
        conn.close()


def load_real_players_by_ids(db_path: str, player_ids: list[int]) -> dict[int, sqlite3.Row]:
    if not player_ids:
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ", ".join("?" for _ in player_ids)
        rows = conn.execute(
            f"SELECT {', '.join(PLAYER_COLUMNS)} FROM players WHERE ID IN ({placeholders})",
            player_ids,
        ).fetchall()
        return {int(row["ID"] or row["PrimaryID"]): row for row in rows}
    finally:
        conn.close()


def _position_candidates(pool: list[sqlite3.Row], slot: str, used_ids: set[int]) -> list[tuple[sqlite3.Row, float]]:
    slot_group = role_group(slot)
    slot_mapped = POSITION_MAP.get(slot, slot)
    exact = []
    compatible = []
    fallback = []

    for row in pool:
        player_id = int(row["ID"] or row["PrimaryID"])
        if player_id in used_ids:
            continue
        positions = all_positions(row["Position"])
        primary = positions[0] if positions else ""
        mapped_positions = {POSITION_MAP.get(pos, pos) for pos in positions}
        groups = {role_group(pos) for pos in positions}

        if slot in positions:
            fit = 10.0 if primary == slot else 7.0
            exact.append((row, fit))
        elif slot_mapped in mapped_positions:
            fit = 5.0 if POSITION_MAP.get(primary, primary) == slot_mapped else 3.5
            compatible.append((row, fit))
        elif slot_group in groups:
            compatible.append((row, 1.5))
        else:
            fallback.append((row, -12.0))

    return exact or compatible or fallback


def _profile_score(abilities: dict[str, int], slot: str, profile: str) -> float:
    group = role_group(slot)
    if profile == "attack":
        if group in ("FW", "W"):
            return (
                abilities.get("Finishing", 0) * 0.34
                + abilities.get("Dribbling", 0) * 0.25
                + abilities.get("Speed", 0) * 0.18
                + abilities.get("Short_Passing", 0) * 0.12
                + abilities.get("Long_Shot", 0) * 0.11
            )
        if group in ("AM", "WM", "CM"):
            return (
                abilities.get("Short_Passing", 0) * 0.27
                + abilities.get("Long_Passing", 0) * 0.22
                + abilities.get("Dribbling", 0) * 0.22
                + abilities.get("IQ", 0) * 0.15
                + abilities.get("Speed", 0) * 0.14
            )
        return (
            abilities.get("Short_Passing", 0) * 0.28
            + abilities.get("Speed", 0) * 0.24
            + abilities.get("Defence", 0) * 0.22
            + abilities.get("Tackling", 0) * 0.16
            + abilities.get("IQ", 0) * 0.10
        )
    if profile == "defense":
        if group == "GK":
            return (
                abilities.get("GK_Saving", 0) * 0.36
                + abilities.get("GK_Positioning", 0) * 0.32
                + abilities.get("GK_Reaction", 0) * 0.32
            )
        if group in ("CB", "FB", "DM"):
            return (
                abilities.get("Defence", 0) * 0.35
                + abilities.get("Tackling", 0) * 0.28
                + abilities.get("Speed", 0) * 0.14
                + abilities.get("Heading", 0) * 0.13
                + abilities.get("IQ", 0) * 0.10
            )
        return (
            abilities.get("Defence", 0) * 0.24
            + abilities.get("Tackling", 0) * 0.20
            + abilities.get("Short_Passing", 0) * 0.18
            + abilities.get("Speed", 0) * 0.16
            + abilities.get("IQ", 0) * 0.12
            + abilities.get("Dribbling", 0) * 0.10
        )
    return compute_real_overall(abilities, slot)


def _row_to_engine_card(row: sqlite3.Row, slot: str, star: int, profile: str) -> dict:
    player_id = int(row["ID"] or row["PrimaryID"])
    style = NPC_STYLE.get(slot, "gloves" if slot in GOALKEEPER else "artist")
    abilities = compute_abilities(
        star=star,
        style=style,
        position=slot,
        height=_parse_int(row["Height"], 180),
        heading_accuracy=row["Heading_Accuracy"] or 0,
        jumping=row["Jumping"] or 0,
        strength=row["Strength"] or 0,
        long_shots=row["Long_Shots"] or 0,
        shot_power=row["Shot_Power"] or 0,
        finishing=row["Finishing"] or 0,
        long_passing=row["Long_Passing"] or 0,
        short_passing=row["Short_Passing"] or 0,
        dribbling=row["Dribbling"] or 0,
        ball_control=row["Ball_Control"] or 0,
        balance=row["Balance"] or 0,
        sliding_tackle=row["Sliding_Tackle"] or 0,
        standing_tackle=row["Standing_Tackle"] or 0,
        defensive_awareness=row["Defensive_Awareness"] or 0,
        aggression=row["Aggression"] or 0,
        interceptions=row["Interceptions"] or 0,
        sprint_speed=row["Sprint_Speed"] or 0,
        acceleration=row["Acceleration"] or 0,
        composure=row["Composure"] or 0,
        gk_handling=row["GK_Handling"] or 0,
        gk_diving=row["GK_Diving"] or 0,
        gk_positioning=row["GK_Positioning"] or 0,
        gk_reflexes=row["GK_Reflexes"] or 0,
        reactions=row["Reactions"] or 0,
    )
    return {
        "name": str(row["Name"]),
        "player_id": player_id,
        "position": slot,
        "source_position": first_position(row["Position"]),
        "profile": profile,
        "color": "gold" if star >= 7 else "silver" if star >= 4 else "bronze",
        "overall": compute_real_overall(abilities, slot),
        "abilities": abilities,
    }


def build_real_squad(db_path: str, profile: str, formation: str, star: int):
    pool = load_real_player_pool(db_path)
    if not pool:
        raise RuntimeError(f"No real players found in {db_path}")

    profile = profile or "balanced"
    positions = formation_positions(formation)
    used_ids: set[int] = set()
    cards = []
    for slot in positions:
        best = None
        for row, fit_bonus in _position_candidates(pool, slot, used_ids):
            card = _row_to_engine_card(row, slot, star, profile)
            score = (
                card["overall"] * 0.70
                + _profile_score(card["abilities"], slot, profile) * 0.30
                + fit_bonus
            )
            if best is None or score > best[0]:
                best = (score, row, card)
        if best is None:
            raise RuntimeError(f"No candidate for slot {slot} in {formation}")
        used_ids.add(int(best[1]["ID"] or best[1]["PrimaryID"]))
        cards.append(best[2])
    return formation, cards


def build_npc_squad(db_path: str, npc_name: str, star: int):
    club = next((team for team in NPC if team["name"] == npc_name), None)
    if club is None:
        available = ", ".join(team["name"] for team in NPC)
        raise RuntimeError(f"Unknown NPC squad {npc_name}. Available: {available}")
    formation = club["formation"]
    positions = formation_positions(formation)
    player_ids = [int(player_id) for player_id in club["players"]]
    rows_by_id = load_real_players_by_ids(db_path, player_ids)
    missing = [player_id for player_id in player_ids if player_id not in rows_by_id]
    if missing:
        raise RuntimeError(f"Missing players for NPC squad {npc_name}: {missing}")
    cards = []
    for slot, player_id in zip(positions, player_ids):
        cards.append(_row_to_engine_card(rows_by_id[player_id], slot, star, "club"))
    return formation, cards


def build_template_squad(template: str, formation: str):
    positions = formation_positions(formation)
    cards = []
    for idx, pos in enumerate(positions):
        if pos == "GK":
            abilities = {key: 30 for key in ABILITY_KEYS}
            if template == "defense":
                abilities.update({"GK_Saving": 92, "GK_Positioning": 92, "GK_Reaction": 92, "Speed": 68, "IQ": 88})
                overall = 88
            else:
                abilities.update({"GK_Saving": 78, "GK_Positioning": 78, "GK_Reaction": 78, "Speed": 72, "IQ": 78})
                overall = 80
        else:
            abilities = {key: 68 for key in ABILITY_KEYS}
            if template == "attack":
                attacker_role = pos in {"ST", "CF", "LS", "RS", "LW", "RW", "LF", "RF", "CAM", "LAM", "RAM"}
                abilities.update({
                    "Finishing": 94 if attacker_role else 74,
                    "Long_Shot": 90 if attacker_role else 72,
                    "Dribbling": 94 if attacker_role else 78,
                    "Short_Passing": 88,
                    "Long_Passing": 84,
                    "Speed": 91 if attacker_role else 80,
                    "IQ": 88,
                    "Heading": 82,
                    "Tackling": 58,
                    "Defence": 58,
                })
                overall = 88
            elif template == "defense":
                defender_role = pos in {"CB", "LCB", "RCB", "LB", "RB", "LWB", "RWB", "CDM", "LDM", "RDM"}
                abilities.update({
                    "Finishing": 42 if not defender_role else 52,
                    "Long_Shot": 42 if not defender_role else 52,
                    "Dribbling": 58 if not defender_role else 66,
                    "Short_Passing": 64 if not defender_role else 72,
                    "Long_Passing": 58 if not defender_role else 70,
                    "Speed": 80 if not defender_role else 86,
                    "IQ": 88,
                    "Heading": 86,
                    "Tackling": 92,
                    "Defence": 94,
                })
                overall = 86
            else:
                overall = 72
        cards.append({
            "name": f"{template.title()} {idx} {pos}",
            "player_id": 900000 + idx,
            "position": pos,
            "color": "gold",
            "overall": overall,
            "abilities": abilities,
        })
    return formation, cards


def run(
    matches: int,
    home_star: int,
    away_star: int,
    seed: int,
    ticks: int,
    db_path: str = "",
    home_qq: int = 0,
    away_qq: int = 0,
    home_template: str = "",
    away_template: str = "",
    home_formation: str = "",
    away_formation: str = "",
    home_real_profile: str = "",
    away_real_profile: str = "",
    home_npc: str = "",
    away_npc: str = "",
    trace_detail: str = "",
    trace_top_k: int = 5,
    trace_sample_rate: int = 1,
    trace_include_defense: bool = False,
    goal_continuity: bool = True,
):
    rng = random.Random(seed)
    aggregate = defaultdict(Counter)
    side_aggregate = defaultdict(Counter)
    players = defaultdict(Counter)
    totals = Counter()

    for i in range(matches):
        if db_path and home_qq and away_qq:
            home_formation, home_cards = build_db_squad(db_path, home_qq)
            away_formation, away_cards = build_db_squad(db_path, away_qq)
        elif home_npc and away_npc:
            real_db_path = db_path or "psl.db"
            home_formation, home_cards = build_npc_squad(real_db_path, home_npc, home_star)
            away_formation, away_cards = build_npc_squad(real_db_path, away_npc, away_star)
        elif home_real_profile and away_real_profile and home_formation and away_formation:
            real_db_path = db_path or "psl.db"
            home_formation, home_cards = build_real_squad(
                real_db_path, home_real_profile, home_formation, home_star
            )
            away_formation, away_cards = build_real_squad(
                real_db_path, away_real_profile, away_formation, away_star
            )
        elif home_template and away_template and home_formation and away_formation:
            home_formation, home_cards = build_template_squad(home_template, home_formation)
            away_formation, away_cards = build_template_squad(away_template, away_formation)
        else:
            home_cards, home_formation = generate_random_team(home_star, rng)
            away_cards, away_formation = generate_random_team(away_star, rng)
        config = EngineConfig()
        config.goal_continuity_enabled = goal_continuity
        if ticks > 0:
            config.total_ticks = ticks
            config.half_ticks = ticks // 2
            config.frame_interval = max(1, ticks // 90)
        if trace_detail:
            config.trace.detail = trace_detail
            config.trace.top_k = trace_top_k
            config.trace.sample_rate = trace_sample_rate
            config.trace.include_defense = trace_include_defense
            if goal_continuity:
                config.trace.include_off_ball = True
        elif goal_continuity:
            config.trace.detail = "chosen"
            config.trace.sample_rate = trace_sample_rate
            config.trace.include_off_ball = True
            config.trace.include_defense = trace_include_defense
        random.seed(seed + i * 9973)
        match = MatchV2(home_cards, away_cards, home_formation, away_formation, config=config)
        result = match.run()
        replay = match.get_replay_data()
        trace = match.get_trace()
        header = replay[0] if replay else {}
        home_players = header.get("home", {}).get("players", [])
        away_players = header.get("away", {}).get("players", [])
        pitch_length = header.get("field", {}).get("length", match.config.pitch_length)
        pitch_width = header.get("field", {}).get("width", match.config.pitch_width)
        frames_by_tick = {
            int(round(frame.get("t", 0) / max(match.config.tick_duration, 1e-6))): frame
            for frame in replay[1:]
            if frame.get("type") == "frame"
        }
        frame_ticks = sorted(frames_by_tick)

        totals["matches"] += 1
        totals["simulated_ticks"] += config.total_ticks
        totals["tick_duration"] = config.tick_duration
        totals["goals"] += result.home_score + result.away_score
        totals["shots"] += result.home_stats.get("shots", 0) + result.away_stats.get("shots", 0)
        totals["sot"] += result.home_stats.get("shots_on_target", 0) + result.away_stats.get("shots_on_target", 0)
        totals["passes"] += result.home_stats.get("passes", 0) + result.away_stats.get("passes", 0)
        totals["completed_passes"] += result.home_stats.get("passes_completed", 0) + result.away_stats.get("passes_completed", 0)
        totals["home_goals"] += result.home_score
        totals["away_goals"] += result.away_score
        totals["home_shots"] += result.home_stats.get("shots", 0)
        totals["away_shots"] += result.away_stats.get("shots", 0)
        totals["home_sot"] += result.home_stats.get("shots_on_target", 0)
        totals["away_sot"] += result.away_stats.get("shots_on_target", 0)

        for side, player_list in (("home", result.home_player_stats), ("away", result.away_player_stats)):
            for player in player_list:
                group = role_group(player.get("position", ""))
                side_key = f"{side}:{group}"
                side_aggregate[side_key]["players"] += 1
                for metric in METRICS:
                    side_aggregate[side_key][metric] += player.get(metric, 0)

        for player in result.home_player_stats + result.away_player_stats:
            group = role_group(player.get("position", ""))
            aggregate[group]["players"] += 1
            player_key = f"{player.get('position', '')}:{player.get('name', '')}"
            players[player_key]["appearances"] += 1
            for metric in METRICS:
                aggregate[group][metric] += player.get(metric, 0)
                players[player_key][metric] += player.get(metric, 0)
            if player in result.home_player_stats:
                totals["home_xg"] += player.get("xg", 0)
            else:
                totals["away_xg"] += player.get("xg", 0)
            for shot in player.get("shot_log", []):
                area = "box" if shot.get("in_box") else "out"
                aggregate[group][f"{area}_shots"] += 1
                aggregate[group][f"{area}_xg"] += shot.get("xg", 0.0)
                if shot.get("outcome") in ("goal", "saved"):
                    aggregate[group][f"{area}_sot"] += 1
                if shot.get("outcome") == "goal":
                    aggregate[group][f"{area}_goals"] += 1
                totals[f"{area}_shots"] += 1
                totals[f"{area}_xg"] += shot.get("xg", 0.0)
                if shot.get("outcome") in ("goal", "saved"):
                    totals[f"{area}_sot"] += 1
                if shot.get("outcome") == "goal":
                    totals[f"{area}_goals"] += 1

        arc_state_sequence = []
        for frame in replay[1:]:
            if frame.get("type") != "frame":
                continue
            half = int(frame.get("half", 1) or 1)
            ball_team = frame.get("ball_team")
            if ball_team not in ("home", "away"):
                continue
            ball = frame.get("ball")
            ball_x = ball[1] if ball else None
            holder_idx = frame.get("ball_holder")
            if holder_idx is not None:
                holder_meta = (home_players if ball_team == "home" else away_players)
                holder_attacking_right = _attacking_right_for_frame(ball_team, half)
                if 0 <= holder_idx < len(holder_meta):
                    group = role_group(holder_meta[holder_idx].get("pos", ""))
                    aggregate[group]["touch_frames"] += 1
                    players[f"{holder_meta[holder_idx].get('pos', '')}:{holder_meta[holder_idx].get('name', '')}"]["touch_frames"] += 1
                    if ball_x is not None:
                        holder_ball_progress = _progress(ball_x, holder_attacking_right, pitch_length)
                        aggregate[group]["touch_progress_sum"] += holder_ball_progress
                        players[f"{holder_meta[holder_idx].get('pos', '')}:{holder_meta[holder_idx].get('name', '')}"]["touch_progress_sum"] += holder_ball_progress
                        if ball:
                            aggregate[group]["touch_width_sum"] += abs(ball[0] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                            players[f"{holder_meta[holder_idx].get('pos', '')}:{holder_meta[holder_idx].get('name', '')}"]["touch_width_sum"] += abs(ball[0] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                        if holder_ball_progress > 0.67:
                            aggregate[group]["final_third_touch_frames"] += 1
                            players[f"{holder_meta[holder_idx].get('pos', '')}:{holder_meta[holder_idx].get('name', '')}"]["final_third_touch_frames"] += 1
                            aggregate[group]["final_third_touch_progress_sum"] += holder_ball_progress
                            players[f"{holder_meta[holder_idx].get('pos', '')}:{holder_meta[holder_idx].get('name', '')}"]["final_third_touch_progress_sum"] += holder_ball_progress
                            if ball:
                                aggregate[group]["final_third_touch_width_sum"] += abs(ball[0] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                                players[f"{holder_meta[holder_idx].get('pos', '')}:{holder_meta[holder_idx].get('name', '')}"]["final_third_touch_width_sum"] += abs(ball[0] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                                wide_attack_window = (
                                    holder_ball_progress > 0.72
                                    and abs(ball[0] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0) > 0.24
                                )
                                nearest_second_line_for_arc = None
                                if wide_attack_window:
                                    arc_x = pitch_length * 0.80 if holder_attacking_right else pitch_length * 0.20
                                    arc_pos = (arc_x, pitch_width / 2.0)
                                    arc_band = (
                                        arc_pos,
                                        (arc_x, pitch_width / 2.0 - pitch_width * 0.10),
                                        (arc_x, pitch_width / 2.0 + pitch_width * 0.10),
                                    )
                                    attacking_side = ball_team
                                    attacking_meta = home_players if attacking_side == "home" else away_players
                                    attacking_coords = frame.get(attacking_side, [])
                                    attacking_targets = frame.get(f"{attacking_side}_targets", [])
                                    attacking_anchors = frame.get(f"{attacking_side}_anchors", [])
                                    nearest_second_line = None
                                    nearest_second_line_band = None
                                    nearest_second_line_target = None
                                    nearest_second_line_anchor = None
                                    for idx, coord in enumerate(attacking_coords):
                                        if idx >= len(attacking_meta):
                                            continue
                                        support_group = role_group(attacking_meta[idx].get("pos", ""))
                                        if support_group not in ("CM", "WM", "AM"):
                                            continue
                                        support_pos = _xy_from_frame_coord(coord)
                                        d = _dist(arc_pos, support_pos)
                                        band_d = min(_dist(point, support_pos) for point in arc_band)
                                        nearest_second_line = d if nearest_second_line is None else min(nearest_second_line, d)
                                        nearest_second_line_band = band_d if nearest_second_line_band is None else min(nearest_second_line_band, band_d)
                                        if idx < len(attacking_targets):
                                            target_d = _dist(arc_pos, _xy_from_frame_coord(attacking_targets[idx]))
                                            nearest_second_line_target = target_d if nearest_second_line_target is None else min(nearest_second_line_target, target_d)
                                        if idx < len(attacking_anchors):
                                            anchor_d = _dist(arc_pos, _xy_from_frame_coord(attacking_anchors[idx]))
                                            nearest_second_line_anchor = anchor_d if nearest_second_line_anchor is None else min(nearest_second_line_anchor, anchor_d)
                                    if nearest_second_line is not None:
                                        nearest_second_line_for_arc = nearest_second_line
                                        totals["arc_second_line_dist_sum"] += nearest_second_line
                                        totals["arc_second_line_band_dist_sum"] += nearest_second_line_band or nearest_second_line
                                        totals["arc_window_samples"] += 1
                                        if nearest_second_line < 10.0:
                                            totals["arc_second_line_close10"] += 1
                                        if nearest_second_line_band is not None and nearest_second_line_band < 10.0:
                                            totals["arc_second_line_band_close10"] += 1
                                    if nearest_second_line_target is not None:
                                        totals["arc_second_line_target_dist_sum"] += nearest_second_line_target
                                        totals["arc_second_line_target_samples"] += 1
                                        if nearest_second_line_target < 10.0:
                                            totals["arc_second_line_target_close10"] += 1
                                    if nearest_second_line_anchor is not None:
                                        totals["arc_second_line_anchor_dist_sum"] += nearest_second_line_anchor
                                        totals["arc_second_line_anchor_samples"] += 1
                                        if nearest_second_line_anchor < 10.0:
                                            totals["arc_second_line_anchor_close10"] += 1
                                defending_side = "away" if ball_team == "home" else "home"
                                defending_meta = away_players if ball_team == "home" else home_players
                                defending_coords = frame.get(defending_side, [])
                                nearest_def = None
                                close6 = 0
                                close8 = 0
                                for idx, coord in enumerate(defending_coords):
                                    if idx >= len(defending_meta):
                                        continue
                                    if role_group(defending_meta[idx].get("pos", "")) == "GK":
                                        continue
                                    d = _dist((ball_x, ball[0]), _xy_from_frame_coord(coord))
                                    nearest_def = d if nearest_def is None else min(nearest_def, d)
                                    if d < 6.0:
                                        close6 += 1
                                    if d < 8.0:
                                        close8 += 1
                                if nearest_def is not None:
                                    aggregate[group]["ft_nearest_def_dist_sum"] += nearest_def
                                    aggregate[group]["ft_nearest_def_samples"] += 1
                                    aggregate[group]["ft_close6_def_sum"] += close6
                                    aggregate[group]["ft_close8_def_sum"] += close8
                                    totals["ft_nearest_def_dist_sum"] += nearest_def
                                    totals["ft_nearest_def_samples"] += 1
                                    totals["ft_close6_def_sum"] += close6
                                    totals["ft_close8_def_sum"] += close8
                                    if wide_attack_window:
                                        arc_x = pitch_length * 0.80 if holder_attacking_right else pitch_length * 0.20
                                        arc_pos = (arc_x, pitch_width / 2.0)
                                        nearest_arc_def = None
                                        nearest_arc_def_group = ""
                                        for idx, coord in enumerate(defending_coords):
                                            if idx >= len(defending_meta):
                                                continue
                                            defender_group = role_group(defending_meta[idx].get("pos", ""))
                                            if defender_group == "GK":
                                                continue
                                            d = _dist(arc_pos, _xy_from_frame_coord(coord))
                                            if nearest_arc_def is None or d < nearest_arc_def:
                                                nearest_arc_def = d
                                                nearest_arc_def_group = defender_group
                                        if nearest_arc_def is not None:
                                            totals["arc_def_samples"] += 1
                                            totals["arc_def_dist_sum"] += nearest_arc_def
                                            totals[f"arc_def_role_{nearest_arc_def_group}"] += 1
                                            if nearest_arc_def > 6.0:
                                                totals["arc_low_pressure"] += 1
                                            if (
                                                nearest_second_line_for_arc is not None
                                                and nearest_second_line_for_arc < 10.0
                                                and nearest_arc_def > 6.0
                                            ):
                                                totals["arc_ready_window"] += 1
                                            if (
                                                nearest_second_line_band is not None
                                                and nearest_second_line_band < 10.0
                                                and nearest_arc_def > 6.0
                                            ):
                                                totals["arc_band_ready_window"] += 1
                                            if nearest_second_line_for_arc is not None:
                                                has_second_line = nearest_second_line_for_arc < 10.0
                                                has_low_pressure = nearest_arc_def > 6.0
                                                if has_second_line and has_low_pressure:
                                                    arc_state_sequence.append("ready")
                                                elif has_second_line:
                                                    arc_state_sequence.append("only2l")
                                                elif has_low_pressure:
                                                    arc_state_sequence.append("onlyp")
                                                else:
                                                    arc_state_sequence.append("none")
                                                if has_second_line and not has_low_pressure:
                                                    totals["arc_only_second_line"] += 1
                                                elif has_low_pressure and not has_second_line:
                                                    totals["arc_only_low_pressure"] += 1
                                                elif not has_second_line and not has_low_pressure:
                                                    totals["arc_neither_ready_part"] += 1
            for side, players_meta, coords, attacking_right in (
                ("home", home_players, frame.get("home", []), _attacking_right_for_frame("home", half)),
                ("away", away_players, frame.get("away", []), _attacking_right_for_frame("away", half)),
            ):
                phase = "atk" if side == ball_team else "def"
                ball_progress = _progress(ball_x, attacking_right, pitch_length) if ball_x is not None else 0.0
                if phase == "atk" and ball_progress > 0.67:
                    targets = frame.get(f"{side}_targets", [])
                    anchors = frame.get(f"{side}_anchors", [])
                    defending_side = "away" if side == "home" else "home"
                    defending_meta = away_players if side == "home" else home_players
                    defending_coords = frame.get(defending_side, [])
                    front_progress = None
                    for didx, dcoord in enumerate(defending_coords):
                        if didx >= len(defending_meta):
                            continue
                        if role_group(defending_meta[didx].get("pos", "")) == "GK":
                            continue
                        dpos = _xy_from_frame_coord(dcoord)
                        dprog = _progress(dpos[0], attacking_right, pitch_length)
                        front_progress = dprog if front_progress is None else min(front_progress, dprog)
                    cover_actual = []
                    cover_target = []
                    cover_anchor = []
                    for cidx, ccoord in enumerate(coords):
                        if cidx >= len(players_meta):
                            continue
                        if role_group(players_meta[cidx].get("pos", "")) == "GK":
                            continue
                        # Use base formation depth from replay order metadata is
                        # unavailable here, so infer rest-defense candidates by
                        # current role group rather than hard action rules.
                        if role_group(players_meta[cidx].get("pos", "")) not in ("CB", "FB", "DM"):
                            continue
                        cpos = _xy_from_frame_coord(ccoord)
                        cover_actual.append(_progress(cpos[0], attacking_right, pitch_length))
                        if cidx < len(targets):
                            tpos = _xy_from_frame_coord(targets[cidx])
                            cover_target.append(_progress(tpos[0], attacking_right, pitch_length))
                        if cidx < len(anchors):
                            apos = _xy_from_frame_coord(anchors[cidx])
                            cover_anchor.append(_progress(apos[0], attacking_right, pitch_length))
                    if cover_actual:
                        totals["rest_def_samples"] += 1
                        totals["rest_def_actual_sum"] += sum(cover_actual) / len(cover_actual)
                        totals["rest_def_actual_max_sum"] += max(cover_actual)
                        if cover_target:
                            totals["rest_def_target_sum"] += sum(cover_target) / len(cover_target)
                            totals["rest_def_target_max_sum"] += max(cover_target)
                        if cover_anchor:
                            totals["rest_def_anchor_sum"] += sum(cover_anchor) / len(cover_anchor)
                            totals["rest_def_anchor_max_sum"] += max(cover_anchor)
                        if front_progress is not None:
                            totals["rest_def_opp_front_sum"] += front_progress
                            totals["rest_def_opp_front_samples"] += 1
                final_third_phase = phase + "3" if ball_progress > 0.67 else ""
                for idx, coord in enumerate(coords):
                    if idx >= len(players_meta):
                        continue
                    pos = players_meta[idx].get("pos", "")
                    group = role_group(pos)
                    if group == "GK":
                        continue
                    y, x = coord
                    aggregate[group][f"{phase}_samples"] += 1
                    aggregate[group][f"{phase}_progress_sum"] += _progress(x, attacking_right, pitch_length)
                    aggregate[group][f"{phase}_width_sum"] += abs(y - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                    if final_third_phase:
                        aggregate[group][f"{final_third_phase}_samples"] += 1
                        aggregate[group][f"{final_third_phase}_progress_sum"] += _progress(x, attacking_right, pitch_length)
                        aggregate[group][f"{final_third_phase}_width_sum"] += abs(y - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)

        for idx, state in enumerate(arc_state_sequence):
            if state not in ("only2l", "onlyp"):
                continue
            lookahead = arc_state_sequence[idx + 1: idx + 4]
            totals[f"arc_{state}_follow_samples"] += 1
            if "ready" in lookahead:
                totals[f"arc_{state}_to_ready3"] += 1

        last_action_by_player = {}
        carry_chain_by_player = Counter()
        last_pass_context = {}
        pending_fw_after_wide = set()
        pending_layoff_receiver = set()
        layoff_receiver_observed = set()
        layoff_receive_ticks = {}
        pending_ft_carry = {}
        for entry in trace.get("entries", []):
            if entry.get("type") != "action":
                continue
            raw_action = entry.get("action")
            action = raw_action
            if raw_action == "pass":
                target_kind = entry.get("target_kind", "")
                pass_type = entry.get("pass_type", "short_pass")
                action = "pass_to_space" if target_kind == "space" else pass_type
            elif raw_action == "receive" and entry.get("receive_kind") == "space":
                action = "receive_space_pass"
            team_side = entry.get("team")
            player_name = entry.get("player")
            if team_side in ("home", "away") and player_name:
                player_meta_for_action = next(
                    (
                        p for p in (home_players if team_side == "home" else away_players)
                        if p.get("name") == player_name
                    ),
                    None,
                )
                if player_meta_for_action:
                    group_for_action = role_group(player_meta_for_action.get("pos", ""))
                    player_key_for_action = f"{player_meta_for_action.get('pos', '')}:{player_name}"
                    action_tick = entry.get("tick", 0)
                    action_half = 1 if action_tick < config.half_ticks else 2
                    action_attacking_right = _attacking_right_for_frame(team_side, action_half)
                    action_progress = None
                    if pos := entry.get("pos"):
                        action_progress = _progress(pos[0], action_attacking_right, pitch_length)
                    else:
                        frame_tick = max((tick for tick in frame_ticks if tick <= action_tick), default=None)
                        frame = frames_by_tick.get(frame_tick) if frame_tick is not None else None
                        if frame is not None and action_tick - frame_tick <= max(1, match.config.frame_interval):
                            ball = frame.get("ball")
                            if ball:
                                action_progress = _progress(ball[1], action_attacking_right, pitch_length)
                    if action_progress is not None and action_progress > 0.67:
                        action_key = f"final_third_action_{action or 'unknown'}"
                        aggregate[group_for_action][action_key] += 1
                        side_aggregate[f"{team_side}:{group_for_action}"][action_key] += 1
                        players[player_key_for_action][action_key] += 1
                        if action == "carry" and (target := entry.get("target")) and (pos := entry.get("pos")):
                            target_progress = _progress(float(target[0]), action_attacking_right, pitch_length)
                            actual_progress = _progress(float(pos[0]), action_attacking_right, pitch_length)
                            progress_gap = max(0.0, target_progress - actual_progress)
                            aggregate[group_for_action]["ft_carry_target_gap_sum"] += progress_gap
                            aggregate[group_for_action]["ft_carry_target_gap_samples"] += 1
                            aggregate[group_for_action]["ft_carry_target_progress_sum"] += target_progress
                            aggregate[group_for_action]["ft_carry_actual_progress_sum"] += actual_progress
                    carry_context = pending_ft_carry.get((team_side, player_name))
                    if (
                        carry_context
                        and action in ("carry", "short_pass", "long_pass", "pass_to_space", "hold", "shot")
                        and action_tick > carry_context["tick"]
                    ):
                        context_group = carry_context["group"]
                        next_key = f"ft_carry_next_{action}"
                        aggregate[context_group][next_key] += 1
                        if action == "shot":
                            aggregate[context_group]["ft_carry_next_shot_from_window"] += carry_context.get("shot_window", 0.0)
                        pending_ft_carry.pop((team_side, player_name), None)
                    if (team_side, player_name) in pending_layoff_receiver and action in ("carry", "short_pass", "long_pass", "pass_to_space", "hold", "shot"):
                        layoff_action_key = f"fw_layoff_next_{action}"
                        aggregate[group_for_action][layoff_action_key] += 1
                        side_aggregate[f"{team_side}:{group_for_action}"][layoff_action_key] += 1
                        players[player_key_for_action][layoff_action_key] += 1
                        if action != "shot":
                            pending_layoff_receiver.discard((team_side, player_name))
                    if action in ("short_pass", "long_pass", "pass_to_space"):
                        action_width = 0.0
                        frame_tick = max((tick for tick in frame_ticks if tick <= action_tick), default=None)
                        frame = frames_by_tick.get(frame_tick) if frame_tick is not None else None
                        if frame is not None and action_tick - frame_tick <= max(1, match.config.frame_interval):
                            ball_for_width = frame.get("ball")
                            if ball_for_width:
                                action_width = abs(ball_for_width[0] - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                        last_pass_context[team_side] = {
                            "passer": player_name,
                            "passer_group": group_for_action,
                            "progress": action_progress or 0.0,
                            "width": action_width,
                            "from_fw_after_wide": (team_side, player_name) in pending_fw_after_wide,
                        }
                    previous_chain = carry_chain_by_player.get((team_side, player_name), 0)
                    if previous_chain >= 3 and action != "carry":
                        chain_next_key = f"chain3_next_{action or 'unknown'}"
                        aggregate[group_for_action][chain_next_key] += 1
                        side_aggregate[f"{team_side}:{group_for_action}"][chain_next_key] += 1
                        players[player_key_for_action][chain_next_key] += 1
                    elif previous_chain >= 3 and action == "carry":
                        aggregate[group_for_action]["chain3_next_carry"] += 1
                        side_aggregate[f"{team_side}:{group_for_action}"]["chain3_next_carry"] += 1
                        players[player_key_for_action]["chain3_next_carry"] += 1
                    if action == "shot":
                        source = last_action_by_player.get((team_side, player_name), "other")
                        source_key = f"shot_after_{source}"
                        aggregate[group_for_action][source_key] += 1
                        side_aggregate[f"{team_side}:{group_for_action}"][source_key] += 1
                        players[player_key_for_action][source_key] += 1
                        shot_tick = entry.get("tick", 0)
                        frame_tick = max((tick for tick in frame_ticks if tick <= shot_tick), default=None)
                        frame = frames_by_tick.get(frame_tick) if frame_tick is not None else None
                        if frame is not None and shot_tick - frame_tick > max(1, match.config.frame_interval):
                            frame = None
                        if frame:
                            team_coords = frame.get(team_side, [])
                            team_meta = home_players if team_side == "home" else away_players
                            shooter_idx = next(
                                (idx for idx, meta in enumerate(team_meta) if meta.get("name") == player_name),
                                None,
                            )
                            if shooter_idx is not None and shooter_idx < len(team_coords):
                                shooter_pos = _xy_from_frame_coord(team_coords[shooter_idx])
                                support_distances = []
                                wide_support_distances = []
                                for idx, coord in enumerate(team_coords):
                                    if idx == shooter_idx or idx >= len(team_meta):
                                        continue
                                    support_group = role_group(team_meta[idx].get("pos", ""))
                                    if support_group in ("GK", "CB", "FB"):
                                        continue
                                    d = _dist(shooter_pos, _xy_from_frame_coord(coord))
                                    support_distances.append(d)
                                    if support_group in ("W", "WM", "CM", "AM"):
                                        wide_support_distances.append(d)
                                if support_distances:
                                    nearest_support = min(support_distances)
                                    aggregate[group_for_action]["shot_support_dist_sum"] += nearest_support
                                    aggregate[group_for_action]["shot_support_samples"] += 1
                                    side_aggregate[f"{team_side}:{group_for_action}"]["shot_support_dist_sum"] += nearest_support
                                    side_aggregate[f"{team_side}:{group_for_action}"]["shot_support_samples"] += 1
                                    players[player_key_for_action]["shot_support_dist_sum"] += nearest_support
                                    players[player_key_for_action]["shot_support_samples"] += 1
                                if wide_support_distances:
                                    nearest_wide_support = min(wide_support_distances)
                                    aggregate[group_for_action]["shot_wide_support_dist_sum"] += nearest_wide_support
                                    aggregate[group_for_action]["shot_wide_support_samples"] += 1
                                    side_aggregate[f"{team_side}:{group_for_action}"]["shot_wide_support_dist_sum"] += nearest_wide_support
                                    side_aggregate[f"{team_side}:{group_for_action}"]["shot_wide_support_samples"] += 1
                                    players[player_key_for_action]["shot_wide_support_dist_sum"] += nearest_wide_support
                                    players[player_key_for_action]["shot_wide_support_samples"] += 1
                        carry_chain = carry_chain_by_player.get((team_side, player_name), 0)
                        if source == "carry":
                            if carry_chain <= 1:
                                chain_key = "shot_after_carry_1"
                            elif carry_chain == 2:
                                chain_key = "shot_after_carry_2"
                            else:
                                chain_key = "shot_after_carry_3p"
                            aggregate[group_for_action][chain_key] += 1
                            side_aggregate[f"{team_side}:{group_for_action}"][chain_key] += 1
                            players[player_key_for_action][chain_key] += 1
                        if (team_side, player_name) in pending_layoff_receiver and group_for_action in ("CM", "WM", "AM"):
                            aggregate[group_for_action]["shot_after_fw_layoff_chain"] += 1
                            side_aggregate[f"{team_side}:{group_for_action}"]["shot_after_fw_layoff_chain"] += 1
                            players[player_key_for_action]["shot_after_fw_layoff_chain"] += 1
                            pending_layoff_receiver.discard((team_side, player_name))
                    if action:
                        last_action_by_player[(team_side, player_name)] = action
                        if action == "carry":
                            carry_chain_by_player[(team_side, player_name)] += 1
                            if (
                                action_progress is not None
                                and action_progress > 0.67
                                and group_for_action in ("WM", "CM", "AM", "W")
                            ):
                                pending_ft_carry[(team_side, player_name)] = {
                                    "tick": action_tick,
                                    "group": group_for_action,
                                    "shot_window": 0.0,
                                }
                        elif action != "shot":
                            carry_chain_by_player[(team_side, player_name)] = 0

            if action not in ("receive", "receive_space_pass"):
                continue
            pos = entry.get("pos")
            if not pos or team_side not in ("home", "away") or not player_name:
                continue
            players_meta = home_players if team_side == "home" else away_players
            player_meta = next((p for p in players_meta if p.get("name") == player_name), None)
            if not player_meta:
                continue
            group = role_group(player_meta.get("pos", ""))
            pass_context = last_pass_context.get(team_side, {})
            passer_group = pass_context.get("passer_group")
            if passer_group in ("W", "WM") and group == "FW" and pass_context.get("progress", 0.0) > 0.67 and pass_context.get("width", 0.0) > 0.24:
                aggregate["FW"]["wide_to_fw_receives"] += 1
                side_aggregate[f"{team_side}:FW"]["wide_to_fw_receives"] += 1
                players[f"{player_meta.get('pos', '')}:{player_name}"]["wide_to_fw_receives"] += 1
                pending_fw_after_wide.add((team_side, player_name))
            if pass_context.get("from_fw_after_wide") and group in ("CM", "WM", "AM"):
                aggregate[group]["fw_layoff_to_second_receives"] += 1
                side_aggregate[f"{team_side}:{group}"]["fw_layoff_to_second_receives"] += 1
                players[f"{player_meta.get('pos', '')}:{player_name}"]["fw_layoff_to_second_receives"] += 1
                pending_layoff_receiver.add((team_side, player_name))
                layoff_receiver_observed.add((team_side, player_name))
                layoff_receive_ticks[(team_side, player_name)] = entry.get("tick", 0)
            x, y = pos[0], pos[1]
            # Trace actions are logged at a tick within the current match.
            trace_half = 1 if entry.get("tick", 0) < config.half_ticks else 2
            attacking_right = _attacking_right_for_frame(team_side, trace_half)
            receive_progress = _progress(x, attacking_right, pitch_length)
            if receive_progress > 0.67:
                aggregate[group]["final_third_receives"] += 1
                side_aggregate[f"{team_side}:{group}"]["final_third_receives"] += 1
                players[f"{player_meta.get('pos', '')}:{player_name}"]["final_third_receives"] += 1
            in_box = (
                receive_progress > 1.0 - 16.5 / pitch_length
                and abs(y - pitch_width / 2.0) < 20.2
            )
            if in_box:
                aggregate[group]["box_receives"] += 1
                side_aggregate[f"{team_side}:{group}"]["box_receives"] += 1
                players[f"{player_meta.get('pos', '')}:{player_name}"]["box_receives"] += 1

        cut_goal_ticks = {
            (decision.get("tick"), decision.get("team"))
            for decision in trace.get("decisions", [])
            if decision.get("phase") == "on_ball"
            and (((decision.get("goal") or {}).get("goal") or {}).get("goal_type") == "cut_inside_to_shoot")
        }
        pending_carry_decision = {}
        pending_cut_chain = {}

        def finalize_cut_chain(key, reason: str):
            chain = pending_cut_chain.pop(key, None)
            if not chain:
                return
            chain_group = chain["group"]
            aggregate[chain_group]["goal_cut_chain4_samples"] += 1
            totals["goal_cut_chain4_samples"] += 1
            if chain.get("shot"):
                aggregate[chain_group]["goal_cut_chain4_shot"] += 1
                totals["goal_cut_chain4_shot"] += 1
            if chain.get("window"):
                aggregate[chain_group]["goal_cut_chain4_window"] += 1
                totals["goal_cut_chain4_window"] += 1
            aggregate[chain_group]["goal_cut_chain4_best_xg_sum"] += chain.get("best_xg", 0.0)
            aggregate[chain_group]["goal_cut_chain4_best_ready_sum"] += chain.get("best_ready", 0.0)
            totals["goal_cut_chain4_best_xg_sum"] += chain.get("best_xg", 0.0)
            totals["goal_cut_chain4_best_ready_sum"] += chain.get("best_ready", 0.0)
            aggregate[chain_group][f"goal_cut_chain4_end_{reason}"] += 1
            totals[f"goal_cut_chain4_end_{reason}"] += 1

        for decision in trace.get("decisions", []):
            team_side_for_goal = decision.get("team")
            player_name_for_goal = decision.get("player")
            if team_side_for_goal in ("home", "away") and player_name_for_goal:
                players_meta_for_goal = home_players if team_side_for_goal == "home" else away_players
                player_meta_for_goal = next((p for p in players_meta_for_goal if p.get("name") == player_name_for_goal), None)
                if player_meta_for_goal:
                    goal_group = role_group(player_meta_for_goal.get("pos", ""))
                    goal_payload = decision.get("goal") or {}
                    goal_info = goal_payload.get("goal") if isinstance(goal_payload, dict) else None
                    goal_type = goal_info.get("goal_type") if isinstance(goal_info, dict) else ""
                    if goal_type:
                        aggregate[goal_group][f"goal_{goal_type}"] += 1
                        totals[f"goal_{goal_type}"] += 1
                        goal_context = goal_info.get("context", {}) if isinstance(goal_info, dict) else {}
                        goal_phase = goal_context.get("phase", "") if isinstance(goal_context, dict) else ""
                        if goal_phase:
                            aggregate[goal_group][f"goal_phase_{goal_type}_{goal_phase}"] += 1
                            totals[f"goal_phase_{goal_type}_{goal_phase}"] += 1
                        if goal_payload.get("switched"):
                            totals[f"goal_switch_{goal_type}"] += 1
            if decision.get("phase") != "on_ball":
                if (
                    decision.get("phase") == "off_ball_attack"
                    and (decision.get("tick"), decision.get("team")) in cut_goal_ticks
                    and team_side_for_goal in ("home", "away")
                    and player_name_for_goal
                ):
                    chosen = decision.get("chosen", {}) or {}
                    target = chosen.get("target")
                    value = chosen.get("value", {}) or {}
                    components = value.get("components", {}) or {}
                    goal_group = role_group(player_meta_for_goal.get("pos", "")) if player_meta_for_goal else ""
                    if goal_group in ("CM", "WM", "AM", "W", "FW") and isinstance(target, (list, tuple)) and len(target) >= 2:
                        half = 1 if int(decision.get("tick", 0) or 0) < config.half_ticks else 2
                        attacking_right = _attacking_right_for_frame(team_side_for_goal, half)
                        target_progress = _progress(float(target[0]), attacking_right, pitch_length)
                        target_width = abs(float(target[1]) - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                        deep_support = target_progress >= 0.72 and target_width <= 0.42
                        aggregate[goal_group]["cut_offball_samples"] += 1
                        if deep_support:
                            aggregate[goal_group]["cut_offball_deep_chosen"] += 1
                        for key in ("score",):
                            val = value.get(key)
                            if isinstance(val, (int, float)):
                                aggregate[goal_group][f"cut_offball_{key}_sum"] += val
                                if deep_support:
                                    aggregate[goal_group][f"cut_offball_deep_{key}_sum"] += val
                        for key in ("support_angle_value", "second_line_support", "reach", "pass_feasibility", "role_shape_factor"):
                            val = components.get(key)
                            if isinstance(val, (int, float)):
                                aggregate[goal_group][f"cut_offball_{key}_sum"] += val
                                if deep_support:
                                    aggregate[goal_group][f"cut_offball_deep_{key}_sum"] += val
                continue
            team_side = decision.get("team")
            player_name = decision.get("player")
            if team_side not in ("home", "away") or not player_name:
                continue
            players_meta = home_players if team_side == "home" else away_players
            player_meta = next((p for p in players_meta if p.get("name") == player_name), None)
            if not player_meta:
                continue
            decision_tick = int(decision.get("tick", 0) or 0)
            decision_pos = decision.get("pos")
            if (
                isinstance(decision_pos, (list, tuple))
                and len(decision_pos) >= 2
                and all(isinstance(v, (int, float)) for v in decision_pos[:2])
            ):
                decision_x = float(decision_pos[0])
                decision_y = float(decision_pos[1])
            else:
                decision_x = None
                decision_y = None
            frame_tick = max((tick for tick in frame_ticks if tick <= decision_tick), default=None)
            frame = frames_by_tick.get(frame_tick) if frame_tick is not None else None
            if frame is None or decision_tick - frame_tick > max(1, match.config.frame_interval):
                if decision_x is None or decision_y is None:
                    continue
                frame = None
            if frame is not None:
                half = int(frame.get("half", 1) or 1)
            else:
                half = 1 if decision_tick < config.half_ticks else 2
            attacking_right = _attacking_right_for_frame(team_side, half)
            if decision_x is None or decision_y is None:
                ball = frame.get("ball") if frame is not None else None
                if not ball:
                    continue
                decision_x, decision_y = ball[1], ball[0]
            if _progress(decision_x, attacking_right, pitch_length) <= 0.67:
                continue

            group = role_group(player_meta.get("pos", ""))
            decision_progress = _progress(decision_x, attacking_right, pitch_length)
            decision_width = abs(decision_y - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
            defending_side = "away" if team_side == "home" else "home"
            defending_meta = away_players if team_side == "home" else home_players
            defending_coords = frame.get(defending_side, []) if frame is not None else []
            nearest_def = None
            for idx, coord in enumerate(defending_coords):
                if idx >= len(defending_meta):
                    continue
                if role_group(defending_meta[idx].get("pos", "")) == "GK":
                    continue
                d = _dist((decision_x, decision_y), _xy_from_frame_coord(coord))
                nearest_def = d if nearest_def is None else min(nearest_def, d)

            chosen = decision.get("chosen", {}) or {}
            action_type = chosen.get("action_type", "unknown")
            if action_type == "pass":
                chosen_details_for_action = chosen.get("details") or {}
                chosen_components_for_action = (chosen.get("value") or {}).get("components") or {}
                if chosen_components_for_action.get("target_kind") == "space":
                    action_type = "pass_to_space"
                else:
                    action_type = chosen_details_for_action.get("pass_type", "short_pass")
            chain_key = (team_side, player_name)
            cut_chain = pending_cut_chain.get(chain_key)
            if cut_chain and decision_tick > cut_chain["tick"]:
                cut_chain["steps"] += 1
                best_shot_item = None
                for item in [chosen] + list(decision.get("alternatives", []) or []):
                    if item.get("action_type") != "shoot":
                        continue
                    score = (item.get("value") or {}).get("score")
                    if isinstance(score, (int, float)) and (
                        best_shot_item is None
                        or score > (best_shot_item.get("value") or {}).get("score", -1)
                    ):
                        best_shot_item = item
                if best_shot_item is not None:
                    components = (best_shot_item.get("value") or {}).get("components") or {}
                    xg = float(components.get("xg", 0.0) or 0.0)
                    ready = max(
                        float(components.get("shot_readiness", 0.0) or 0.0),
                        float(components.get("open_medium_window", 0.0) or 0.0),
                        float(components.get("clean_second_line_shot", 0.0) or 0.0),
                    )
                    cut_chain["best_xg"] = max(cut_chain.get("best_xg", 0.0), xg)
                    cut_chain["best_ready"] = max(cut_chain.get("best_ready", 0.0), ready)
                    if xg >= 0.080 or ready >= 0.180:
                        cut_chain["window"] = True
                if action_type == "shoot":
                    cut_chain["shot"] = True
                    finalize_cut_chain(chain_key, "shot")
                elif action_type in PASS_ACTIONS or action_type == "clear":
                    if action_type in PASS_ACTIONS:
                        chosen_details = chosen.get("details") or {}
                        chosen_components = (chosen.get("value") or {}).get("components") or {}
                        chosen_target = chosen.get("target") or chosen_details.get("target")
                        receiver_idx = chosen_details.get("target_player_idx")
                        if receiver_idx is None:
                            receiver_idx = chosen_details.get("intended_receiver")
                        receiver_group = "UNKNOWN"
                        if isinstance(receiver_idx, int) and 0 <= receiver_idx < len(players_meta):
                            receiver_group = role_group(players_meta[receiver_idx].get("pos", ""))
                        if isinstance(chosen_target, (list, tuple)) and len(chosen_target) >= 2:
                            release_progress = _progress(float(chosen_target[0]), attacking_right, pitch_length)
                            release_width = abs(float(chosen_target[1]) - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                            release_zone = target_zone(release_progress, release_width)
                            aggregate[cut_chain["group"]][f"goal_cut_release_zone_{release_zone}"] += 1
                            totals[f"goal_cut_release_zone_{release_zone}"] += 1
                            aggregate[cut_chain["group"]]["goal_cut_release_target_progress_sum"] += release_progress
                            aggregate[cut_chain["group"]]["goal_cut_release_target_width_sum"] += release_width
                            totals["goal_cut_release_target_progress_sum"] += release_progress
                            totals["goal_cut_release_target_width_sum"] += release_width
                        aggregate[cut_chain["group"]][f"goal_cut_release_to_{receiver_group}"] += 1
                        totals[f"goal_cut_release_to_{receiver_group}"] += 1
                        aggregate[cut_chain["group"]][f"goal_cut_release_kind_{chosen_components.get('target_kind', action_type)}"] += 1
                        totals[f"goal_cut_release_kind_{chosen_components.get('target_kind', action_type)}"] += 1
                    finalize_cut_chain(chain_key, "release")
                elif cut_chain.get("steps", 0) >= 4:
                    finalize_cut_chain(chain_key, "horizon")

            pending_decision = pending_carry_decision.get((team_side, player_name))
            if (
                pending_decision
                and decision_tick > pending_decision["tick"]
                and group in ("W", "WM", "CM", "AM")
            ):
                pending_group = pending_decision["group"]
                next_action = action_type
                if next_action in ("pass", "short_pass", "long_pass"):
                    next_action = "pass"
                elif next_action == "pass_to_space":
                    next_action = "pass_to_space"
                aggregate[pending_group][f"ft_carry_decision_next_{next_action}"] += 1
                pending_goal_type = pending_decision.get("goal_type", "")
                if pending_goal_type:
                    aggregate[pending_group][f"goal_follow_{pending_goal_type}_{next_action}"] += 1
                    totals[f"goal_follow_{pending_goal_type}_{next_action}"] += 1
                if isinstance(chosen_score := (chosen.get("value") or {}).get("score"), (int, float)):
                    aggregate[pending_group]["ft_carry_decision_next_score_sum"] += chosen_score
                pending_carry_decision.pop((team_side, player_name), None)
            aggregate[group]["ft_decision_samples"] += 1
            aggregate[group]["ft_decision_progress_sum"] += decision_progress
            aggregate[group]["ft_decision_width_sum"] += decision_width
            if nearest_def is not None:
                aggregate[group]["ft_decision_nearest_def_sum"] += nearest_def
                aggregate[group]["ft_decision_nearest_def_samples"] += 1
            aggregate[group][f"ft_decision_chosen_{action_type}"] += 1
            aggregate[group][f"ft_decision_chosen_{action_type}_progress_sum"] += decision_progress
            aggregate[group][f"ft_decision_chosen_{action_type}_width_sum"] += decision_width
            aggregate[group][f"ft_decision_chosen_{action_type}_samples"] += 1
            chosen_score = (chosen.get("value") or {}).get("score")
            chosen_target = (chosen.get("target") or (chosen.get("details") or {}).get("target"))
            if isinstance(chosen_target, (list, tuple)) and len(chosen_target) >= 2:
                target_progress = _progress(float(chosen_target[0]), attacking_right, pitch_length)
                target_width = abs(float(chosen_target[1]) - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                aggregate[group][f"ft_decision_chosen_{action_type}_target_progress_sum"] += target_progress
                aggregate[group][f"ft_decision_chosen_{action_type}_target_width_sum"] += target_width
                aggregate[group][f"ft_decision_chosen_{action_type}_target_samples"] += 1
                if action_type in PASS_ACTIONS:
                    chosen_details = chosen.get("details") or {}
                    chosen_components = (chosen.get("value") or {}).get("components") or {}
                    receiver_idx = chosen_details.get("target_player_idx")
                    if receiver_idx is None:
                        receiver_idx = chosen_details.get("intended_receiver")
                    receiver_group = "UNKNOWN"
                    if isinstance(receiver_idx, int) and 0 <= receiver_idx < len(players_meta):
                        receiver_group = role_group(players_meta[receiver_idx].get("pos", ""))
                    component_kind = chosen_components.get("target_kind")
                    target_kind = str(component_kind or ("space" if action_type == "pass_to_space" else "feet"))
                    zone = target_zone(target_progress, target_width)
                    aggregate[group]["ft_pass_topology_samples"] += 1
                    aggregate[group][f"ft_pass_to_{receiver_group}"] += 1
                    aggregate[group][f"ft_pass_kind_{target_kind}"] += 1
                    aggregate[group][f"ft_pass_zone_{zone}"] += 1
                    aggregate[group]["ft_pass_target_progress_sum"] += target_progress
                    aggregate[group]["ft_pass_target_width_sum"] += target_width
                    aggregate[group]["ft_pass_target_kind_space"] += 1 if target_kind == "space" else 0
                    if isinstance(chosen_score, (int, float)):
                        aggregate[group]["ft_pass_score_sum"] += chosen_score
                    for key in (
                        "delta",
                        "effective_delta",
                        "success_prob",
                        "receiver_pressure",
                        "lane_risk",
                        "after_value",
                        "high_threat_space",
                        "final_third_combination",
                        "wide_creation_value",
                        "inside_arrival_value",
                        "second_line_arrival_value",
                        "second_line_cutback_value",
                        "cutback_value",
                        "pressure_release_value",
                        "stale_release_value",
                        "current_shot_window",
                        "pass_can_pay_for_window",
                        "shoot_window_release_cost",
                    ):
                        value = chosen_components.get(key)
                        if isinstance(value, (int, float)):
                            aggregate[group][f"ft_pass_{key}_sum"] += value
            if isinstance(chosen_score, (int, float)):
                aggregate[group]["ft_decision_chosen_score_sum"] += chosen_score
            goal_payload_for_action = decision.get("goal") or {}
            goal_info_for_action = goal_payload_for_action.get("goal") if isinstance(goal_payload_for_action, dict) else None
            goal_type_for_action = goal_info_for_action.get("goal_type") if isinstance(goal_info_for_action, dict) else ""
            if goal_type_for_action:
                if goal_type_for_action == "cut_inside_to_shoot" and frame is not None:
                    attacking_coords = frame.get(team_side, [])
                    nearest_support = None
                    nearest_second_line_support = None
                    nearest_forward_support = None
                    for aidx, acoord in enumerate(attacking_coords):
                        if aidx >= len(players_meta):
                            continue
                        if players_meta[aidx].get("name") == player_name:
                            continue
                        support_group = role_group(players_meta[aidx].get("pos", ""))
                        if support_group == "GK":
                            continue
                        d = _dist((decision_x, decision_y), _xy_from_frame_coord(acoord))
                        nearest_support = d if nearest_support is None else min(nearest_support, d)
                        if support_group in ("CM", "WM", "AM"):
                            nearest_second_line_support = d if nearest_second_line_support is None else min(nearest_second_line_support, d)
                        if support_group == "FW":
                            nearest_forward_support = d if nearest_forward_support is None else min(nearest_forward_support, d)
                    if nearest_support is not None:
                        aggregate[group]["goal_cut_support_dist_sum"] += nearest_support
                    if nearest_second_line_support is not None:
                        aggregate[group]["goal_cut_second_line_support_dist_sum"] += nearest_second_line_support
                    if nearest_forward_support is not None:
                        aggregate[group]["goal_cut_forward_support_dist_sum"] += nearest_forward_support
                    aggregate[group]["goal_cut_support_samples"] += 1
                converted_action = action_type
                if converted_action in ("pass", "short_pass", "long_pass", "pass_to_space"):
                    converted_action = "pass"
                elif converted_action == "shoot":
                    converted_action = "shoot"
                elif converted_action not in ("carry", "hold", "clear"):
                    converted_action = "other"
                totals[f"goal_action_{goal_type_for_action}_{converted_action}"] += 1
                aggregate[group][f"goal_action_{goal_type_for_action}_{converted_action}"] += 1
                goal_context_for_action = goal_info_for_action.get("context", {}) if isinstance(goal_info_for_action, dict) else {}
                goal_phase_for_action = goal_context_for_action.get("phase", "") if isinstance(goal_context_for_action, dict) else ""
                if goal_phase_for_action:
                    totals[f"goal_action_{goal_type_for_action}_{goal_phase_for_action}_{converted_action}"] += 1
                    aggregate[group][f"goal_action_{goal_type_for_action}_{goal_phase_for_action}_{converted_action}"] += 1
                if goal_type_for_action == "cut_inside_to_shoot" and action_type == "carry":
                    chosen_components = (chosen.get("value") or {}).get("components") or {}
                    if isinstance(chosen_target, (list, tuple)) and len(chosen_target) >= 2:
                        aggregate[group]["goal_cut_carry_target_progress_sum"] += target_progress
                        aggregate[group]["goal_cut_carry_target_width_sum"] += target_width
                        if target_progress >= 0.80 and target_width <= 0.34:
                            cut_bucket = "good"
                        elif target_progress >= 0.76 and target_width <= 0.50:
                            cut_bucket = "mid"
                        else:
                            cut_bucket = "wide"
                        aggregate[group][f"goal_cut_carry_target_{cut_bucket}"] += 1
                        target_pos = (float(chosen_target[0]), float(chosen_target[1]))
                        nearest_cut_def = None
                        cut_def_10 = 0
                        cut_def_14 = 0
                        for dcoord in defending_coords:
                            dpos = _xy_from_frame_coord(dcoord)
                            d = _dist(target_pos, dpos)
                            nearest_cut_def = d if nearest_cut_def is None else min(nearest_cut_def, d)
                            if d < 10.0:
                                cut_def_10 += 1
                            if d < 14.0:
                                cut_def_14 += 1
                        attacking_coords = frame.get(team_side, []) if frame is not None else []
                        nearest_cut_support = None
                        for aidx, acoord in enumerate(attacking_coords):
                            if aidx >= len(players_meta):
                                continue
                            if players_meta[aidx].get("name") == player_name:
                                continue
                            if role_group(players_meta[aidx].get("pos", "")) == "GK":
                                continue
                            apos = _xy_from_frame_coord(acoord)
                            d = _dist(target_pos, apos)
                            nearest_cut_support = d if nearest_cut_support is None else min(nearest_cut_support, d)
                        aggregate[group]["goal_cut_carry_target_def10_sum"] += cut_def_10
                        aggregate[group]["goal_cut_carry_target_def14_sum"] += cut_def_14
                        if nearest_cut_def is not None:
                            aggregate[group]["goal_cut_carry_target_nearest_def_sum"] += nearest_cut_def
                        if nearest_cut_support is not None:
                            aggregate[group]["goal_cut_carry_target_support_sum"] += nearest_cut_support
                    for key in (
                        "future_shot_gain",
                        "carry_to_shoot_window",
                        "wide_second_line_carry_window",
                        "path_min_perp",
                        "path_peak_threat",
                        "path_peak_proj",
                        "path_peak_final_third_control",
                        "path_peak_control_factor",
                    ):
                        value = chosen_components.get(key)
                        if isinstance(value, (int, float)):
                            aggregate[group][f"goal_cut_carry_{key}_sum"] += value
                            if isinstance(chosen_target, (list, tuple)) and len(chosen_target) >= 2:
                                aggregate[group][f"goal_cut_carry_{cut_bucket}_{key}_sum"] += value
                    path_value = chosen_components.get("path_feasibility")
                    if isinstance(path_value, (int, float)):
                        aggregate[group]["goal_cut_carry_path_feasibility_sum"] += path_value
                        if isinstance(chosen_target, (list, tuple)) and len(chosen_target) >= 2:
                            aggregate[group][f"goal_cut_carry_{cut_bucket}_path_feasibility_sum"] += path_value
                    if isinstance(chosen_score, (int, float)):
                        aggregate[group]["goal_cut_carry_score_sum"] += chosen_score
                    aggregate[group]["goal_cut_carry_samples"] += 1
                    if (team_side, player_name) not in pending_cut_chain:
                        pending_cut_chain[(team_side, player_name)] = {
                            "tick": decision_tick,
                            "group": group,
                            "steps": 0,
                            "shot": False,
                            "window": False,
                            "best_xg": 0.0,
                            "best_ready": 0.0,
                        }
            layoff_tick = layoff_receive_ticks.get((team_side, player_name))
            is_layoff_decision = (
                layoff_tick is not None
                and group in ("CM", "WM", "AM")
                and 0 <= decision_tick - layoff_tick <= max(2, match.config.frame_interval)
            )
            if is_layoff_decision:
                aggregate[group]["fw_layoff_decision_samples"] += 1
                aggregate[group]["fw_layoff_decision_progress_sum"] += decision_progress
                aggregate[group]["fw_layoff_decision_width_sum"] += decision_width
                aggregate[group][f"fw_layoff_chosen_{action_type}"] += 1
                if nearest_def is not None:
                    aggregate[group]["fw_layoff_nearest_def_sum"] += nearest_def
                    aggregate[group]["fw_layoff_nearest_def_samples"] += 1
                if isinstance(chosen_score, (int, float)):
                    aggregate[group]["fw_layoff_chosen_score_sum"] += chosen_score

            if action_type == "carry" and group in ("W", "WM", "CM", "AM"):
                pending_goal_type = goal_type_for_action if goal_type_for_action == "cut_inside_to_shoot" else ""
                pending_carry_decision[(team_side, player_name)] = {
                    "tick": decision_tick,
                    "group": group,
                    "goal_type": pending_goal_type,
                }

            candidate_scores = defaultdict(float)
            candidate_counts = Counter()
            best_by_action = {}
            through_candidate_seen = False
            byline_candidate_seen = False
            best_through_score = 0.0
            best_byline_score = 0.0
            chosen_through_candidate = False
            chosen_byline_candidate = False
            for item in [chosen] + list(decision.get("alternatives", []) or []):
                item_action = item.get("action_type", "unknown")
                item_components = (item.get("value") or {}).get("components") or {}
                item_target = item.get("target") or (item.get("details") or {}).get("target")
                item_target_progress = None
                item_target_width = None
                if isinstance(item_target, (list, tuple)) and len(item_target) >= 2:
                    item_target_progress = _progress(float(item_target[0]), attacking_right, pitch_length)
                    item_target_width = abs(float(item_target[1]) - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                if item_action == "pass":
                    item_details = item.get("details") or {}
                    if item_components.get("target_kind") == "space":
                        item_action = "pass_to_space"
                    else:
                        item_action = item_details.get("pass_type", "short_pass")
                score = (item.get("value") or {}).get("score")
                if item_action in PASS_ACTIONS and isinstance(score, (int, float)):
                    high_threat = float(item_components.get("high_threat_space", 0.0) or 0.0)
                    final_comb = float(item_components.get("final_third_combination", 0.0) or 0.0)
                    success_prob = float(item_components.get("success_prob", 0.0) or 0.0)
                    receiver_pressure = float(item_components.get("receiver_pressure", 0.0) or 0.0)
                    lane_risk = float(item_components.get("lane_risk", 0.0) or 0.0)
                    progress_gain = float(item_components.get("progress_gain", 0.0) or 0.0)
                    target_kind = str(item_components.get("target_kind", ""))
                    is_through_shape = (
                        target_kind == "space"
                        and item_target_progress is not None
                        and item_target_width is not None
                        and item_target_progress >= 0.70
                        and item_target_width <= 0.54
                        and progress_gain >= 0.045
                        and high_threat > 0.0
                    )
                    is_byline_shape = (
                        decision_progress >= 0.82
                        and decision_width >= 0.48
                        and item_target_progress is not None
                        and item_target_width is not None
                        and item_target_progress >= 0.82
                        and item_target_width <= 0.62
                        and max(high_threat, final_comb) > 0.0
                    )
                    if is_through_shape:
                        through_candidate_seen = True
                        best_through_score = max(best_through_score, float(score))
                        aggregate[group]["through_candidate_samples"] += 1
                        aggregate[group]["through_candidate_score_sum"] += float(score)
                        aggregate[group]["through_candidate_success_sum"] += success_prob
                        aggregate[group]["through_candidate_pressure_sum"] += receiver_pressure
                        aggregate[group]["through_candidate_lane_sum"] += lane_risk
                        aggregate[group]["through_candidate_high_sum"] += high_threat
                        if item is chosen:
                            chosen_through_candidate = True
                    if is_byline_shape:
                        byline_candidate_seen = True
                        best_byline_score = max(best_byline_score, float(score))
                        aggregate[group]["byline_candidate_samples"] += 1
                        aggregate[group]["byline_candidate_score_sum"] += float(score)
                        aggregate[group]["byline_candidate_success_sum"] += success_prob
                        aggregate[group]["byline_candidate_pressure_sum"] += receiver_pressure
                        aggregate[group]["byline_candidate_lane_sum"] += lane_risk
                        aggregate[group]["byline_candidate_high_sum"] += max(high_threat, final_comb)
                        if item is chosen:
                            chosen_byline_candidate = True
                if isinstance(score, (int, float)):
                    candidate_scores[item_action] += score
                    candidate_counts[item_action] += 1
                    if item_action not in best_by_action or score > best_by_action[item_action][0]:
                        best_by_action[item_action] = (score, item)
            for item_action, score_sum in candidate_scores.items():
                aggregate[group][f"ft_candidate_{item_action}_score_sum"] += score_sum
                aggregate[group][f"ft_candidate_{item_action}_samples"] += candidate_counts[item_action]
            if through_candidate_seen:
                aggregate[group]["through_decision_samples"] += 1
                aggregate[group]["through_best_score_sum"] += best_through_score
                aggregate[group][f"through_decision_chosen_{action_type}"] += 1
                if chosen_through_candidate:
                    aggregate[group]["through_candidate_chosen"] += 1
            if byline_candidate_seen:
                aggregate[group]["byline_decision_samples"] += 1
                aggregate[group]["byline_best_score_sum"] += best_byline_score
                aggregate[group][f"byline_decision_chosen_{action_type}"] += 1
                if chosen_byline_candidate:
                    aggregate[group]["byline_candidate_chosen"] += 1

            if goal_type_for_action == "hold_for_opportunity":
                goal_context = goal_info.get("context", {}) if isinstance(goal_info, dict) else {}
                goal_age = float(goal_context.get("goal_age_ticks", 0.0) or 0.0)
                aggregate[group]["hold_goal_decision_samples"] += 1
                aggregate[group]["hold_goal_age_sum"] += goal_age
                aggregate[group][f"hold_goal_chosen_{action_type}"] += 1
                for family, action_names in (
                    ("pass", ("pass", "short_pass", "long_pass", "pass_to_space")),
                    ("carry", ("carry",)),
                    ("shoot", ("shoot",)),
                    ("hold", ("hold",)),
                ):
                    best_score = 0.0
                    for action_name in action_names:
                        if action_name in best_by_action:
                            best_score = max(best_score, float(best_by_action[action_name][0] or 0.0))
                    aggregate[group][f"hold_goal_best_{family}_score_sum"] += best_score
                if goal_age >= 2.0:
                    aggregate[group]["hold_goal_mature_samples"] += 1
                    aggregate[group][f"hold_goal_mature_chosen_{action_type}"] += 1

            for item_action, (score, item) in best_by_action.items():
                aggregate[group][f"ft_best_{item_action}_score_sum"] += score
                aggregate[group][f"ft_best_{item_action}_samples"] += 1
                if is_layoff_decision:
                    aggregate[group][f"fw_layoff_best_{item_action}_score_sum"] += score
                    aggregate[group][f"fw_layoff_best_{item_action}_samples"] += 1
                components = (item.get("value") or {}).get("components") or {}
                if item_action == "shoot":
                    for key in ("xg", "open_medium_window", "pressure_factor", "lane_factor", "distance"):
                        value = components.get(key)
                        if isinstance(value, (int, float)):
                            aggregate[group][f"ft_best_shoot_{key}_sum"] += value
                            if is_layoff_decision:
                                aggregate[group][f"fw_layoff_best_shoot_{key}_sum"] += value
                    aggregate[group]["ft_best_shoot_component_samples"] += 1
                    if is_layoff_decision:
                        aggregate[group]["fw_layoff_best_shoot_score_sum"] += score
                        aggregate[group]["fw_layoff_best_shoot_component_samples"] += 1
                item_target = item.get("target") or (item.get("details") or {}).get("target")
                if isinstance(item_target, (list, tuple)) and len(item_target) >= 2:
                    target_progress = _progress(float(item_target[0]), attacking_right, pitch_length)
                    target_width = abs(float(item_target[1]) - pitch_width / 2.0) / max(1.0, pitch_width / 2.0)
                    aggregate[group][f"ft_best_{item_action}_target_progress_sum"] += target_progress
                    aggregate[group][f"ft_best_{item_action}_target_width_sum"] += target_width
                    aggregate[group][f"ft_best_{item_action}_target_samples"] += 1
                    if is_layoff_decision:
                        aggregate[group][f"fw_layoff_best_{item_action}_target_progress_sum"] += target_progress
                        aggregate[group][f"fw_layoff_best_{item_action}_target_width_sum"] += target_width
                        aggregate[group][f"fw_layoff_best_{item_action}_target_samples"] += 1

                if item_action == "carry" and group in ("WM", "CM", "AM", "W"):
                    components = (item.get("value") or {}).get("components") or {}
                    for key in ("future_shot_gain", "carry_to_shoot_window", "wide_second_line_carry_window"):
                        value = components.get(key)
                        if isinstance(value, (int, float)):
                            aggregate[group][f"ft_best_carry_{key}_sum"] += value
                    aggregate[group]["ft_best_carry_window_component_samples"] += 1

            best_second_pass = None
            for item in [chosen] + list(decision.get("alternatives", []) or []):
                item_action = item.get("action_type", "unknown")
                if item_action not in PASS_ACTIONS:
                    continue
                score = (item.get("value") or {}).get("score")
                if not isinstance(score, (int, float)):
                    continue
                components = (item.get("value") or {}).get("components") or {}
                receiver_goal_fit = float(components.get("receiver_goal_fit", 0.0) or 0.0)
                second_value = (
                    float(components.get("second_line_arrival_value", 0.0) or 0.0)
                    + float(components.get("second_line_cutback_value", 0.0) or 0.0)
                )
                if receiver_goal_fit < 0.35 and second_value < 0.010:
                    continue
                candidate_weight = score + receiver_goal_fit * 0.020 + second_value
                if best_second_pass is None or candidate_weight > best_second_pass[0]:
                    best_second_pass = (candidate_weight, score, receiver_goal_fit, second_value, item_action)
            if best_second_pass is not None and isinstance(chosen_score, (int, float)):
                _, second_score, receiver_goal_fit, second_value, second_action = best_second_pass
                gap = chosen_score - second_score
                aggregate[group]["ft_second_pass_candidate_samples"] += 1
                aggregate[group]["ft_second_pass_candidate_score_sum"] += second_score
                aggregate[group]["ft_second_pass_candidate_fit_sum"] += receiver_goal_fit
                aggregate[group]["ft_second_pass_candidate_value_sum"] += second_value
                aggregate[group]["ft_second_pass_gap_sum"] += gap
                aggregate[group][f"ft_second_pass_chosen_{action_type}"] += 1
                if action_type in PASS_ACTIONS:
                    chosen_components = (chosen.get("value") or {}).get("components") or {}
                    chosen_fit = float(chosen_components.get("receiver_goal_fit", 0.0) or 0.0)
                    chosen_second = (
                        float(chosen_components.get("second_line_arrival_value", 0.0) or 0.0)
                        + float(chosen_components.get("second_line_cutback_value", 0.0) or 0.0)
                    )
                    if chosen_fit >= 0.35 or chosen_second >= 0.010:
                        aggregate[group]["ft_second_pass_chosen_second_pass"] += 1
                    else:
                        aggregate[group]["ft_second_pass_chosen_other_pass"] += 1
                if gap <= 0.0:
                    aggregate[group]["ft_second_pass_wins_value"] += 1

        for key in list(pending_cut_chain.keys()):
            finalize_cut_chain(key, "open")

    return totals, aggregate, players, side_aggregate


def structure_scorecard(totals: Counter, aggregate) -> dict:
    matches = max(1, totals["matches"])
    total_shots = max(1, sum(row["shots"] for row in aggregate.values()))
    ft_touches = max(1, sum(row["final_third_touch_frames"] for row in aggregate.values()))
    ft_receives = max(1, sum(row["final_third_receives"] for row in aggregate.values()))
    chain3_events = sum(
        row["chain3_next_carry"]
        + row["chain3_next_pass"]
        + row["chain3_next_pass_to_space"]
        + row["chain3_next_shot"]
        + row["chain3_next_hold"]
        + row["chain3_next_clear"]
        + row["chain3_next_unknown"]
        for row in aggregate.values()
    )
    def row(group: str) -> Counter:
        return aggregate.get(group, Counter())

    def pct(value: float, total: float) -> float:
        return value / max(1.0, total) * 100.0

    nearest_samples = max(1, totals["ft_nearest_def_samples"])
    arc_samples = max(1, totals["arc_window_samples"])
    arc_def_samples = max(1, totals["arc_def_samples"])
    arc_target_samples = max(1, totals["arc_second_line_target_samples"])
    arc_anchor_samples = max(1, totals["arc_second_line_anchor_samples"])
    rest_samples = max(1, totals["rest_def_samples"])
    rest_front_samples = max(1, totals["rest_def_opp_front_samples"])
    arc_roles = {
        group: totals[f"arc_def_role_{group}"]
        for group in ("CB", "FB", "DM", "CM", "WM", "FW", "AM")
    }
    arc_main_role = max(arc_roles, key=arc_roles.get) if any(arc_roles.values()) else "NA"
    cut_support_samples = sum(row(group)["goal_cut_support_samples"] for group in ("W", "WM", "CM", "AM", "FW"))
    cut_support_denom = max(1, cut_support_samples)
    cut_release_total = max(1, totals["goal_cut_chain4_end_release"])
    card = {
        "matches": totals["matches"],
        "goals": totals["goals"] / matches,
        "shots": totals["shots"] / matches,
        "sot_pct": pct(totals["sot"], totals["shots"]),
        "pass_pct": pct(totals["completed_passes"], totals["passes"]),
        "fw_shot_pct": pct(row("FW")["shots"], total_shots),
        "w_shot_pct": pct(row("W")["shots"], total_shots),
        "wm_shot_pct": pct(row("WM")["shots"], total_shots),
        "cm_shot_pct": pct(row("CM")["shots"], total_shots),
        "def_shot_pct": pct(row("FB")["shots"] + row("CB")["shots"], total_shots),
        "fw_ft_touch_pct": pct(row("FW")["final_third_touch_frames"], ft_touches),
        "w_ft_touch_pct": pct(row("W")["final_third_touch_frames"], ft_touches),
        "wm_ft_touch_pct": pct(row("WM")["final_third_touch_frames"], ft_touches),
        "cm_ft_touch_pct": pct(row("CM")["final_third_touch_frames"], ft_touches),
        "fw_ft_receive_pct": pct(row("FW")["final_third_receives"], ft_receives),
        "w_ft_receive_pct": pct(row("W")["final_third_receives"], ft_receives),
        "wm_ft_receive_pct": pct(row("WM")["final_third_receives"], ft_receives),
        "cm_ft_receive_pct": pct(row("CM")["final_third_receives"], ft_receives),
        "c3p_shots": sum(r["shot_after_carry_3p"] for r in aggregate.values()),
        "chain3_carry": sum(r["chain3_next_carry"] for r in aggregate.values()),
        "chain3_pass": sum(r["chain3_next_pass"] + r["chain3_next_pass_to_space"] for r in aggregate.values()),
        "chain3_shot": sum(r["chain3_next_shot"] for r in aggregate.values()),
        "chain3_events": chain3_events,
        "def_nearest": totals["ft_nearest_def_dist_sum"] / nearest_samples,
        "def_close6": totals["ft_close6_def_sum"] / nearest_samples,
        "def_close8": totals["ft_close8_def_sum"] / nearest_samples,
        "rest_actual": totals["rest_def_actual_sum"] / rest_samples,
        "rest_actual_max": totals["rest_def_actual_max_sum"] / rest_samples,
        "rest_target": totals["rest_def_target_sum"] / rest_samples,
        "rest_target_max": totals["rest_def_target_max_sum"] / rest_samples,
        "rest_anchor": totals["rest_def_anchor_sum"] / rest_samples,
        "rest_anchor_max": totals["rest_def_anchor_max_sum"] / rest_samples,
        "rest_opp_front": totals["rest_def_opp_front_sum"] / rest_front_samples,
        "arc_second_line": totals["arc_second_line_dist_sum"] / arc_samples,
        "arc_second_line_band": totals["arc_second_line_band_dist_sum"] / arc_samples,
        "arc_second_line_target": totals["arc_second_line_target_dist_sum"] / arc_target_samples,
        "arc_second_line_anchor": totals["arc_second_line_anchor_dist_sum"] / arc_anchor_samples,
        "arc_def": totals["arc_def_dist_sum"] / arc_def_samples,
        "arc_second_line_close_pct": pct(totals["arc_second_line_close10"], totals["arc_window_samples"]),
        "arc_second_line_target_close_pct": pct(totals["arc_second_line_target_close10"], totals["arc_second_line_target_samples"]),
        "arc_second_line_anchor_close_pct": pct(totals["arc_second_line_anchor_close10"], totals["arc_second_line_anchor_samples"]),
        "arc_low_pressure_pct": pct(totals["arc_low_pressure"], totals["arc_window_samples"]),
        "arc_ready_pct": pct(totals["arc_ready_window"], totals["arc_window_samples"]),
        "arc_band_ready_pct": pct(totals["arc_band_ready_window"], totals["arc_window_samples"]),
        "arc_only_second_line_pct": pct(totals["arc_only_second_line"], totals["arc_window_samples"]),
        "arc_only_low_pressure_pct": pct(totals["arc_only_low_pressure"], totals["arc_window_samples"]),
        "arc_neither_pct": pct(totals["arc_neither_ready_part"], totals["arc_window_samples"]),
        "arc_only2l_sync_pct": pct(totals["arc_only2l_to_ready3"], totals["arc_only2l_follow_samples"]),
        "arc_onlyp_sync_pct": pct(totals["arc_onlyp_to_ready3"], totals["arc_onlyp_follow_samples"]),
        "arc_main_role": arc_main_role,
        "arc_main_role_pct": pct(arc_roles.get(arc_main_role, 0), totals["arc_def_samples"]),
        "arc_def_samples": totals["arc_def_samples"],
        "arc_role_CB": arc_roles["CB"],
        "arc_role_FB": arc_roles["FB"],
        "arc_role_DM": arc_roles["DM"],
        "arc_role_CM": arc_roles["CM"],
        "arc_role_WM": arc_roles["WM"],
        "arc_role_FW": arc_roles["FW"],
        "arc_role_AM": arc_roles["AM"],
        "wide_to_fw": row("FW")["wide_to_fw_receives"],
        "fw_layoff_second": sum(row(group)["fw_layoff_to_second_receives"] for group in ("CM", "WM", "AM")),
        "layoff_second_shot": sum(row(group)["shot_after_fw_layoff_chain"] for group in ("CM", "WM", "AM")),
        "layoff_next_carry": sum(row(group)["fw_layoff_next_carry"] for group in ("CM", "WM", "AM")),
        "layoff_next_pass": sum(
            row(group)["fw_layoff_next_short_pass"] + row(group)["fw_layoff_next_long_pass"] + row(group)["fw_layoff_next_pass_to_space"]
            for group in ("CM", "WM", "AM")
        ),
        "layoff_next_hold": sum(row(group)["fw_layoff_next_hold"] for group in ("CM", "WM", "AM")),
        "fw_ft_shot": row("FW")["final_third_action_shot"],
        "fw_ft_pass": (
            row("FW")["final_third_action_short_pass"]
            + row("FW")["final_third_action_long_pass"]
            + row("FW")["final_third_action_pass_to_space"]
        ),
        "fw_ft_carry": row("FW")["final_third_action_carry"],
        "w_ft_shot": row("W")["final_third_action_shot"],
        "w_ft_pass": (
            row("W")["final_third_action_short_pass"]
            + row("W")["final_third_action_long_pass"]
            + row("W")["final_third_action_pass_to_space"]
        ),
        "w_ft_carry": row("W")["final_third_action_carry"],
        "wm_ft_shot": row("WM")["final_third_action_shot"],
        "wm_ft_pass": (
            row("WM")["final_third_action_short_pass"]
            + row("WM")["final_third_action_long_pass"]
            + row("WM")["final_third_action_pass_to_space"]
        ),
        "wm_ft_carry": row("WM")["final_third_action_carry"],
        "cm_ft_shot": row("CM")["final_third_action_shot"],
        "cm_ft_pass": (
            row("CM")["final_third_action_short_pass"]
            + row("CM")["final_third_action_long_pass"]
            + row("CM")["final_third_action_pass_to_space"]
        ),
        "cm_ft_carry": row("CM")["final_third_action_carry"],
        "goal_cut_inside": totals["goal_cut_inside_to_shoot"] / matches,
        "goal_arc_arrival": totals["goal_arc_arrival_for_cutback"] / matches,
        "goal_wide_hold": totals["goal_wide_hold_for_overlap"] / matches,
        "goal_pressure_layoff": totals["goal_release_pressure_with_layoff"] / matches,
        "goal_release_support": totals["goal_release_to_arriving_support"] / matches,
        "goal_hold_opportunity": totals["goal_hold_for_opportunity"] / matches,
        "goal_through_behind": totals["goal_through_ball_behind"] / matches,
        "goal_drive_byline": totals["goal_phase_wide_byline_attack_drive"] / matches,
        "goal_byline_delivery": totals["goal_phase_wide_byline_attack_release"] / matches,
        "goal_far_post": totals["goal_attack_far_post"] / matches,
        "goal_on_ball_generic": (
            totals["goal_create_shot"]
            + totals["goal_progress_carry"]
            + totals["goal_protect_ball"]
            + totals["goal_recycle"]
            + totals["goal_switch_play"]
            + totals["goal_through_ball"]
            + totals["goal_clear_danger"]
        ) / matches,
        "goal_off_ball_generic": (
            totals["goal_support_second_line"]
            + totals["goal_drop_between_lines"]
            + totals["goal_support_carrier"]
            + totals["goal_hold_width"]
            + totals["goal_run_behind"]
            + totals["goal_attack_box"]
            + totals["goal_recycle_support"]
        ) / matches,
        "goal_attack_box": totals["goal_attack_box"] / matches,
        "goal_defense": (
            totals["goal_defend_press"]
            + totals["goal_defend_cover_lane"]
            + totals["goal_defend_mark_runner"]
            + totals["goal_defend_protect_box"]
            + totals["goal_defend_recover_shape"]
        ) / matches,
        "goal_switch_cut_inside": totals["goal_switch_cut_inside_to_shoot"] / matches,
        "goal_switch_arc_arrival": totals["goal_switch_arc_arrival_for_cutback"] / matches,
        "goal_switch_wide_hold": totals["goal_switch_wide_hold_for_overlap"] / matches,
        "goal_switch_pressure_layoff": totals["goal_switch_release_pressure_with_layoff"] / matches,
        "goal_switch_release_support": totals["goal_switch_release_to_arriving_support"] / matches,
        "goal_switch_hold_opportunity": totals["goal_switch_hold_for_opportunity"] / matches,
        "goal_switch_far_post": totals["goal_switch_attack_far_post"] / matches,
        "goal_cut_shot": totals["goal_action_cut_inside_to_shoot_shoot"] / matches,
        "goal_cut_carry": totals["goal_action_cut_inside_to_shoot_carry"] / matches,
        "goal_cut_pass": totals["goal_action_cut_inside_to_shoot_pass"] / matches,
        "goal_hold_hold": totals["goal_action_wide_hold_for_overlap_hold"] / matches,
        "goal_hold_pass": totals["goal_action_wide_hold_for_overlap_pass"] / matches,
        "goal_layoff_pass": totals["goal_action_release_pressure_with_layoff_pass"] / matches,
        "goal_release_support_pass": totals["goal_action_release_to_arriving_support_pass"] / matches,
        "goal_through_pass": totals["goal_action_through_ball_behind_pass"] / matches,
        "goal_drive_byline_carry": totals["goal_action_wide_byline_attack_drive_carry"] / matches,
        "goal_byline_pass": totals["goal_action_wide_byline_attack_release_pass"] / matches,
        "goal_opportunity_hold": totals["goal_action_hold_for_opportunity_hold"] / matches,
        "goal_opportunity_pass": totals["goal_action_hold_for_opportunity_pass"] / matches,
        "goal_opportunity_carry": totals["goal_action_hold_for_opportunity_carry"] / matches,
        "goal_cut_follow_shot": totals["goal_follow_cut_inside_to_shoot_shoot"] / matches,
        "goal_cut_follow_carry": totals["goal_follow_cut_inside_to_shoot_carry"] / matches,
        "goal_cut_follow_pass": (
            totals["goal_follow_cut_inside_to_shoot_pass"]
            + totals["goal_follow_cut_inside_to_shoot_pass_to_space"]
        ) / matches,
        "goal_cut_chain4_samples": totals["goal_cut_chain4_samples"] / matches,
        "goal_cut_chain4_shot": totals["goal_cut_chain4_shot"] / matches,
        "goal_cut_chain4_window": totals["goal_cut_chain4_window"] / matches,
        "goal_cut_chain4_best_xg": totals["goal_cut_chain4_best_xg_sum"] / max(1, totals["goal_cut_chain4_samples"]),
        "goal_cut_chain4_best_ready": totals["goal_cut_chain4_best_ready_sum"] / max(1, totals["goal_cut_chain4_samples"]),
        "goal_cut_chain4_end_shot": totals["goal_cut_chain4_end_shot"] / matches,
        "goal_cut_chain4_end_release": totals["goal_cut_chain4_end_release"] / matches,
        "goal_cut_chain4_end_horizon": totals["goal_cut_chain4_end_horizon"] / matches,
        "goal_cut_release_target_progress": totals["goal_cut_release_target_progress_sum"] / cut_release_total,
        "goal_cut_release_target_width": totals["goal_cut_release_target_width_sum"] / cut_release_total,
        "goal_cut_release_to_FW": totals["goal_cut_release_to_FW"] / matches,
        "goal_cut_release_to_WM": totals["goal_cut_release_to_WM"] / matches,
        "goal_cut_release_to_CM": totals["goal_cut_release_to_CM"] / matches,
        "goal_cut_release_to_AM": totals["goal_cut_release_to_AM"] / matches,
        "goal_cut_release_zone_boxC": totals["goal_cut_release_zone_box_center"] / matches,
        "goal_cut_release_zone_arcC": totals["goal_cut_release_zone_arc_center"] / matches,
        "goal_cut_release_zone_fWide": totals["goal_cut_release_zone_final_wide"] / matches,
        "goal_cut_release_zone_recycle": totals["goal_cut_release_zone_recycle"] / matches,
        "goal_cut_drive": totals["goal_phase_cut_inside_to_shoot_drive"] / matches,
        "goal_cut_finish": totals["goal_phase_cut_inside_to_shoot_finish"] / matches,
        "goal_cut_release": totals["goal_phase_cut_inside_to_shoot_release"] / matches,
        "goal_cut_support_dist": sum(row(group)["goal_cut_support_dist_sum"] for group in ("W", "WM", "CM", "AM", "FW")) / cut_support_denom,
        "goal_cut_second_support_dist": sum(row(group)["goal_cut_second_line_support_dist_sum"] for group in ("W", "WM", "CM", "AM", "FW")) / cut_support_denom,
        "goal_cut_forward_support_dist": sum(row(group)["goal_cut_forward_support_dist_sum"] for group in ("W", "WM", "CM", "AM", "FW")) / cut_support_denom,
    }
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        group_row = row(group)
        card["through_candidate_decisions"] = card.get("through_candidate_decisions", 0.0) + group_row["through_decision_samples"] / matches
        card["through_candidate_chosen"] = card.get("through_candidate_chosen", 0.0) + group_row["through_candidate_chosen"] / matches
        card["byline_candidate_decisions"] = card.get("byline_candidate_decisions", 0.0) + group_row["byline_decision_samples"] / matches
        card["byline_candidate_chosen"] = card.get("byline_candidate_chosen", 0.0) + group_row["byline_candidate_chosen"] / matches
    return card


def average_scorecards(cards: list[dict]) -> dict:
    if not cards:
        return {}
    averaged = {}
    keys = cards[0].keys()
    for key in keys:
        if isinstance(cards[0].get(key), str):
            averaged[key] = cards[0].get(key, "")
        else:
            averaged[key] = sum(card.get(key, 0.0) for card in cards) / len(cards)
    role_keys = {
        group: f"arc_role_{group}"
        for group in ("CB", "FB", "DM", "CM", "WM", "FW", "AM")
    }
    if all(key in averaged for key in role_keys.values()):
        arc_roles = {group: averaged[key] for group, key in role_keys.items()}
        arc_main_role = max(arc_roles, key=arc_roles.get) if any(arc_roles.values()) else "NA"
        averaged["arc_main_role"] = arc_main_role
        averaged["arc_main_role_pct"] = (
            arc_roles.get(arc_main_role, 0.0)
            / max(1.0, averaged.get("arc_def_samples", 0.0))
            * 100.0
        )
    return averaged


def print_scorecard_line(name: str, card: dict):
    print(
        f"{name:34s} "
        f"m={card['matches']:.0f} "
        f"g={card['goals']:.2f} sh={card['shots']:.2f} sot={card['sot_pct']:.1f}% pass={card['pass_pct']:.1f}% "
        f"shot% FW/W/WM/CM/DEF={card['fw_shot_pct']:.1f}/{card['w_shot_pct']:.1f}/{card['wm_shot_pct']:.1f}/{card['cm_shot_pct']:.1f}/{card['def_shot_pct']:.1f} "
        f"ft% FW/W/WM/CM={card['fw_ft_touch_pct']:.1f}/{card['w_ft_touch_pct']:.1f}/{card['wm_ft_touch_pct']:.1f}/{card['cm_ft_touch_pct']:.1f} "
        f"ftRecv% FW/W/WM/CM={card['fw_ft_receive_pct']:.1f}/{card['w_ft_receive_pct']:.1f}/{card['wm_ft_receive_pct']:.1f}/{card['cm_ft_receive_pct']:.1f} "
        f"c3p={card['c3p_shots']:.1f} c3next C/P/S={card['chain3_carry']:.1f}/{card['chain3_pass']:.1f}/{card['chain3_shot']:.1f} "
        f"def near={card['def_nearest']:.2f} c6={card['def_close6']:.2f} c8={card['def_close8']:.2f} "
        f"rest act/tgt/anc/max/front={card['rest_actual']:.2f}/{card['rest_target']:.2f}/{card['rest_anchor']:.2f}/{card['rest_actual_max']:.2f}/{card['rest_opp_front']:.2f} "
        f"arc 2L/2Lt/2La/def/role/2L10/2Lt10/2La10/lowP/ready/only2L/onlyP/none/sync2L/syncP={card['arc_second_line']:.1f}/{card['arc_second_line_target']:.1f}/{card['arc_second_line_anchor']:.1f}/{card['arc_def']:.1f}/{card['arc_main_role']}:{card['arc_main_role_pct']:.0f}%/{card['arc_second_line_close_pct']:.0f}%/{card['arc_second_line_target_close_pct']:.0f}%/{card['arc_second_line_anchor_close_pct']:.0f}%/{card['arc_low_pressure_pct']:.0f}%/{card['arc_ready_pct']:.0f}%/{card['arc_only_second_line_pct']:.0f}%/{card['arc_only_low_pressure_pct']:.0f}%/{card['arc_neither_pct']:.0f}%/{card['arc_only2l_sync_pct']:.0f}%/{card['arc_onlyp_sync_pct']:.0f}% "
        f"chain W-FW-2L-S/nextC/P/H={card['wide_to_fw']:.1f}/{card['fw_layoff_second']:.1f}/{card['layoff_second_shot']:.1f}/{card['layoff_next_carry']:.1f}/{card['layoff_next_pass']:.1f}/{card['layoff_next_hold']:.1f} "
        f"ftAct FW S/P/C={card['fw_ft_shot']:.1f}/{card['fw_ft_pass']:.1f}/{card['fw_ft_carry']:.1f} "
        f"W={card['w_ft_shot']:.1f}/{card['w_ft_pass']:.1f}/{card['w_ft_carry']:.1f} "
        f"WM={card['wm_ft_shot']:.1f}/{card['wm_ft_pass']:.1f}/{card['wm_ft_carry']:.1f} "
        f"CM={card['cm_ft_shot']:.1f}/{card['cm_ft_pass']:.1f}/{card['cm_ft_carry']:.1f} "
        f"goals cut/arc/hold/layoff/relSup/opp/th/byD/byl/far/box={card['goal_cut_inside']:.1f}/{card['goal_arc_arrival']:.1f}/{card['goal_wide_hold']:.1f}/{card['goal_pressure_layoff']:.1f}/{card['goal_release_support']:.1f}/{card['goal_hold_opportunity']:.1f}/{card['goal_through_behind']:.1f}/{card['goal_drive_byline']:.1f}/{card['goal_byline_delivery']:.1f}/{card['goal_far_post']:.1f}/{card['goal_attack_box']:.1f} "
        f"goalFam O/OFF/D={card['goal_on_ball_generic']:.0f}/{card['goal_off_ball_generic']:.0f}/{card['goal_defense']:.0f} "
        f"sw={card['goal_switch_cut_inside']:.1f}/{card['goal_switch_arc_arrival']:.1f}/{card['goal_switch_wide_hold']:.1f}/{card['goal_switch_pressure_layoff']:.1f}/{card['goal_switch_release_support']:.1f}/{card['goal_switch_hold_opportunity']:.1f}/{card['goal_switch_far_post']:.1f} "
        f"gAct cut S/C/P={card['goal_cut_shot']:.1f}/{card['goal_cut_carry']:.1f}/{card['goal_cut_pass']:.1f} "
        f"cutNext S/C/P={card['goal_cut_follow_shot']:.1f}/{card['goal_cut_follow_carry']:.1f}/{card['goal_cut_follow_pass']:.1f} "
        f"cut4 S/W/xG/R={card['goal_cut_chain4_shot']:.1f}/{card['goal_cut_chain4_window']:.1f}/{card['goal_cut_chain4_best_xg']:.2f}/{card['goal_cut_chain4_best_ready']:.2f} "
        f"cutPhase D/F/R={card['goal_cut_drive']:.1f}/{card['goal_cut_finish']:.1f}/{card['goal_cut_release']:.1f} "
        f"hold H/P={card['goal_hold_hold']:.1f}/{card['goal_hold_pass']:.1f} layP={card['goal_layoff_pass']:.1f} relSupP={card['goal_release_support_pass']:.1f} thP={card['goal_through_pass']:.1f} bylP={card['goal_byline_pass']:.1f} "
        f"opp H/P/C={card['goal_opportunity_hold']:.1f}/{card['goal_opportunity_pass']:.1f}/{card['goal_opportunity_carry']:.1f}"
    )


def _band(value: float, low: float, high: float, reverse: bool = False) -> str:
    if reverse:
        if value <= low:
            return "OK"
        if value <= high:
            return "WARN"
        return "BAD"
    if value >= high:
        return "OK"
    if value >= low:
        return "WARN"
    return "BAD"


def print_health_line(name: str, card: dict):
    non_fw_shot = 100.0 - card["fw_shot_pct"]
    width_touch = card["w_ft_touch_pct"] + card["wm_ft_touch_pct"]
    second_touch = card["wm_ft_touch_pct"] + card["cm_ft_touch_pct"]
    second_receive = card["wm_ft_receive_pct"] + card["cm_ft_receive_pct"]
    rest_gap = card["rest_actual_max"] - card["rest_opp_front"]
    cut_finish_rate = card["goal_cut_shot"] / max(1.0, card["goal_cut_inside"]) * 100.0
    cut_next_shot_rate = card["goal_cut_follow_shot"] / max(1.0, card["goal_cut_carry"]) * 100.0
    cut_chain_window_rate = card["goal_cut_chain4_window"] / max(1.0, card["goal_cut_chain4_samples"]) * 100.0
    print(
        f"{name:34s} "
        f"shots={card['shots']:.2f}({_band(card['shots'], 4.0, 8.0)}) "
        f"nonFW%={non_fw_shot:.1f}({_band(non_fw_shot, 12.0, 30.0)}) "
        f"wideFT%={width_touch:.1f}({_band(width_touch, 25.0, 45.0)}) "
        f"2LFT%={second_touch:.1f}({_band(second_touch, 10.0, 25.0)}) "
        f"2LRecv%={second_receive:.1f}({_band(second_receive, 8.0, 22.0)}) "
        f"restGap={rest_gap:.2f}({_band(rest_gap, 0.18, 0.30, reverse=True)}) "
        f"arcReady={card['arc_ready_pct']:.0f}%({_band(card['arc_ready_pct'], 8.0, 20.0)}) "
        f"arcBand={card['arc_band_ready_pct']:.0f}%({_band(card['arc_band_ready_pct'], 12.0, 28.0)}) "
        f"arcParts={card['arc_only_second_line_pct']:.0f}/{card['arc_only_low_pressure_pct']:.0f}/{card['arc_neither_pct']:.0f} "
        f"goalFam O/OFF/D={card['goal_on_ball_generic']:.0f}/{card['goal_off_ball_generic']:.0f}/{card['goal_defense']:.0f} "
        f"cutS={cut_finish_rate:.0f}%({_band(cut_finish_rate, 8.0, 20.0)}) "
        f"cutNextS={cut_next_shot_rate:.0f}%({_band(cut_next_shot_rate, 5.0, 15.0)}) "
        f"cut4W={cut_chain_window_rate:.0f}%({_band(cut_chain_window_rate, 20.0, 45.0)}) "
        f"cutEnd S/R/H={card['goal_cut_chain4_end_shot']:.1f}/{card['goal_cut_chain4_end_release']:.1f}/{card['goal_cut_chain4_end_horizon']:.1f} "
        f"cutBest xG/R={card['goal_cut_chain4_best_xg']:.2f}/{card['goal_cut_chain4_best_ready']:.2f} "
        f"cutRel P/W={card['goal_cut_release_target_progress']:.2f}/{card['goal_cut_release_target_width']:.2f} "
        f"to F/W/C/A={card['goal_cut_release_to_FW']:.1f}/{card['goal_cut_release_to_WM']:.1f}/{card['goal_cut_release_to_CM']:.1f}/{card['goal_cut_release_to_AM']:.1f} "
        f"cutSup={card['goal_cut_support_dist']:.1f}/{card['goal_cut_second_support_dist']:.1f}/{card['goal_cut_forward_support_dist']:.1f} "
        f"th c/ch/g/a={card.get('through_candidate_decisions', 0.0):.1f}/{card.get('through_candidate_chosen', 0.0):.1f}/{card['goal_through_behind']:.1f}/{card['goal_through_pass']:.1f} "
        f"byD g/a={card['goal_drive_byline']:.1f}/{card['goal_drive_byline_carry']:.1f} "
        f"byl c/ch/g/a={card.get('byline_candidate_decisions', 0.0):.1f}/{card.get('byline_candidate_chosen', 0.0):.1f}/{card['goal_byline_delivery']:.1f}/{card['goal_byline_pass']:.1f}"
    )


def _avg_candidate_score(row: Counter, action_type: str) -> float:
    samples = row[f"ft_candidate_{action_type}_samples"]
    if samples <= 0:
        return 0.0
    return row[f"ft_candidate_{action_type}_score_sum"] / samples


def print_decision_report(aggregate):
    print()
    print("GOAL TRACE SUMMARY")
    print("role cut arc hold layoff opp far box | cut S/C/P next S/C/P phase D/F/R cutCarry tgtP/tgtW good/mid/wide fGain/c2shot/w2L bucket fGain good/mid/wide path good/mid/wide risk perp/threat/ctrl tgt def10/def14/nearD/support hold H/P layP opp H/P/C")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        if not row:
            continue
        total_goals = (
            row["goal_cut_inside_to_shoot"]
            + row["goal_arc_arrival_for_cutback"]
            + row["goal_wide_hold_for_overlap"]
            + row["goal_release_pressure_with_layoff"]
            + row["goal_hold_for_opportunity"]
            + row["goal_attack_far_post"]
            + row["goal_attack_box"]
        )
        if total_goals <= 0:
            continue
        print(
            f"{group:5s} "
            f"{row['goal_cut_inside_to_shoot']:3.0f} "
            f"{row['goal_arc_arrival_for_cutback']:3.0f} "
            f"{row['goal_wide_hold_for_overlap']:4.0f} "
            f"{row['goal_release_pressure_with_layoff']:6.0f} "
            f"{row['goal_hold_for_opportunity']:3.0f} "
            f"{row['goal_attack_far_post']:3.0f} "
            f"{row['goal_attack_box']:3.0f} | "
            f"{row['goal_action_cut_inside_to_shoot_shoot']:3.0f} "
            f"{row['goal_action_cut_inside_to_shoot_carry']:3.0f} "
            f"{row['goal_action_cut_inside_to_shoot_pass']:3.0f} "
            f"{row['goal_follow_cut_inside_to_shoot_shoot']:3.0f} "
            f"{row['goal_follow_cut_inside_to_shoot_carry']:3.0f} "
            f"{row['goal_follow_cut_inside_to_shoot_pass'] + row['goal_follow_cut_inside_to_shoot_pass_to_space']:3.0f} "
            f"{row['goal_phase_cut_inside_to_shoot_drive']:3.0f} "
            f"{row['goal_phase_cut_inside_to_shoot_finish']:3.0f} "
            f"{row['goal_phase_cut_inside_to_shoot_release']:3.0f} "
            f"{row['goal_cut_carry_target_progress_sum']/max(1, row['goal_cut_carry_samples']):4.2f}/"
            f"{row['goal_cut_carry_target_width_sum']/max(1, row['goal_cut_carry_samples']):4.2f} "
            f"{row['goal_cut_carry_target_good']:3.0f}/"
            f"{row['goal_cut_carry_target_mid']:3.0f}/"
            f"{row['goal_cut_carry_target_wide']:3.0f} "
            f"{row['goal_cut_carry_future_shot_gain_sum']/max(1, row['goal_cut_carry_samples']):4.3f}/"
            f"{row['goal_cut_carry_carry_to_shoot_window_sum']/max(1, row['goal_cut_carry_samples']):4.3f}/"
            f"{row['goal_cut_carry_wide_second_line_carry_window_sum']/max(1, row['goal_cut_carry_samples']):4.3f} "
            f"{row['goal_cut_carry_good_future_shot_gain_sum']/max(1, row['goal_cut_carry_target_good']):4.3f}/"
            f"{row['goal_cut_carry_mid_future_shot_gain_sum']/max(1, row['goal_cut_carry_target_mid']):4.3f}/"
            f"{row['goal_cut_carry_wide_future_shot_gain_sum']/max(1, row['goal_cut_carry_target_wide']):4.3f} "
            f"{row['goal_cut_carry_good_path_feasibility_sum']/max(1, row['goal_cut_carry_target_good']):4.2f}/"
            f"{row['goal_cut_carry_mid_path_feasibility_sum']/max(1, row['goal_cut_carry_target_mid']):4.2f}/"
            f"{row['goal_cut_carry_wide_path_feasibility_sum']/max(1, row['goal_cut_carry_target_wide']):4.2f} "
            f"{row['goal_cut_carry_path_min_perp_sum']/max(1, row['goal_cut_carry_samples']):4.1f}/"
            f"{row['goal_cut_carry_path_peak_threat_sum']/max(1, row['goal_cut_carry_samples']):4.2f}/"
            f"{row['goal_cut_carry_path_peak_final_third_control_sum']/max(1, row['goal_cut_carry_samples']):4.2f} "
            f"{row['goal_cut_carry_target_def10_sum']/max(1, row['goal_cut_carry_samples']):4.1f}/"
            f"{row['goal_cut_carry_target_def14_sum']/max(1, row['goal_cut_carry_samples']):4.1f}/"
            f"{row['goal_cut_carry_target_nearest_def_sum']/max(1, row['goal_cut_carry_samples']):4.1f}/"
            f"{row['goal_cut_carry_target_support_sum']/max(1, row['goal_cut_carry_samples']):4.1f} "
            f"{row['goal_action_wide_hold_for_overlap_hold']:4.0f} "
            f"{row['goal_action_wide_hold_for_overlap_pass']:3.0f} "
            f"{row['goal_action_release_pressure_with_layoff_pass']:5.0f} "
            f"{row['goal_action_hold_for_opportunity_hold']:3.0f}/"
            f"{row['goal_action_hold_for_opportunity_pass']:3.0f}/"
            f"{row['goal_action_hold_for_opportunity_carry']:3.0f}"
        )
    print()
    print("THROUGH/BYLINE CANDIDATES")
    print("role through decisions/cand/chosen/goal/action best/score/succ/press/lane/high | byline decisions/cand/chosen/goal/action best/score/succ/press/lane/high")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        if not row:
            continue
        through_decisions = row["through_decision_samples"]
        byline_decisions = row["byline_decision_samples"]
        if (
            through_decisions <= 0
            and byline_decisions <= 0
            and row["goal_through_ball_behind"] <= 0
            and row["goal_phase_wide_byline_attack_release"] <= 0
        ):
            continue
        through_cands = max(1, row["through_candidate_samples"])
        through_dec = max(1, through_decisions)
        byline_cands = max(1, row["byline_candidate_samples"])
        byline_dec = max(1, byline_decisions)
        print(
            f"{group:5s} "
            f"{through_decisions:3.0f}/{row['through_candidate_samples']:3.0f}/{row['through_candidate_chosen']:3.0f}/"
            f"{row['goal_through_ball_behind']:3.0f}/{row['goal_action_through_ball_behind_pass']:3.0f} "
            f"{row['through_best_score_sum']/through_dec:5.3f}/"
            f"{row['through_candidate_score_sum']/through_cands:5.3f}/"
            f"{row['through_candidate_success_sum']/through_cands:4.2f}/"
            f"{row['through_candidate_pressure_sum']/through_cands:4.2f}/"
            f"{row['through_candidate_lane_sum']/through_cands:4.2f}/"
            f"{row['through_candidate_high_sum']/through_cands:4.2f} | "
            f"{byline_decisions:3.0f}/{row['byline_candidate_samples']:3.0f}/{row['byline_candidate_chosen']:3.0f}/"
            f"{row['goal_phase_wide_byline_attack_release']:3.0f}/{row['goal_action_wide_byline_attack_release_pass']:3.0f} "
            f"{row['byline_best_score_sum']/byline_dec:5.3f}/"
            f"{row['byline_candidate_score_sum']/byline_cands:5.3f}/"
            f"{row['byline_candidate_success_sum']/byline_cands:4.2f}/"
            f"{row['byline_candidate_pressure_sum']/byline_cands:4.2f}/"
            f"{row['byline_candidate_lane_sum']/byline_cands:4.2f}/"
            f"{row['byline_candidate_high_sum']/byline_cands:4.2f}"
        )
    print()
    print("CUT OFF-BALL SUPPORT SUMMARY")
    print("role samples deep% score/deep support/deep second/deep reach/deep pass/deep shape/deep")
    for group in ("FW", "W", "WM", "CM", "AM"):
        row = aggregate.get(group)
        if not row or row["cut_offball_samples"] <= 0:
            continue
        samples = max(1, row["cut_offball_samples"])
        deep = max(1, row["cut_offball_deep_chosen"])
        print(
            f"{group:5s} "
            f"{row['cut_offball_samples']:7.0f} "
            f"{row['cut_offball_deep_chosen']/samples*100:5.1f} "
            f"{row['cut_offball_score_sum']/samples:5.3f}/"
            f"{row['cut_offball_deep_score_sum']/deep:5.3f} "
            f"{row['cut_offball_support_angle_value_sum']/samples:5.3f}/"
            f"{row['cut_offball_deep_support_angle_value_sum']/deep:5.3f} "
            f"{row['cut_offball_second_line_support_sum']/samples:5.3f}/"
            f"{row['cut_offball_deep_second_line_support_sum']/deep:5.3f} "
            f"{row['cut_offball_reach_sum']/samples:5.3f}/"
            f"{row['cut_offball_deep_reach_sum']/deep:5.3f} "
            f"{row['cut_offball_pass_feasibility_sum']/samples:5.3f}/"
            f"{row['cut_offball_deep_pass_feasibility_sum']/deep:5.3f} "
            f"{row['cut_offball_role_shape_factor_sum']/samples:5.3f}/"
            f"{row['cut_offball_deep_role_shape_factor_sum']/deep:5.3f}"
        )
    print()
    print("FINAL THIRD DECISION TRACE")
    print("role samples loc x/w/def chosen S/P/C/H avg_candidate S/P/C/H chosen_loc Sx/Sw Px/Pw Cx/Cw target Pt/Pw Ct/Cw")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        if not row or not row["ft_decision_samples"]:
            continue
        chosen_pass = (
            row["ft_decision_chosen_pass"]
            + row["ft_decision_chosen_short_pass"]
            + row["ft_decision_chosen_long_pass"]
            + row["ft_decision_chosen_pass_to_space"]
        )
        pass_score_sum = (
            row["ft_candidate_pass_score_sum"]
            + row["ft_candidate_short_pass_score_sum"]
            + row["ft_candidate_long_pass_score_sum"]
            + row["ft_candidate_pass_to_space_score_sum"]
        )
        pass_samples = (
            row["ft_candidate_pass_samples"]
            + row["ft_candidate_short_pass_samples"]
            + row["ft_candidate_long_pass_samples"]
            + row["ft_candidate_pass_to_space_samples"]
        )
        pass_avg = pass_score_sum / pass_samples if pass_samples else 0.0
        samples = max(1, row["ft_decision_samples"])
        nearest_samples = max(1, row["ft_decision_nearest_def_samples"])

        def chosen_loc(action: str) -> tuple[float, float]:
            count = row[f"ft_decision_chosen_{action}_samples"]
            if count <= 0:
                return (0.0, 0.0)
            return (
                row[f"ft_decision_chosen_{action}_progress_sum"] / count,
                row[f"ft_decision_chosen_{action}_width_sum"] / count,
            )

        def target_loc(action: str) -> tuple[float, float]:
            count = row[f"ft_decision_chosen_{action}_target_samples"]
            if count <= 0:
                return (0.0, 0.0)
            return (
                row[f"ft_decision_chosen_{action}_target_progress_sum"] / count,
                row[f"ft_decision_chosen_{action}_target_width_sum"] / count,
            )

        sx, sw = chosen_loc("shoot")
        px_short, pw_short = chosen_loc("short_pass")
        px_long, pw_long = chosen_loc("long_pass")
        px_space, pw_space = chosen_loc("pass_to_space")
        pass_count = (
            row["ft_decision_chosen_short_pass_samples"]
            + row["ft_decision_chosen_long_pass_samples"]
            + row["ft_decision_chosen_pass_to_space_samples"]
        )
        if pass_count > 0:
            px = (
                row["ft_decision_chosen_short_pass_progress_sum"]
                + row["ft_decision_chosen_long_pass_progress_sum"]
                + row["ft_decision_chosen_pass_to_space_progress_sum"]
            ) / pass_count
            pw = (
                row["ft_decision_chosen_short_pass_width_sum"]
                + row["ft_decision_chosen_long_pass_width_sum"]
                + row["ft_decision_chosen_pass_to_space_width_sum"]
            ) / pass_count
        else:
            px = px_short + px_long + px_space
            pw = pw_short + pw_long + pw_space
        pass_target_count = (
            row["ft_decision_chosen_short_pass_target_samples"]
            + row["ft_decision_chosen_long_pass_target_samples"]
            + row["ft_decision_chosen_pass_to_space_target_samples"]
        )
        if pass_target_count > 0:
            ptx = (
                row["ft_decision_chosen_short_pass_target_progress_sum"]
                + row["ft_decision_chosen_long_pass_target_progress_sum"]
                + row["ft_decision_chosen_pass_to_space_target_progress_sum"]
            ) / pass_target_count
            ptw = (
                row["ft_decision_chosen_short_pass_target_width_sum"]
                + row["ft_decision_chosen_long_pass_target_width_sum"]
                + row["ft_decision_chosen_pass_to_space_target_width_sum"]
            ) / pass_target_count
        else:
            ptx = 0.0
            ptw = 0.0
        cx, cw = chosen_loc("carry")
        ctx, ctw = target_loc("carry")
        print(
            f"{group:5s} "
            f"{row['ft_decision_samples']:7.0f} "
            f"{row['ft_decision_progress_sum']/samples:4.2f}/"
            f"{row['ft_decision_width_sum']/samples:4.2f}/"
            f"{row['ft_decision_nearest_def_sum']/nearest_samples:4.1f} "
            f"{row['ft_decision_chosen_shoot']:6.0f} "
            f"{chosen_pass:5.0f} "
            f"{row['ft_decision_chosen_carry']:5.0f} "
            f"{row['ft_decision_chosen_hold']:5.0f} "
            f"{_avg_candidate_score(row, 'shoot'):6.3f} "
            f"{pass_avg:5.3f} "
            f"{_avg_candidate_score(row, 'carry'):5.3f} "
            f"{_avg_candidate_score(row, 'hold'):5.3f} "
            f"{sx:4.2f}/{sw:4.2f} "
            f"{px:4.2f}/{pw:4.2f} "
            f"{cx:4.2f}/{cw:4.2f} "
            f"{ptx:4.2f}/{ptw:4.2f} "
            f"{ctx:4.2f}/{ctw:4.2f}"
        )
    print()
    print("FINAL THIRD PASS TOPOLOGY")
    print("role samples to FW/W/WM/CM/AM kind feet/space zone boxC/arcC/fWide/recycle tgt P/W score delta/succ/press/lane values high/comb/2L/cutback/release shotCost")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        samples = row["ft_pass_topology_samples"] if row else 0
        if not row or samples <= 0:
            continue
        samples = max(1, samples)
        target_progress = row["ft_pass_target_progress_sum"] / samples
        target_width = row["ft_pass_target_width_sum"] / samples
        feet = row["ft_pass_kind_feet"]
        space = row["ft_pass_kind_space"]
        print(
            f"{group:5s} "
            f"{samples:7.0f} "
            f"{row['ft_pass_to_FW']:3.0f}/"
            f"{row['ft_pass_to_W']:3.0f}/"
            f"{row['ft_pass_to_WM']:3.0f}/"
            f"{row['ft_pass_to_CM']:3.0f}/"
            f"{row['ft_pass_to_AM']:3.0f} "
            f"{feet:4.0f}/{space:5.0f} "
            f"{row['ft_pass_zone_box_center']:4.0f}/"
            f"{row['ft_pass_zone_arc_center']:4.0f}/"
            f"{row['ft_pass_zone_final_wide']:5.0f}/"
            f"{row['ft_pass_zone_recycle']:7.0f} "
            f"{target_progress:4.2f}/{target_width:4.2f} "
            f"{row['ft_pass_score_sum']/samples:5.3f} "
            f"{row['ft_pass_delta_sum']/samples:5.3f}/"
            f"{row['ft_pass_success_prob_sum']/samples:4.2f}/"
            f"{row['ft_pass_receiver_pressure_sum']/samples:4.2f}/"
            f"{row['ft_pass_lane_risk_sum']/samples:4.2f} "
            f"{row['ft_pass_high_threat_space_sum']/samples:4.2f}/"
            f"{row['ft_pass_final_third_combination_sum']/samples:4.2f}/"
            f"{(row['ft_pass_second_line_arrival_value_sum'] + row['ft_pass_second_line_cutback_value_sum'])/samples:5.3f}/"
            f"{row['ft_pass_cutback_value_sum']/samples:5.3f}/"
            f"{(row['ft_pass_pressure_release_value_sum'] + row['ft_pass_stale_release_value_sum'])/samples:5.3f} "
            f"{row['ft_pass_shoot_window_release_cost_sum']/samples:5.3f}"
        )
    print()
    print("FINAL THIRD BEST CANDIDATES")
    print("role bestScore S/P/C/H bestTarget Ptx/Ptw Ctx/Ctw shot xG/open/press/lane/dist")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        if not row or not row["ft_decision_samples"]:
            continue

        def best_score(action: str) -> float:
            samples = row[f"ft_best_{action}_samples"]
            if samples <= 0:
                return 0.0
            return row[f"ft_best_{action}_score_sum"] / samples

        def best_target(action: str) -> tuple[float, float]:
            samples = row[f"ft_best_{action}_target_samples"]
            if samples <= 0:
                return (0.0, 0.0)
            return (
                row[f"ft_best_{action}_target_progress_sum"] / samples,
                row[f"ft_best_{action}_target_width_sum"] / samples,
            )

        pass_samples = (
            row["ft_best_pass_samples"]
            + row["ft_best_short_pass_samples"]
            + row["ft_best_long_pass_samples"]
            + row["ft_best_pass_to_space_samples"]
        )
        pass_score = 0.0
        ptx = 0.0
        ptw = 0.0
        if pass_samples:
            pass_score = (
                row["ft_best_pass_score_sum"]
                + row["ft_best_short_pass_score_sum"]
                + row["ft_best_long_pass_score_sum"]
                + row["ft_best_pass_to_space_score_sum"]
            ) / pass_samples
            ptarget_samples = (
                row["ft_best_pass_target_samples"]
                + row["ft_best_short_pass_target_samples"]
                + row["ft_best_long_pass_target_samples"]
                + row["ft_best_pass_to_space_target_samples"]
            )
            if ptarget_samples:
                ptx = (
                    row["ft_best_pass_target_progress_sum"]
                    + row["ft_best_short_pass_target_progress_sum"]
                    + row["ft_best_long_pass_target_progress_sum"]
                    + row["ft_best_pass_to_space_target_progress_sum"]
                ) / ptarget_samples
                ptw = (
                    row["ft_best_pass_target_width_sum"]
                    + row["ft_best_short_pass_target_width_sum"]
                    + row["ft_best_long_pass_target_width_sum"]
                    + row["ft_best_pass_to_space_target_width_sum"]
                ) / ptarget_samples
        ctx, ctw = best_target("carry")
        shot_samples = max(1, row["ft_best_shoot_component_samples"])
        print(
            f"{group:5s} "
            f"{best_score('shoot'):6.3f} "
            f"{pass_score:5.3f} "
            f"{best_score('carry'):5.3f} "
            f"{best_score('hold'):5.3f} "
            f"{ptx:4.2f}/{ptw:4.2f} "
            f"{ctx:4.2f}/{ctw:4.2f} "
            f"{row['ft_best_shoot_xg_sum']/shot_samples:4.3f}/"
            f"{row['ft_best_shoot_open_medium_window_sum']/shot_samples:4.2f}/"
            f"{row['ft_best_shoot_pressure_factor_sum']/shot_samples:4.2f}/"
            f"{row['ft_best_shoot_lane_factor_sum']/shot_samples:4.2f}/"
            f"{row['ft_best_shoot_distance_sum']/shot_samples:4.1f}"
        )
    print()
    print("HOLD FOR OPPORTUNITY DECISIONS")
    print("role samples age chosen P/C/S/H mature P/C/S/H best P/C/S/H")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        samples = row["hold_goal_decision_samples"] if row else 0
        if not row or samples <= 0:
            continue
        samples = max(1, samples)
        mature = max(1, row["hold_goal_mature_samples"])
        print(
            f"{group:5s} "
            f"{samples:7.0f} "
            f"{row['hold_goal_age_sum']/samples:4.1f} "
            f"{row['hold_goal_chosen_pass'] + row['hold_goal_chosen_short_pass'] + row['hold_goal_chosen_long_pass'] + row['hold_goal_chosen_pass_to_space']:4.0f}/"
            f"{row['hold_goal_chosen_carry']:1.0f}/"
            f"{row['hold_goal_chosen_shoot']:1.0f}/"
            f"{row['hold_goal_chosen_hold']:1.0f} "
            f"{row['hold_goal_mature_chosen_pass'] + row['hold_goal_mature_chosen_short_pass'] + row['hold_goal_mature_chosen_long_pass'] + row['hold_goal_mature_chosen_pass_to_space']:4.0f}/"
            f"{row['hold_goal_mature_chosen_carry']:1.0f}/"
            f"{row['hold_goal_mature_chosen_shoot']:1.0f}/"
            f"{row['hold_goal_mature_chosen_hold']:1.0f} "
            f"{row['hold_goal_best_pass_score_sum']/samples:5.3f}/"
            f"{row['hold_goal_best_carry_score_sum']/samples:5.3f}/"
            f"{row['hold_goal_best_shoot_score_sum']/samples:5.3f}/"
            f"{row['hold_goal_best_hold_score_sum']/samples:5.3f}"
        )
    print()
    print("FINAL THIRD SECOND-LINE PASS PRESSURE")
    print("role samples wins% chosen 2P/otherP/C/S/H avgScore/fit/2L/gap")
    for group in ("FW", "W", "WM", "CM", "AM", "FB"):
        row = aggregate.get(group)
        samples = row["ft_second_pass_candidate_samples"] if row else 0
        if not row or samples <= 0:
            continue
        samples = max(1, samples)
        print(
            f"{group:5s} "
            f"{samples:7.0f} "
            f"{row['ft_second_pass_wins_value']/samples*100:5.1f}% "
            f"{row['ft_second_pass_chosen_second_pass']:4.0f}/"
            f"{row['ft_second_pass_chosen_other_pass']:6.0f}/"
            f"{row['ft_second_pass_chosen_carry']:1.0f}/"
            f"{row['ft_second_pass_chosen_shoot']:1.0f}/"
            f"{row['ft_second_pass_chosen_hold']:1.0f} "
            f"{row['ft_second_pass_candidate_score_sum']/samples:6.3f}/"
            f"{row['ft_second_pass_candidate_fit_sum']/samples:4.2f}/"
            f"{row['ft_second_pass_candidate_value_sum']/samples:5.3f}/"
            f"{row['ft_second_pass_gap_sum']/samples:5.3f}"
        )
    print()
    print("FW LAYOFF SECOND-LINE DECISIONS")
    print("role decisionSamples loc x/w/def chosen S/C/P/H best S/P/C/H passT carryT shot xG/open/press/lane/dist")
    for group in ("CM", "WM", "AM"):
        row = aggregate.get(group)
        if not row or not row["fw_layoff_decision_samples"]:
            continue
        decision_samples = max(1, row["fw_layoff_decision_samples"])
        nearest_samples = max(1, row["fw_layoff_nearest_def_samples"])
        shot_samples = max(1, row["fw_layoff_best_shoot_component_samples"])
        next_pass = (
            row["fw_layoff_next_pass"]
            + row["fw_layoff_next_short_pass"]
            + row["fw_layoff_next_long_pass"]
            + row["fw_layoff_next_pass_to_space"]
        )
        chosen_pass = (
            row["fw_layoff_chosen_pass"]
            + row["fw_layoff_chosen_short_pass"]
            + row["fw_layoff_chosen_long_pass"]
            + row["fw_layoff_chosen_pass_to_space"]
        )

        def layoff_best_score(action: str) -> float:
            samples = row[f"fw_layoff_best_{action}_samples"]
            if samples <= 0:
                return 0.0
            return row[f"fw_layoff_best_{action}_score_sum"] / samples

        def layoff_best_target(action: str) -> tuple[float, float]:
            samples = row[f"fw_layoff_best_{action}_target_samples"]
            if samples <= 0:
                return (0.0, 0.0)
            return (
                row[f"fw_layoff_best_{action}_target_progress_sum"] / samples,
                row[f"fw_layoff_best_{action}_target_width_sum"] / samples,
            )

        pass_samples = (
            row["fw_layoff_best_pass_samples"]
            + row["fw_layoff_best_short_pass_samples"]
            + row["fw_layoff_best_long_pass_samples"]
            + row["fw_layoff_best_pass_to_space_samples"]
        )
        pass_score = 0.0
        pass_target_progress = 0.0
        pass_target_width = 0.0
        if pass_samples:
            pass_score = (
                row["fw_layoff_best_pass_score_sum"]
                + row["fw_layoff_best_short_pass_score_sum"]
                + row["fw_layoff_best_long_pass_score_sum"]
                + row["fw_layoff_best_pass_to_space_score_sum"]
            ) / pass_samples
            pass_target_samples = (
                row["fw_layoff_best_pass_target_samples"]
                + row["fw_layoff_best_short_pass_target_samples"]
                + row["fw_layoff_best_long_pass_target_samples"]
                + row["fw_layoff_best_pass_to_space_target_samples"]
            )
            if pass_target_samples:
                pass_target_progress = (
                    row["fw_layoff_best_pass_target_progress_sum"]
                    + row["fw_layoff_best_short_pass_target_progress_sum"]
                    + row["fw_layoff_best_long_pass_target_progress_sum"]
                    + row["fw_layoff_best_pass_to_space_target_progress_sum"]
                ) / pass_target_samples
                pass_target_width = (
                    row["fw_layoff_best_pass_target_width_sum"]
                    + row["fw_layoff_best_short_pass_target_width_sum"]
                    + row["fw_layoff_best_long_pass_target_width_sum"]
                    + row["fw_layoff_best_pass_to_space_target_width_sum"]
                ) / pass_target_samples
        carry_target_progress, carry_target_width = layoff_best_target("carry")
        print(
            f"{group:5s} "
            f"{row['fw_layoff_decision_samples']:7.0f} "
            f"{row['fw_layoff_decision_progress_sum']/decision_samples:4.2f}/"
            f"{row['fw_layoff_decision_width_sum']/decision_samples:4.2f}/"
            f"{row['fw_layoff_nearest_def_sum']/nearest_samples:4.1f} "
            f"{row['fw_layoff_chosen_shoot']:4.0f} "
            f"{row['fw_layoff_chosen_carry']:4.0f} "
            f"{chosen_pass:4.0f} "
            f"{row['fw_layoff_chosen_hold']:4.0f} "
            f"{row['fw_layoff_best_shoot_score_sum']/shot_samples:6.3f}/"
            f"{pass_score:5.3f}/"
            f"{layoff_best_score('carry'):5.3f}/"
            f"{layoff_best_score('hold'):5.3f} "
            f"{pass_target_progress:4.2f}/{pass_target_width:4.2f} "
            f"{carry_target_progress:4.2f}/{carry_target_width:4.2f} "
            f"{row['fw_layoff_best_shoot_xg_sum']/shot_samples:4.3f}/"
            f"{row['fw_layoff_best_shoot_open_medium_window_sum']/shot_samples:4.2f}/"
            f"{row['fw_layoff_best_shoot_pressure_factor_sum']/shot_samples:4.2f}/"
            f"{row['fw_layoff_best_shoot_lane_factor_sum']/shot_samples:4.2f}/"
            f"{row['fw_layoff_best_shoot_distance_sum']/shot_samples:4.1f}"
        )
    print()
    print("FT CARRY FOLLOW-UP")
    print("role actionNext S/C/P/H decisionNext S/C/P/H carry actual/target/gap bestCarry fShotGain/c2shot/w2L")
    for group in ("W", "WM", "CM", "AM"):
        row = aggregate.get(group)
        if not row:
            continue
        next_pass = row["ft_carry_next_short_pass"] + row["ft_carry_next_long_pass"] + row["ft_carry_next_pass_to_space"]
        next_total = row["ft_carry_next_shot"] + row["ft_carry_next_carry"] + next_pass + row["ft_carry_next_hold"]
        decision_next_pass = (
            row["ft_carry_decision_next_pass"]
            + row["ft_carry_decision_next_pass_to_space"]
            + row["ft_carry_decision_next_short_pass"]
            + row["ft_carry_decision_next_long_pass"]
        )
        decision_next_total = (
            row["ft_carry_decision_next_shoot"]
            + row["ft_carry_decision_next_carry"]
            + decision_next_pass
            + row["ft_carry_decision_next_hold"]
        )
        samples = row["ft_best_carry_window_component_samples"]
        if next_total <= 0 and decision_next_total <= 0 and samples <= 0:
            continue
        denom = max(1, samples)
        carry_gap_samples = max(1, row["ft_carry_target_gap_samples"])
        print(
            f"{group:5s} "
            f"{row['ft_carry_next_shot']:4.0f} "
            f"{row['ft_carry_next_carry']:4.0f} "
            f"{next_pass:4.0f} "
            f"{row['ft_carry_next_hold']:4.0f} "
            f"{row['ft_carry_decision_next_shoot']:4.0f} "
            f"{row['ft_carry_decision_next_carry']:4.0f} "
            f"{decision_next_pass:4.0f} "
            f"{row['ft_carry_decision_next_hold']:4.0f} "
            f"{row['ft_carry_actual_progress_sum']/carry_gap_samples:4.2f}/"
            f"{row['ft_carry_target_progress_sum']/carry_gap_samples:4.2f}/"
            f"{row['ft_carry_target_gap_sum']/carry_gap_samples:4.2f} "
            f"{row['ft_best_carry_future_shot_gain_sum']/denom:6.3f}/"
            f"{row['ft_best_carry_carry_to_shoot_window_sum']/denom:6.3f}/"
            f"{row['ft_best_carry_wide_second_line_carry_window_sum']/denom:6.3f}"
        )


def _real_case(
    db_path: str,
    home_profile: str,
    away_profile: str,
    home_formation: str,
    away_formation: str,
    home_star: int,
    away_star: int,
) -> dict:
    return {
        "db_path": db_path,
        "home_real_profile": home_profile,
        "away_real_profile": away_profile,
        "home_formation": home_formation,
        "away_formation": away_formation,
        "home_star": home_star,
        "away_star": away_star,
    }


def _npc_case(db_path: str, home_npc: str, away_npc: str, home_star: int, away_star: int) -> dict:
    return {
        "db_path": db_path,
        "home_npc": home_npc,
        "away_npc": away_npc,
        "home_star": home_star,
        "away_star": away_star,
    }


def matrix_cases(default_db_path: str = "psl.db", suite: str = "smoke"):
    cases = []

    def add(name: str, overrides: dict, *suites: str):
        payload = dict(overrides)
        payload["_suites"] = set(suites) | {"full"}
        cases.append((name, payload))

    add("db_10001_vs_10002", {"db_path": default_db_path, "home_qq": 10001, "away_qq": 10002}, "smoke", "db")
    add("db_10002_vs_10001", {"db_path": default_db_path, "home_qq": 10002, "away_qq": 10001}, "smoke", "db")

    for star in (1, 5, 10):
        add(f"random_{star}v{star}", {"home_star": star, "away_star": star}, "random")
    add("random_10v1", {"home_star": 10, "away_star": 1}, "random")

    for formation in ("433", "4141"):
        for star in (1, 5, 10):
            add(
                f"real_balanced{formation}_{star}v{star}",
                _real_case(default_db_path, "balanced", "balanced", formation, formation, star, star),
                "smoke" if formation == "433" and star in (5, 10) else "real",
                "real",
            )

    for star in (1, 5, 10):
        add(
            f"real_attack433_vs_defense532_{star}v{star}",
            _real_case(default_db_path, "attack", "defense", "433", "532", star, star),
            "smoke" if star == 5 else "real",
            "real",
        )
        add(
            f"real_defense532_vs_attack433_{star}v{star}",
            _real_case(default_db_path, "defense", "attack", "532", "433", star, star),
            "smoke" if star == 5 else "real",
            "real",
        )

    add(
        "real_balanced4231_vs_balanced451_5v5",
        _real_case(default_db_path, "balanced", "balanced", "4231", "451", 5, 5),
        "real",
    )
    add(
        "real_balanced343_vs_balanced532_5v5",
        _real_case(default_db_path, "balanced", "balanced", "343", "532", 5, 5),
        "real",
    )
    add(
        "real_attack433_10v1",
        _real_case(default_db_path, "attack", "balanced", "433", "451", 10, 1),
        "real",
    )
    add(
        "real_attack424_10v1",
        _real_case(default_db_path, "attack", "balanced", "424", "451", 10, 1),
        "smoke",
        "real",
    )
    add(
        "real_defense532_10v1",
        _real_case(default_db_path, "defense", "balanced", "532", "451", 10, 1),
        "real",
    )

    add(
        "club_barcelona_vs_juventus_5v5",
        _npc_case(default_db_path, "FC Barcelona", "Juventus F.C.", 5, 5),
        "smoke",
        "club",
        "real",
    )
    add(
        "club_mancity_vs_real_5v5",
        _npc_case(default_db_path, "Manchester City F.C.", "Real Madrid", 5, 5),
        "club",
        "real",
    )
    add(
        "club_psg_vs_bayern_10v10",
        _npc_case(default_db_path, "Paris Saint-Germain F.C.", "Bayern München", 10, 10),
        "club",
        "real",
    )
    add(
        "club_mancity_vs_juventus_10v1",
        _npc_case(default_db_path, "Manchester City F.C.", "Juventus F.C.", 10, 1),
        "club",
        "real",
    )

    add("template_attack433_vs_defense532", {
        "home_template": "attack",
        "away_template": "defense",
        "home_formation": "433",
        "away_formation": "532",
    }, "template")
    add("template_defense532_vs_attack433", {
        "home_template": "defense",
        "away_template": "attack",
        "home_formation": "532",
        "away_formation": "433",
    }, "template")
    add("template_attack4231_vs_defense451", {
        "home_template": "attack",
        "away_template": "defense",
        "home_formation": "4231",
        "away_formation": "451",
    }, "template")

    if suite == "full":
        selected = cases
    else:
        selected = [(name, overrides) for name, overrides in cases if suite in overrides.get("_suites", set())]
    return [(name, {key: value for key, value in overrides.items() if key != "_suites"}) for name, overrides in selected]


def print_report(totals: Counter, aggregate, players=None, include_players: bool = False, side_aggregate=None):
    matches = max(1, totals["matches"])
    simulated_minutes = max(1e-6, totals["simulated_ticks"] * totals["tick_duration"] / 60.0)
    scale_to_90 = 90.0 / simulated_minutes
    total_shots = max(1, sum(row["shots"] for row in aggregate.values()))
    ft_touches = max(1, sum(row["final_third_touch_frames"] for row in aggregate.values()))
    c3_total = sum(
        row["shot_after_carry_3p"]
        for row in aggregate.values()
    )
    c3_next_total = sum(
        row["chain3_next_carry"]
        + row["chain3_next_pass"]
        + row["chain3_next_pass_to_space"]
        + row["chain3_next_shot"]
        + row["chain3_next_hold"]
        + row["chain3_next_clear"]
        + row["chain3_next_unknown"]
        for row in aggregate.values()
    )
    nearest_def_samples = max(1, totals["ft_nearest_def_samples"])
    print("Engine V2 Structure Diagnostics")
    print(f"matches={matches} goals/match={totals['goals']/matches:.2f} shots/match={totals['shots']/matches:.2f} "
          f"sot%={(totals['sot']/max(1, totals['shots']))*100:.1f} pass%={(totals['completed_passes']/max(1, totals['passes']))*100:.1f}")
    print(
        f"home g/sh/sot/xg={totals['home_goals']/matches:.2f}/"
        f"{totals['home_shots']/matches:.2f}/"
        f"{totals['home_sot']/matches:.2f}/"
        f"{totals['home_xg']/matches:.2f} "
        f"away g/sh/sot/xg={totals['away_goals']/matches:.2f}/"
        f"{totals['away_shots']/matches:.2f}/"
        f"{totals['away_sot']/matches:.2f}/"
        f"{totals['away_xg']/matches:.2f}"
    )
    print(
        f"box_shots={totals['box_shots']} box_goal%={(totals['box_goals']/max(1, totals['box_shots']))*100:.1f} "
        f"box_sot%={(totals['box_sot']/max(1, totals['box_shots']))*100:.1f} "
        f"box_xg/shot={totals['box_xg']/max(1, totals['box_shots']):.3f}"
    )
    print(
        f"out_shots={totals['out_shots']} out_goal%={(totals['out_goals']/max(1, totals['out_shots']))*100:.1f} "
        f"out_sot%={(totals['out_sot']/max(1, totals['out_shots']))*100:.1f} "
        f"out_xg/shot={totals['out_xg']/max(1, totals['out_shots']):.3f}"
    )
    print()
    print("STRUCTURE SUMMARY")
    print(
        "shot_share "
        f"FW={aggregate.get('FW', Counter())['shots']/total_shots*100:.1f}% "
        f"W={aggregate.get('W', Counter())['shots']/total_shots*100:.1f}% "
        f"WM={aggregate.get('WM', Counter())['shots']/total_shots*100:.1f}% "
        f"CM={aggregate.get('CM', Counter())['shots']/total_shots*100:.1f}% "
        f"FB+CB={(aggregate.get('FB', Counter())['shots'] + aggregate.get('CB', Counter())['shots'])/total_shots*100:.1f}%"
    )
    print(
        "final_third_touch_share "
        f"FW={aggregate.get('FW', Counter())['final_third_touch_frames']/ft_touches*100:.1f}% "
        f"W={aggregate.get('W', Counter())['final_third_touch_frames']/ft_touches*100:.1f}% "
        f"WM={aggregate.get('WM', Counter())['final_third_touch_frames']/ft_touches*100:.1f}% "
        f"CM={aggregate.get('CM', Counter())['final_third_touch_frames']/ft_touches*100:.1f}%"
    )
    print(
        "carry_chain "
        f"c3p_shots={c3_total} "
        f"chain3_next_carry={sum(row['chain3_next_carry'] for row in aggregate.values())} "
        f"chain3_next_pass={sum(row['chain3_next_pass'] + row['chain3_next_pass_to_space'] for row in aggregate.values())} "
        f"chain3_next_shot={sum(row['chain3_next_shot'] for row in aggregate.values())} "
        f"chain3_events={c3_next_total}"
    )
    print(
        "final_third_def_pressure "
        f"nearest={totals['ft_nearest_def_dist_sum']/nearest_def_samples:.2f}m "
        f"close6={totals['ft_close6_def_sum']/nearest_def_samples:.2f} "
        f"close8={totals['ft_close8_def_sum']/nearest_def_samples:.2f}"
    )
    print()
    header = (
        "role players shots% shots/90 xg/90 box_pass/90 cross/90 "
        "carry_box/90 box_recv/90 sh_recv sh_space sh_carry c1 c2 c3p sh_other ch3_car ch3_pass ch3_shot ch3_other sup_d wide_d touch% ft_touch% touch_x ft_x touch_w press/90 tack/90 int/90 atk_x def_x atk3_x def3_x atk_w def_w"
        " ft_sh ft_ps ft_car"
    )
    print(header)
    total_touches = max(1, sum(row["touch_frames"] for row in aggregate.values()))
    total_final_third_touches = max(1, sum(row["final_third_touch_frames"] for row in aggregate.values()))
    for group in ("GK", "CB", "FB", "DM", "CM", "WM", "AM", "W", "FW", "OTHER"):
        row = aggregate.get(group)
        if not row:
            continue
        per90_scale = scale_to_90
        touch_samples = max(1, row["touch_frames"])
        final_touch_samples = max(1, row["final_third_touch_frames"])
        atk_samples = max(1, row["atk_samples"])
        def_samples = max(1, row["def_samples"])
        atk3_samples = max(1, row["atk3_samples"])
        def3_samples = max(1, row["def3_samples"])
        shot_support_samples = max(1, row["shot_support_samples"])
        shot_wide_support_samples = max(1, row["shot_wide_support_samples"])
        ft_pass_actions = (
            row["final_third_action_short_pass"]
            + row["final_third_action_long_pass"]
            + row["final_third_action_pass_to_space"]
        )
        print(
            f"{group:5s} "
            f"{int(row['players']):7d} "
            f"{row['shots']/total_shots*100:6.1f} "
            f"{row['shots']*per90_scale:8.2f} "
            f"{row['xg']*per90_scale:6.2f} "
            f"{row['passes_into_box']*per90_scale:11.2f} "
            f"{row['crosses']*per90_scale:8.2f} "
            f"{row['carries_into_box']*per90_scale:12.2f} "
            f"{row['box_receives']*per90_scale:11.2f} "
            f"{row['shot_after_receive']:7.0f} "
            f"{row['shot_after_receive_space_pass']:8.0f} "
            f"{row['shot_after_carry']:8.0f} "
            f"{row['shot_after_carry_1']:2.0f} "
            f"{row['shot_after_carry_2']:2.0f} "
            f"{row['shot_after_carry_3p']:3.0f} "
            f"{row['shot_after_other']:8.0f} "
            f"{row['chain3_next_carry']:7.0f} "
            f"{row['chain3_next_pass'] + row['chain3_next_pass_to_space']:8.0f} "
            f"{row['chain3_next_shot']:8.0f} "
            f"{row['chain3_next_hold'] + row['chain3_next_clear'] + row['chain3_next_unknown']:9.0f} "
            f"{row['shot_support_dist_sum']/shot_support_samples:5.1f} "
            f"{row['shot_wide_support_dist_sum']/shot_wide_support_samples:6.1f} "
            f"{row['touch_frames']/total_touches*100:6.1f} "
            f"{row['final_third_touch_frames']/total_final_third_touches*100:9.1f} "
            f"{row['touch_progress_sum']/touch_samples:7.2f} "
            f"{row['final_third_touch_progress_sum']/final_touch_samples:4.2f} "
            f"{row['touch_width_sum']/touch_samples:7.2f} "
            f"{row['pressures']*per90_scale:8.2f} "
            f"{row['tackles_attempted']*per90_scale:7.2f} "
            f"{row['interceptions']*per90_scale:6.2f} "
            f"{row['atk_progress_sum']/atk_samples:5.2f} "
            f"{row['def_progress_sum']/def_samples:5.2f} "
            f"{row['atk3_progress_sum']/atk3_samples:6.2f} "
            f"{row['def3_progress_sum']/def3_samples:6.2f} "
            f"{row['atk_width_sum']/atk_samples:5.2f} "
            f"{row['def_width_sum']/def_samples:5.2f} "
            f"{row['final_third_action_shot']:5.0f} "
            f"{ft_pass_actions:5.0f} "
            f"{row['final_third_action_carry']:6.0f}"
        )

    if side_aggregate:
        print()
        print("side role shots xg pass_box cross carry_box box_recv sh_recv sh_space sh_carry c1 c2 c3p sh_other ch3_car ch3_pass ch3_shot ch3_other sup_d wide_d press tack int")
        for side in ("home", "away"):
            for group in ("GK", "CB", "FB", "DM", "CM", "WM", "AM", "W", "FW", "OTHER"):
                row = side_aggregate.get(f"{side}:{group}")
                if not row:
                    continue
                shot_support_samples = max(1, row["shot_support_samples"])
                shot_wide_support_samples = max(1, row["shot_wide_support_samples"])
                print(
                    f"{side:4s} {group:5s} "
                    f"{row['shots']:5.0f} "
                    f"{row['xg']:4.2f} "
                    f"{row['passes_into_box']:8.0f} "
                    f"{row['crosses']:5.0f} "
                    f"{row['carries_into_box']:9.0f} "
                    f"{row['box_receives']:8.0f} "
                    f"{row['shot_after_receive']:7.0f} "
                    f"{row['shot_after_receive_space_pass']:8.0f} "
                    f"{row['shot_after_carry']:8.0f} "
                    f"{row['shot_after_carry_1']:2.0f} "
                    f"{row['shot_after_carry_2']:2.0f} "
                    f"{row['shot_after_carry_3p']:3.0f} "
                    f"{row['shot_after_other']:8.0f} "
                    f"{row['chain3_next_carry']:7.0f} "
                    f"{row['chain3_next_pass'] + row['chain3_next_pass_to_space']:8.0f} "
                    f"{row['chain3_next_shot']:8.0f} "
                    f"{row['chain3_next_hold'] + row['chain3_next_clear'] + row['chain3_next_unknown']:9.0f} "
                    f"{row['shot_support_dist_sum']/shot_support_samples:5.1f} "
                    f"{row['shot_wide_support_dist_sum']/shot_wide_support_samples:6.1f} "
                    f"{row['pressures']:5.0f} "
                    f"{row['tackles_attempted']:4.0f} "
                    f"{row['interceptions']:3.0f}"
                )

    if include_players and players:
        print()
        print("players pos apps shots xg box_pass cross carry_box box_recv sh_recv sh_space sh_carry c1 c2 c3p sh_other ch3_car ch3_pass ch3_shot ch3_other sup_d wide_d touch% ft_touch% touch_x ft_x touch_w press tack int")
        total_touches_all = max(1, sum(row["touch_frames"] for row in players.values()))
        total_final_touches_all = max(1, sum(row["final_third_touch_frames"] for row in players.values()))
        for key, row in sorted(
            players.items(),
            key=lambda item: (
                -item[1]["shots"],
                -item[1]["final_third_touch_frames"],
                item[0],
            ),
        ):
            pos, name = key.split(":", 1)
            touch_samples = max(1, row["touch_frames"])
            final_touch_samples = max(1, row["final_third_touch_frames"])
            shot_support_samples = max(1, row["shot_support_samples"])
            shot_wide_support_samples = max(1, row["shot_wide_support_samples"])
            print(
                f"{name[:18]:18s} {pos:4s} "
                f"{int(row['appearances']):4d} "
                f"{row['shots']:5.0f} "
                f"{row['xg']:4.2f} "
                f"{row['passes_into_box']:8.0f} "
                f"{row['crosses']:5.0f} "
                f"{row['carries_into_box']:9.0f} "
                f"{row['box_receives']:8.0f} "
                f"{row['shot_after_receive']:7.0f} "
                f"{row['shot_after_receive_space_pass']:8.0f} "
                f"{row['shot_after_carry']:8.0f} "
                f"{row['shot_after_carry_1']:2.0f} "
                f"{row['shot_after_carry_2']:2.0f} "
                f"{row['shot_after_carry_3p']:3.0f} "
                f"{row['shot_after_other']:8.0f} "
                f"{row['chain3_next_carry']:7.0f} "
                f"{row['chain3_next_pass'] + row['chain3_next_pass_to_space']:8.0f} "
                f"{row['chain3_next_shot']:8.0f} "
                f"{row['chain3_next_hold'] + row['chain3_next_clear'] + row['chain3_next_unknown']:9.0f} "
                f"{row['shot_support_dist_sum']/shot_support_samples:5.1f} "
                f"{row['shot_wide_support_dist_sum']/shot_wide_support_samples:6.1f} "
                f"{row['touch_frames']/total_touches_all*100:6.1f} "
                f"{row['final_third_touch_frames']/total_final_touches_all*100:9.1f} "
                f"{row['touch_progress_sum']/touch_samples:7.2f} "
                f"{row['final_third_touch_progress_sum']/final_touch_samples:4.2f} "
                f"{row['touch_width_sum']/touch_samples:7.2f} "
                f"{row['pressures']:5.0f} "
                f"{row['tackles_attempted']:4.0f} "
                f"{row['interceptions']:3.0f}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=3)
    parser.add_argument("--home-star", type=int, default=3)
    parser.add_argument("--away-star", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--ticks", type=int, default=360, help="Use 0 for full match length")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--home-qq", type=int, default=0)
    parser.add_argument("--away-qq", type=int, default=0)
    parser.add_argument("--home-real-profile", choices=["attack", "defense", "balanced"], default="")
    parser.add_argument("--away-real-profile", choices=["attack", "defense", "balanced"], default="")
    parser.add_argument("--home-formation", default="")
    parser.add_argument("--away-formation", default="")
    parser.add_argument("--players", action="store_true", help="Print per-player micro diagnostics")
    parser.add_argument("--matrix", action="store_true", help="Run a fixed diagnostic matrix")
    parser.add_argument(
        "--suite",
        choices=["smoke", "db", "random", "real", "club", "template", "full"],
        default="smoke",
        help="Diagnostic matrix suite to run",
    )
    parser.add_argument("--case", default="", help="When using --matrix, run only cases containing this text")
    parser.add_argument("--scorecard", action="store_true", help="Print compact structure scorecard only")
    parser.add_argument("--health", action="store_true", help="Print compact structural health scorecard")
    parser.add_argument("--seed-count", type=int, default=1, help="Seeds per case for --scorecard")
    parser.add_argument("--trace-detail", choices=["", "chosen", "top_candidates", "full"], default="")
    parser.add_argument("--trace-top-k", type=int, default=5)
    parser.add_argument("--trace-sample-rate", type=int, default=1)
    parser.add_argument("--trace-include-defense", action="store_true", help="Include off-ball defense decisions in trace output")
    parser.add_argument("--no-goal-continuity", action="store_true", help="Disable Goal continuity layer for A/B baselines")
    args = parser.parse_args()

    if args.matrix:
        cases = matrix_cases(args.db_path or "psl.db", suite=args.suite)
        if args.case:
            exact_cases = [(name, overrides) for name, overrides in cases if args.case == name]
            cases = exact_cases or [(name, overrides) for name, overrides in cases if args.case in name]
            if not cases:
                raise SystemExit(f"No matrix cases match: {args.case}")
        for idx, (name, overrides) in enumerate(cases):
            if args.scorecard or args.health:
                cards = []
                for seed_idx in range(max(1, args.seed_count)):
                    totals, aggregate, _, _ = run(
                        args.matches,
                        overrides.get("home_star", args.home_star),
                        overrides.get("away_star", args.away_star),
                        args.seed + idx * 1000 + seed_idx * 100000,
                        args.ticks,
                        db_path=overrides.get("db_path", ""),
                        home_qq=overrides.get("home_qq", 0),
                        away_qq=overrides.get("away_qq", 0),
                        home_template=overrides.get("home_template", ""),
                        away_template=overrides.get("away_template", ""),
                        home_formation=overrides.get("home_formation", ""),
                        away_formation=overrides.get("away_formation", ""),
                        home_real_profile=overrides.get("home_real_profile", ""),
                        away_real_profile=overrides.get("away_real_profile", ""),
                        home_npc=overrides.get("home_npc", ""),
                        away_npc=overrides.get("away_npc", ""),
                        trace_detail=args.trace_detail,
                        trace_top_k=args.trace_top_k,
                        trace_sample_rate=args.trace_sample_rate,
                        trace_include_defense=args.trace_include_defense,
                        goal_continuity=not args.no_goal_continuity,
                    )
                    cards.append(structure_scorecard(totals, aggregate))
                card = average_scorecards(cards)
                if args.health:
                    print_health_line(name, card)
                else:
                    print_scorecard_line(name, card)
                continue
            print()
            print("=" * 80)
            print(f"CASE {name}")
            print("=" * 80)
            totals, aggregate, players, side_aggregate = run(
                args.matches,
                overrides.get("home_star", args.home_star),
                overrides.get("away_star", args.away_star),
                args.seed + idx * 1000,
                args.ticks,
                db_path=overrides.get("db_path", ""),
                home_qq=overrides.get("home_qq", 0),
                away_qq=overrides.get("away_qq", 0),
                home_template=overrides.get("home_template", ""),
                away_template=overrides.get("away_template", ""),
                home_formation=overrides.get("home_formation", ""),
                away_formation=overrides.get("away_formation", ""),
                home_real_profile=overrides.get("home_real_profile", ""),
                away_real_profile=overrides.get("away_real_profile", ""),
                home_npc=overrides.get("home_npc", ""),
                away_npc=overrides.get("away_npc", ""),
                trace_detail=args.trace_detail,
                trace_top_k=args.trace_top_k,
                trace_sample_rate=args.trace_sample_rate,
                trace_include_defense=args.trace_include_defense,
                goal_continuity=not args.no_goal_continuity,
            )
            print_report(totals, aggregate, players, include_players=args.players, side_aggregate=side_aggregate)
            if args.trace_detail:
                print_decision_report(aggregate)
        return 0

    totals, aggregate, players, side_aggregate = run(
        args.matches,
        args.home_star,
        args.away_star,
        args.seed,
        args.ticks,
        db_path=args.db_path,
        home_qq=args.home_qq,
        away_qq=args.away_qq,
        home_formation=args.home_formation,
        away_formation=args.away_formation,
        home_real_profile=args.home_real_profile,
        away_real_profile=args.away_real_profile,
        trace_detail=args.trace_detail,
        trace_top_k=args.trace_top_k,
        trace_sample_rate=args.trace_sample_rate,
        trace_include_defense=args.trace_include_defense,
        goal_continuity=not args.no_goal_continuity,
    )
    if args.health:
        print_health_line("single", structure_scorecard(totals, aggregate))
    else:
        print_report(totals, aggregate, players, include_players=args.players, side_aggregate=side_aggregate)
    if args.trace_detail:
        print_decision_report(aggregate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
