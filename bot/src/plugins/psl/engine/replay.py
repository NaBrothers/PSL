"""Replay recorder - captures frame data during match simulation.

Writes JSONL files with:
- Line 1: header (roster, formations)
- Subsequent lines: frames (positions) and events (actions)
"""

import json
import os
import time as time_module
from typing import List

from engine.const import Const


class ReplayRecorder:
    def __init__(self):
        self.frames = []

    def record_header(self, home_team, away_team, home_formation, away_formation):
        home_players = []
        for p in home_team.players:
            home_players.append({
                "name": p.card.player.Name,
                "pos": p.position,
            })
        away_players = []
        for p in away_team.players:
            away_players.append({
                "name": p.card.player.Name,
                "pos": p.position,
            })
        self.frames.append({
            "type": "header",
            "home": {"name": home_team.coach.name, "players": home_players},
            "away": {"name": away_team.coach.name, "players": away_players},
            "formation_home": home_formation,
            "formation_away": away_formation,
            "field": {"width": Const.WIDTH, "length": Const.LENGTH},
        })

    def record_frame(self, game):
        """Record a position frame. Converts to absolute coords (home attacks left→right, toward y=LENGTH)."""
        home_coords = []
        away_coords = []

        is_home_offence = (game.offence is game.home)

        for p in game.home.players:
            if is_home_offence:
                # Home is offence: attacks toward y=0 in engine coords
                # Absolute: flip so home attacks toward y=LENGTH (right side)
                ax = Const.WIDTH - p.x
                ay = Const.LENGTH - p.y
            else:
                # Home is defence: already mirrored in engine
                # Defence coords are mirrored, so actual position is already flipped
                # In engine: defence.x = WIDTH - real.x, defence.y = LENGTH - real.y
                # So real = WIDTH - engine.x, LENGTH - engine.y
                # But we want home attacking right (y=LENGTH), so:
                ax = p.x
                ay = p.y
            home_coords.append([round(ax, 1), round(ay, 1)])

        for p in game.away.players:
            if is_home_offence:
                # Away is defence: coords are mirrored in engine
                ax = p.x
                ay = p.y
            else:
                # Away is offence: attacks toward y=0 in engine
                ax = Const.WIDTH - p.x
                ay = Const.LENGTH - p.y
            away_coords.append([round(ax, 1), round(ay, 1)])

        ball_holder_idx = None
        ball_holder_team = None
        for i, p in enumerate(game.home.players):
            if p is game.ball_holder:
                ball_holder_idx = i
                ball_holder_team = "home"
                break
        if ball_holder_idx is None:
            for i, p in enumerate(game.away.players):
                if p is game.ball_holder:
                    ball_holder_idx = i
                    ball_holder_team = "away"
                    break

        half = 1 if game.half == "上半时" else 2
        self.frames.append({
            "type": "frame",
            "t": game.time + (0 if half == 1 else 45 * 60),
            "half": half,
            "home": home_coords,
            "away": away_coords,
            "ball_holder": ball_holder_idx,
            "ball_team": ball_holder_team,
            "score": [game.home.point, game.away.point],
        })

    def record_event(self, game, event_type, player=None, target=None, target_xy=None, from_xy=None):
        """Record a match event with optional trajectory data."""
        half = 1 if game.half == "上半时" else 2
        is_home_offence = (game.offence is game.home)

        ev = {
            "type": "event",
            "t": game.time + (0 if half == 1 else 45 * 60),
            "half": half,
            "event": event_type,
            "score": [game.home.point, game.away.point],
        }

        if player:
            for i, p in enumerate(game.home.players):
                if p is player:
                    ev["player"] = i
                    ev["team"] = "home"
                    break
            else:
                for i, p in enumerate(game.away.players):
                    if p is player:
                        ev["player"] = i
                        ev["team"] = "away"
                        break

        if target_xy:
            ev["target_xy"] = self._to_absolute(target_xy[0], target_xy[1], is_home_offence, True)

        if from_xy:
            ev["from_xy"] = self._to_absolute(from_xy[0], from_xy[1], is_home_offence, True)

        if target:
            for i, p in enumerate(game.home.players):
                if p is target:
                    ev["target_player"] = i
                    ev["target_team"] = "home"
                    break
            else:
                for i, p in enumerate(game.away.players):
                    if p is target:
                        ev["target_player"] = i
                        ev["target_team"] = "away"
                        break

        self.frames.append(ev)

    def _to_absolute(self, x, y, is_home_offence, is_offence_coord):
        """Convert engine coords to absolute (home attacks toward y=LENGTH)."""
        if is_home_offence and is_offence_coord:
            return [round(Const.WIDTH - x, 1), round(Const.LENGTH - y, 1)]
        elif not is_home_offence and is_offence_coord:
            return [round(Const.WIDTH - x, 1), round(Const.LENGTH - y, 1)]
        return [round(x, 1), round(y, 1)]

    def save(self, filepath):
        """Write all recorded data to a JSONL file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for frame in self.frames:
                f.write(json.dumps(frame, ensure_ascii=False) + "\n")

    @staticmethod
    def cleanup(replay_dir, max_files=100):
        """Delete oldest files if count exceeds max_files."""
        if not os.path.isdir(replay_dir):
            return
        files = []
        for name in os.listdir(replay_dir):
            path = os.path.join(replay_dir, name)
            if os.path.isfile(path) and name.endswith(".jsonl"):
                files.append((os.path.getmtime(path), path))
        files.sort()
        while len(files) > max_files:
            _, oldest = files.pop(0)
            os.remove(oldest)
