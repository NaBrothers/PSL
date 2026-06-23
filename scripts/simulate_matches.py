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
    "home_shots_on_target": 0,
    "away_shots_on_target": 0,
    "home_passes": 0,
    "away_passes": 0,
    "home_successful_passes": 0,
    "away_successful_passes": 0,
    "home_dribbles": 0,
    "away_dribbles": 0,
    "home_carries": 0,
    "away_carries": 0,
    "home_tackles": 0,
    "away_tackles": 0,
    "home_tackle_attempts": 0,
    "away_tackle_attempts": 0,
    "home_interceptions": 0,
    "away_interceptions": 0,
    "home_blocks": 0,
    "away_blocks": 0,
    "home_saves": 0,
    "away_saves": 0,
    "home_control": 0,
    "away_control": 0,
    "home_xg": 0,
    "away_xg": 0,
    "home_adjusted_xg": 0,
    "away_adjusted_xg": 0,
    "home_xt": 0,
    "away_xt": 0,
    "home_key_passes": 0,
    "away_key_passes": 0,
    "home_box_touches": 0,
    "away_box_touches": 0,
    "home_big_chances": 0,
    "away_big_chances": 0,
    "home_possessions": 0,
    "away_possessions": 0,
    "home_offsides": 0,
    "away_offsides": 0,
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
    result["home_shots_on_target"] += game.home.shoots_in_target
    result["away_shots_on_target"] += game.away.shoots_in_target
    result["home_passes"] += game.home.passes
    result["away_passes"] += game.away.passes
    result["home_successful_passes"] += game.home.successful_passes
    result["away_successful_passes"] += game.away.successful_passes
    result["home_dribbles"] += game.home.dribbles
    result["away_dribbles"] += game.away.dribbles
    result["home_carries"] += game.home.carries
    result["away_carries"] += game.away.carries
    result["home_tackles"] += game.home.tackles
    result["away_tackles"] += game.away.tackles
    result["home_tackle_attempts"] += game.home.tackle_attempts
    result["away_tackle_attempts"] += game.away.tackle_attempts
    result["home_interceptions"] += game.home.interceptions
    result["away_interceptions"] += game.away.interceptions
    result["home_blocks"] += game.home.blocks
    result["away_blocks"] += game.away.blocks
    result["home_saves"] += game.home.saves
    result["away_saves"] += game.away.saves
    result["home_control"] += game.home.control
    result["away_control"] += game.away.control
    result["home_xg"] += game.home.xg
    result["away_xg"] += game.away.xg
    result["home_adjusted_xg"] += game.home.adjusted_xg
    result["away_adjusted_xg"] += game.away.adjusted_xg
    result["home_xt"] += game.home.xt
    result["away_xt"] += game.away.xt
    result["home_key_passes"] += game.home.key_passes
    result["away_key_passes"] += game.away.key_passes
    result["home_box_touches"] += game.home.box_touches
    result["away_box_touches"] += game.away.box_touches
    result["home_big_chances"] += game.home.big_chances
    result["away_big_chances"] += game.away.big_chances
    result["home_possessions"] += game.home.possessions
    result["away_possessions"] += game.away.possessions
    for event in game.match_events:
      if event.event_type == "turnover" and "越位" in event.text:
        if event.team == game.home:
          result["home_offsides"] += 1
        elif event.team == game.away:
          result["away_offsides"] += 1
    if game.home.point > game.away.point:
      result["home_wins"] += 1
    elif game.home.point == game.away.point:
      result["draws"] += 1
    else:
      result["away_wins"] += 1
  return result


def print_report(result):
  matches = result["matches"]
  home_pass_rate = 0 if result["home_passes"] == 0 else result["home_successful_passes"] * 100 / result["home_passes"]
  away_pass_rate = 0 if result["away_passes"] == 0 else result["away_successful_passes"] * 100 / result["away_passes"]
  total_control = result["home_control"] + result["away_control"]
  home_control = 0 if total_control == 0 else result["home_control"] * 100 / total_control
  away_control = 0 if total_control == 0 else result["away_control"] * 100 / total_control
  print("matches:", matches)
  print("home_wins:", result["home_wins"], "draws:", result["draws"], "away_wins:", result["away_wins"])
  print("avg_score:", round(result["home_goals"] / matches, 2), "-", round(result["away_goals"] / matches, 2))
  print("avg_shots:", round(result["home_shots"] / matches, 2), "-", round(result["away_shots"] / matches, 2))
  print("avg_shots_on_target:", round(result["home_shots_on_target"] / matches, 2), "-", round(result["away_shots_on_target"] / matches, 2))
  home_sot_rate = 0 if result["home_shots"] == 0 else result["home_shots_on_target"] * 100 / result["home_shots"]
  away_sot_rate = 0 if result["away_shots"] == 0 else result["away_shots_on_target"] * 100 / result["away_shots"]
  print("shot_on_target_pct:", round(home_sot_rate, 1), "-", round(away_sot_rate, 1))
  print("avg_passes:", round(result["home_passes"] / matches, 2), "-", round(result["away_passes"] / matches, 2))
  print("pass_success_pct:", round(home_pass_rate, 1), "-", round(away_pass_rate, 1))
  print("avg_dribbles:", round(result["home_dribbles"] / matches, 2), "-", round(result["away_dribbles"] / matches, 2))
  print("avg_carries:", round(result["home_carries"] / matches, 2), "-", round(result["away_carries"] / matches, 2))
  print("avg_tackles:", round(result["home_tackles"] / matches, 2), "-", round(result["away_tackles"] / matches, 2))
  print("avg_tackle_attempts:", round(result["home_tackle_attempts"] / matches, 2), "-", round(result["away_tackle_attempts"] / matches, 2))
  print("avg_interceptions:", round(result["home_interceptions"] / matches, 2), "-", round(result["away_interceptions"] / matches, 2))
  print("avg_blocks:", round(result["home_blocks"] / matches, 2), "-", round(result["away_blocks"] / matches, 2))
  print("avg_saves:", round(result["home_saves"] / matches, 2), "-", round(result["away_saves"] / matches, 2))
  print("control_pct:", round(home_control, 1), "-", round(away_control, 1))
  print("avg_xg:", round(result["home_xg"] / matches, 2), "-", round(result["away_xg"] / matches, 2))
  print("avg_adjusted_xg:", round(result["home_adjusted_xg"] / matches, 2), "-", round(result["away_adjusted_xg"] / matches, 2))
  print("avg_xt:", round(result["home_xt"] / matches, 2), "-", round(result["away_xt"] / matches, 2))
  print("avg_key_passes:", round(result["home_key_passes"] / matches, 2), "-", round(result["away_key_passes"] / matches, 2))
  print("avg_box_touches:", round(result["home_box_touches"] / matches, 2), "-", round(result["away_box_touches"] / matches, 2))
  print("avg_big_chances:", round(result["home_big_chances"] / matches, 2), "-", round(result["away_big_chances"] / matches, 2))
  print("avg_possessions:", round(result["home_possessions"] / matches, 2), "-", round(result["away_possessions"] / matches, 2))
  print("avg_offsides:", round(result["home_offsides"] / matches, 2), "-", round(result["away_offsides"] / matches, 2))


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
