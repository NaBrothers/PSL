"""Replay recorder.

The file format is frame-based: each frame contains the positions and the
optional ball flight that starts from that exact frame.
"""

import json
import os
import re

from engine.const import Const


class ReplayRecorder:
    def __init__(self):
        self.lines = []
        self._home_team = None
        self._away_team = None

    def record_header(self, home_team, away_team, home_formation, away_formation):
        self._home_team = home_team
        self._away_team = away_team
        def player_meta(player):
            colored = player.card.getNameWithColor()
            match = re.match(r"/~([^/])(.+)/", colored)
            color = match.group(1) if match else "w"
            return {"name": player.card.player.Name, "pos": player.position, "color": color}
        self.lines.append({
            "type": "header",
            "home": {
                "name": home_team.coach.name,
                "players": [player_meta(p) for p in home_team.players],
            },
            "away": {
                "name": away_team.coach.name,
                "players": [player_meta(p) for p in away_team.players],
            },
            "formation_home": home_formation,
            "formation_away": away_formation,
            "field": {"width": Const.WIDTH, "length": Const.LENGTH},
        })

    def record_frame(self, game, ball_flight=None, event_text=None, pause_ms=None, cut=False):
        if hasattr(game, "prepare_replay_frame"):
            game.prepare_replay_frame()
        half = 1 if game.half == "上半时" else 2
        holder_idx, holder_team = self._find_ball_holder(game)
        frame = {
            "type": "frame",
            "t": game.time + (0 if half == 1 else 45 * 60),
            "half": half,
            "home": [self._player_to_absolute(game, p) for p in game.home.players],
            "away": [self._player_to_absolute(game, p) for p in game.away.players],
            "ball_holder": holder_idx,
            "ball_team": holder_team,
            "score": [game.home.point, game.away.point],
        }
        if ball_flight:
            frame["ball_flight"] = ball_flight
        if event_text:
            frame["event_text"] = event_text
        if pause_ms:
            frame["pause_ms"] = pause_ms
        if cut:
            frame["cut"] = True
        self.lines.append(frame)
        return frame

    def make_ball_flight(self, game, from_player, to_xy, flight_type="shot", on_target=None):
        flight = {
            "from": self._player_to_absolute(game, from_player),
            "to": self._offence_coord_to_absolute(game, to_xy[0], to_xy[1]),
            "type": flight_type,
        }
        if on_target is not None:
            flight["on_target"] = on_target
        return flight

    def make_pass_flight(self, game, from_player, to_player):
        return {
            "from": self._player_to_absolute(game, from_player),
            "to": self._player_to_absolute(game, to_player),
            "type": "pass",
        }

    def _player_to_absolute(self, game, player):
        team = self._team_of(player)
        is_home_offence = game.offence is game.home
        if team == "home":
            if is_home_offence:
                return [round(player.x, 1), round(Const.LENGTH - player.y, 1)]
            return [round(Const.WIDTH - player.x, 1), round(player.y, 1)]
        if is_home_offence:
            return [round(player.x, 1), round(Const.LENGTH - player.y, 1)]
        return [round(Const.WIDTH - player.x, 1), round(player.y, 1)]

    def _offence_coord_to_absolute(self, game, x, y):
        if game.offence is game.home:
            return [round(x, 1), round(Const.LENGTH - y, 1)]
        return [round(Const.WIDTH - x, 1), round(y, 1)]

    def _team_of(self, player):
        if self._home_team:
            for p in self._home_team.players:
                if p is player:
                    return "home"
        if self._away_team:
            for p in self._away_team.players:
                if p is player:
                    return "away"
        return None

    def _find_ball_holder(self, game):
        for i, p in enumerate(game.home.players):
            if p is game.ball_holder:
                return i, "home"
        for i, p in enumerate(game.away.players):
            if p is game.ball_holder:
                return i, "away"
        return None, None

    def save(self, filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for line in self.lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

    @staticmethod
    def cleanup(replay_dir, max_files=100):
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
