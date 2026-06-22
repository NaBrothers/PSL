#!/usr/bin/env python3
import argparse
import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
  if str(path) not in sys.path:
    sys.path.insert(0, str(path))


class DummyMatcher:
  async def send(self, *args, **kwargs):
    return None


def initialize_temp_db(path):
  from database.init_db import initialize_database

  conn = sqlite3.connect(path)
  initialize_database(conn)
  conn.close()


async def add_user_with_squad(user_cls, player_cls, card_cls, bag_cls, formation_kernel, qq, name, star):
  user = user_cls.addUser(qq, name)
  player_ids = [200389, 212622, 203376, 155862, 216267, 189596, 192985, 215914, 200104, 158023, 188545]
  for player_id in player_ids:
    player = player_cls.getPlayerByID(player_id)
    bag_cls.addToBag(user, card_cls.new(player, user, star=star))

  async def finish_noop(*args, **kwargs):
    return None

  old_finish = formation_kernel.get_team.finish
  formation_kernel.get_team.finish = finish_noop
  try:
    await formation_kernel.auto_update(user)
  finally:
    formation_kernel.get_team.finish = old_finish
  return user_cls.getUserByQQ(qq)


async def run_matches(count, seed, home_star, away_star):
  from engine.const import Const
  from engine.game import Game
  from model.bag import Bag
  from model.card import Card
  from model.player import Player
  from model.user import User
  from kernel import formation as formation_kernel

  qq_base = 90000 + seed * 10 + home_star * 1000 + away_star * 100
  home = await add_user_with_squad(User, Player, Card, Bag, formation_kernel, qq_base + 1, "home", home_star)
  away = await add_user_with_squad(User, Player, Card, Bag, formation_kernel, qq_base + 2, "away", away_star)

  result = {
    "matches": count,
    "home_wins": 0,
    "draws": 0,
    "away_wins": 0,
    "home_goals": 0,
    "away_goals": 0,
    "home_shots": 0,
    "away_shots": 0,
    "home_passes": 0,
    "away_passes": 0,
  }
  for index in range(count):
    game = Game(DummyMatcher(), home, away, seed=seed + index)
    await game.start(Const.MODE_SILENCE)
    game.home.getStats()
    game.away.getStats()
    result["home_goals"] += game.home.point
    result["away_goals"] += game.away.point
    result["home_shots"] += game.home.shoots
    result["away_shots"] += game.away.shoots
    result["home_passes"] += game.home.passes
    result["away_passes"] += game.away.passes
    if game.home.point > game.away.point:
      result["home_wins"] += 1
    elif game.home.point == game.away.point:
      result["draws"] += 1
    else:
      result["away_wins"] += 1
  return result


def print_report(result):
  matches = result["matches"]
  print("matches:", matches)
  print("home_wins:", result["home_wins"], "draws:", result["draws"], "away_wins:", result["away_wins"])
  print("avg_score:", round(result["home_goals"] / matches, 2), "-", round(result["away_goals"] / matches, 2))
  print("avg_shots:", round(result["home_shots"] / matches, 2), "-", round(result["away_shots"] / matches, 2))
  print("avg_passes:", round(result["home_passes"] / matches, 2), "-", round(result["away_passes"] / matches, 2))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--matches", type=int, default=100)
  parser.add_argument("--seed", type=int, default=1)
  parser.add_argument("--home-star", type=int, default=3)
  parser.add_argument("--away-star", type=int, default=3)
  args = parser.parse_args()

  with tempfile.TemporaryDirectory() as tmp:
    db_path = os.path.join(tmp, "psl-sim.db")
    os.environ["PSL_DB_PATH"] = db_path
    initialize_temp_db(db_path)
    result = asyncio.run(run_matches(args.matches, args.seed, args.home_star, args.away_star))
    print_report(result)


if __name__ == "__main__":
  main()
