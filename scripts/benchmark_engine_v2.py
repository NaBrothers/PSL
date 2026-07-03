#!/usr/bin/env python3
"""Benchmark script for PSL engine_v2.

Runs N matches with random teams at configurable star levels and outputs
macro statistics with assertion checks against expected ranges.

Usage:
    python3 scripts/benchmark_engine_v2.py --matches 100
    python3 scripts/benchmark_engine_v2.py --matches 50 --home-star 5 --away-star 3
"""

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psl_core.engine_v2.match import MatchV2


# 13 ability keys used by engine_v2
ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]

# Realistic ability ranges per star level (base ability center)
STAR_ABILITY_RANGES = {
    1: (35, 55),
    2: (42, 62),
    3: (50, 70),
    4: (58, 78),
    5: (65, 85),
    6: (72, 90),
    7: (78, 94),
    8: (82, 96),
    9: (85, 98),
    10: (88, 99),
}

FORMATIONS = ["442", "433", "352", "4231", "343", "532", "451"]

POSITIONS_BY_FORMATION = {
    "442": ["GK", "RB", "CB", "CB", "LB", "RM", "CM", "CM", "LM", "ST", "ST"],
    "433": ["GK", "RB", "CB", "CB", "LB", "CM", "CM", "CM", "RW", "ST", "LW"],
    "352": ["GK", "CB", "CB", "CB", "RM", "CM", "CM", "LM", "CAM", "ST", "ST"],
    "4231": ["GK", "RB", "CB", "CB", "LB", "CDM", "CDM", "CAM", "RW", "LW", "ST"],
    "343": ["GK", "CB", "CB", "CB", "RM", "CM", "CM", "LM", "RW", "ST", "LW"],
    "532": ["GK", "RWB", "CB", "CB", "CB", "LWB", "CM", "CM", "CM", "ST", "ST"],
    "451": ["GK", "RB", "CB", "CB", "LB", "RM", "CM", "CM", "CM", "LM", "ST"],
}

PLAYER_NAMES = [
    "Player A", "Player B", "Player C", "Player D", "Player E",
    "Player F", "Player G", "Player H", "Player I", "Player J", "Player K",
]


def generate_random_team(star: int, rng: random.Random) -> tuple:
    """Generate a random team of 11 cards at the given star level.

    Returns (cards_list, formation_key).
    """
    formation = rng.choice(FORMATIONS)
    positions = POSITIONS_BY_FORMATION[formation]
    lo, hi = STAR_ABILITY_RANGES.get(star, (50, 70))

    cards = []
    for i in range(11):
        abilities = {}
        pos = positions[i]
        for key in ABILITY_KEYS:
            # GK gets boosted GK stats, reduced outfield stats
            if pos == "GK":
                if key.startswith("GK_"):
                    abilities[key] = rng.randint(max(lo + 10, 50), min(hi + 10, 99))
                else:
                    abilities[key] = rng.randint(max(lo - 15, 20), max(hi - 20, 40))
            else:
                if key.startswith("GK_"):
                    abilities[key] = rng.randint(10, 30)
                else:
                    abilities[key] = rng.randint(lo, hi)
        cards.append({
            "name": PLAYER_NAMES[i],
            "player_id": 1000 + i,
            "position": pos,
            "color": "gold" if star >= 7 else "silver" if star >= 4 else "bronze",
            "overall": int((lo + hi) / 2),
            "abilities": abilities,
        })
    return cards, formation


def run_benchmark(matches: int, home_star: int, away_star: int, seed: int):
    """Run benchmark and return statistics."""
    rng = random.Random(seed)

    # Accumulators
    total_home_goals = 0
    total_away_goals = 0
    total_home_shots = 0
    total_away_shots = 0
    total_home_sot = 0
    total_away_sot = 0
    total_home_passes = 0
    total_away_passes = 0
    total_home_passes_completed = 0
    total_away_passes_completed = 0
    total_home_possession = 0.0
    total_away_possession = 0.0
    home_wins = 0
    draws = 0
    away_wins = 0

    start_time = time.time()

    for i in range(matches):
        home_cards, home_formation = generate_random_team(home_star, rng)
        away_cards, away_formation = generate_random_team(away_star, rng)

        match = MatchV2(home_cards, away_cards, home_formation, away_formation)
        result = match.run()

        total_home_goals += result.home_score
        total_away_goals += result.away_score

        hs = result.home_stats
        as_ = result.away_stats
        total_home_shots += hs.get("shots", 0)
        total_away_shots += as_.get("shots", 0)
        total_home_sot += hs.get("shots_on_target", 0)
        total_away_sot += as_.get("shots_on_target", 0)
        total_home_passes += hs.get("passes", 0)
        total_away_passes += as_.get("passes", 0)
        total_home_passes_completed += hs.get("passes_completed", 0)
        total_away_passes_completed += as_.get("passes_completed", 0)
        total_home_possession += hs.get("possession", 50.0)
        total_away_possession += as_.get("possession", 50.0)

        if result.home_score > result.away_score:
            home_wins += 1
        elif result.home_score == result.away_score:
            draws += 1
        else:
            away_wins += 1

    elapsed = time.time() - start_time

    # Compute averages
    avg_home_goals = total_home_goals / matches
    avg_away_goals = total_away_goals / matches
    avg_goals = (total_home_goals + total_away_goals) / matches
    avg_home_shots = total_home_shots / matches
    avg_away_shots = total_away_shots / matches
    avg_shots = (total_home_shots + total_away_shots) / matches

    total_shots = total_home_shots + total_away_shots
    total_sot = total_home_sot + total_away_sot
    shot_accuracy = (total_sot / max(total_shots, 1)) * 100

    total_passes = total_home_passes + total_away_passes
    total_passes_completed = total_home_passes_completed + total_away_passes_completed
    pass_success_rate = (total_passes_completed / max(total_passes, 1)) * 100

    avg_home_possession = total_home_possession / matches
    avg_away_possession = total_away_possession / matches

    # Upset rate: if stars are unequal, the weaker team winning is an upset
    upset_rate = 0.0
    if home_star > away_star:
        upset_rate = away_wins / matches * 100
    elif away_star > home_star:
        upset_rate = home_wins / matches * 100

    stats = {
        "matches": matches,
        "home_star": home_star,
        "away_star": away_star,
        "elapsed_sec": round(elapsed, 2),
        "avg_goals_per_match": round(avg_goals, 2),
        "avg_home_goals": round(avg_home_goals, 2),
        "avg_away_goals": round(avg_away_goals, 2),
        "avg_shots_per_match": round(avg_shots, 2),
        "avg_home_shots": round(avg_home_shots, 2),
        "avg_away_shots": round(avg_away_shots, 2),
        "shot_accuracy_pct": round(shot_accuracy, 1),
        "pass_success_rate_pct": round(pass_success_rate, 1),
        "avg_home_possession": round(avg_home_possession, 1),
        "avg_away_possession": round(avg_away_possession, 1),
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "home_win_pct": round(home_wins / matches * 100, 1),
        "draw_pct": round(draws / matches * 100, 1),
        "away_win_pct": round(away_wins / matches * 100, 1),
        "upset_rate_pct": round(upset_rate, 1),
    }
    return stats


def print_report(stats: dict):
    """Print formatted report."""
    print("=" * 60)
    print(f"  PSL Engine V2 Benchmark Results")
    print(f"  Matches: {stats['matches']}  |  "
          f"Home {stats['home_star']}★ vs Away {stats['away_star']}★  |  "
          f"Time: {stats['elapsed_sec']}s")
    print("=" * 60)
    print()
    print(f"  Goals per match:      {stats['avg_goals_per_match']:.2f}  "
          f"(home {stats['avg_home_goals']:.2f} - away {stats['avg_away_goals']:.2f})")
    print(f"  Shots per match:      {stats['avg_shots_per_match']:.2f}  "
          f"(home {stats['avg_home_shots']:.2f} - away {stats['avg_away_shots']:.2f})")
    print(f"  Shot accuracy:        {stats['shot_accuracy_pct']:.1f}%")
    print(f"  Pass success rate:    {stats['pass_success_rate_pct']:.1f}%")
    print(f"  Possession:           home {stats['avg_home_possession']:.1f}% - "
          f"away {stats['avg_away_possession']:.1f}%")
    print()
    print(f"  Results:  W {stats['home_wins']} / D {stats['draws']} / L {stats['away_wins']}  "
          f"({stats['home_win_pct']:.1f}% / {stats['draw_pct']:.1f}% / {stats['away_win_pct']:.1f}%)")
    if stats['home_star'] != stats['away_star']:
        print(f"  Upset rate:           {stats['upset_rate_pct']:.1f}%")
    print()
    print("=" * 60)


def run_assertions(stats: dict):
    """Run sanity-check assertions against expected ranges."""
    errors = []

    # Goals per match: expect 1.5 - 5.0 (realistic football range)
    if not (1.0 <= stats["avg_goals_per_match"] <= 6.0):
        errors.append(f"avg_goals_per_match={stats['avg_goals_per_match']:.2f} outside [1.0, 6.0]")

    # Shots per match: expect 15 - 40 total
    if not (8.0 <= stats["avg_shots_per_match"] <= 50.0):
        errors.append(f"avg_shots_per_match={stats['avg_shots_per_match']:.2f} outside [8.0, 50.0]")

    # Shot accuracy: expect 25% - 65%
    if not (20.0 <= stats["shot_accuracy_pct"] <= 70.0):
        errors.append(f"shot_accuracy_pct={stats['shot_accuracy_pct']:.1f}% outside [20%, 70%]")

    # Pass success: expect 50% - 95%
    if not (40.0 <= stats["pass_success_rate_pct"] <= 98.0):
        errors.append(f"pass_success_rate_pct={stats['pass_success_rate_pct']:.1f}% outside [40%, 98%]")

    # Possession split: should add to ~100%
    total_poss = stats["avg_home_possession"] + stats["avg_away_possession"]
    if not (95.0 <= total_poss <= 105.0):
        errors.append(f"possession sum={total_poss:.1f}% not close to 100%")

    # If stars equal, home wins should not dominate too heavily (< 70%)
    if stats["home_star"] == stats["away_star"]:
        if stats["home_win_pct"] > 75.0:
            errors.append(f"home_win_pct={stats['home_win_pct']:.1f}% too high for equal stars")
        if stats["away_win_pct"] > 75.0:
            errors.append(f"away_win_pct={stats['away_win_pct']:.1f}% too high for equal stars")

    # If stars unequal, stronger team should generally win more
    if stats["home_star"] > stats["away_star"] + 2:
        if stats["home_win_pct"] < stats["away_win_pct"]:
            errors.append(f"stronger home team ({stats['home_star']}★) loses more than "
                          f"weaker away ({stats['away_star']}★)")

    if errors:
        print("\n  ASSERTION FAILURES:")
        for e in errors:
            print(f"    - {e}")
        print()
        return False
    else:
        print("  All assertions passed.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Benchmark PSL engine_v2")
    parser.add_argument("--matches", type=int, default=100, help="Number of matches to simulate")
    parser.add_argument("--home-star", type=int, default=5, help="Home team star level (1-10)")
    parser.add_argument("--away-star", type=int, default=5, help="Away team star level (1-10)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    stats = run_benchmark(args.matches, args.home_star, args.away_star, args.seed)
    print_report(stats)
    success = run_assertions(stats)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
