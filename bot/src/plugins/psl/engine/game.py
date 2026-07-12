from engine.team import Team
from engine.const import Const
from engine.types import MatchResult, TeamStats, GoalRecord
from engine.types import MatchEvent as PureMatchEvent
from utils.image import toImage
from config import PROJECT_DIR
import json
import os
import random
import re
import time
from dataclasses import dataclass


@dataclass
class MatchEvent:
    minute: int
    second: int
    seq: int
    event_type: str
    text: str
    home_score: int = 0
    away_score: int = 0
    importance: int = 1
    team: object = None
    player: object = None
    xg: float = 0
    target: object = None
    result: str = ""


class Game:

    BROADCAST_INTERVAL = 270

    def __init__(self, matcher, user1, user2, npc=-1, difficulty=0, seed=None, rng=None):
        self.matcher = matcher
        self.home = Team(user1)
        self.away = Team(user2, npc, difficulty)
        self.half = "上半时"
        self.timeline = []
        self.match_events = []
        self.mode = Const.MODE_NORMAL
        self.seed = seed
        self.rng = rng or random.Random(seed)
        self.event_seq = 0

    def _load_engine_config(self):
        if hasattr(self, "_engine_config"):
            return self._engine_config

        from psl_core.engine_v2.config import EngineConfig, load_config_from_service

        config = EngineConfig()
        try:
            from server.database import Database
            from server.services.game_config import GameConfigService

            db_path = os.environ.get("PSL_DB_PATH", os.path.join(PROJECT_DIR, "psl.db"))
            config_db = Database(db_path)
            try:
                config_service = GameConfigService(config_db)
                config = load_config_from_service(config_service)
            finally:
                config_db.close()
        except Exception:
            # A missing configuration store must not reintroduce an engine fallback.
            pass

        self._engine_config = config
        return config
    def _formation_key(self, team):
        formation = getattr(team.coach, "formation", "442")
        return formation if formation else "442"

    def _rust_card_payload(self, player):
        card = player.card
        colored_name = card.getNameWithColor()
        color_match = re.match(r"/~([^/])", colored_name)
        try:
            overall = card.getRealOverall(player.position)
        except Exception:
            overall = getattr(card, "overall", 50)
        return {
            "name": player.getName(False),
            "player_id": getattr(card.player, "ID", ""),
            "position": player.position,
            "color": color_match.group(1) if color_match else "w",
            "overall": overall,
            "abilities": dict(player.ability),
        }

    def _apply_rust_player_stats(self, team, stats):
        field_map = {
            "goals": "goals",
            "assists": "assists",
            "shots": "shoots",
            "shots_on_target": "shoots_in_target",
            "xg": "xg",
            "npxg": "npxg",
            "post_shot_xg": "post_shot_xg",
            "big_chances": "big_chances",
            "big_chances_missed": "big_chances_missed",
            "passes": "passes",
            "completed_passes": "successful_passes",
            "key_passes": "key_passes",
            "xa": "xa",
            "progressive_passes": "progressive_passes",
            "passes_into_final_third": "passes_into_final_third",
            "passes_into_box": "passes_into_box",
            "long_passes": "long_passes",
            "completed_long_passes": "completed_long_passes",
            "crosses": "crosses",
            "successful_crosses": "successful_crosses",
            "carries": "carries",
            "progressive_carries": "progressive_carries",
            "carries_into_final_third": "carries_into_final_third",
            "carries_into_box": "carries_into_box",
            "take_ons": "take_ons",
            "successful_take_ons": "successful_take_ons",
            "tackles_attempted": "tackle_attempts",
            "tackles_won": "tackles",
            "interceptions": "interceptions",
            "blocks": "blocks",
            "clearances": "clearances",
            "pressures": "pressures",
            "successful_pressures": "successful_pressures",
            "turnovers": "turnovers",
            "dispossessed": "dispossessed",
            "offsides": "offsides",
            "saves": "saves",
            "goals_conceded": "goals_conceded",
            "psxg_faced": "psxg_faced",
            "goals_prevented": "goals_prevented",
        }
        for index, player in enumerate(team.players):
            player_stats = stats[index] if index < len(stats) else {}
            for source, target in field_map.items():
                setattr(player, target, player_stats.get(source, 0))

            player.short_passes = max(0, player.passes - player.long_passes)
            player.completed_short_passes = max(
                0, player.successful_passes - player.completed_long_passes
            )
            player.dribbles = player.successful_take_ons
            player.shot_log = list(player_stats.get("shot_log", []))
            player.position_samples = [
                tuple(sample) for sample in player_stats.get("position_samples", [])
            ]
            player.goals_detailed = []
            player.current_carry_progress = 0

            pass_network = {}
            for receiver_idx, count in player_stats.get("pass_network", {}).items():
                try:
                    receiver = team.players[int(receiver_idx)]
                except (ValueError, IndexError, TypeError):
                    continue
                pass_network[id(receiver)] = count
            player.pass_connections = pass_network

    def _find_rust_player(self, team, name):
        return next(
            (player for player in team.players if player.getName(False) == name),
            None,
        )

    def _find_rust_identity(self, team, identity):
        if not isinstance(identity, dict):
            return None
        player_id = identity.get("player_id")
        if player_id is not None:
            for player in team.players:
                card_player_id = getattr(player.card.player, "ID", None)
                if str(card_player_id) == str(player_id):
                    return player
        return self._find_rust_player(team, identity.get("name", ""))

    def _apply_rust_events(self, result, presentation):
        self.timeline = []
        self.match_events = []
        self.event_seq = 0
        raw_by_seq = {
            int(event.get("seq", 0)): event
            for event in result.events
        }

        for event in presentation.events:
            raw = raw_by_seq.get(event.seq, {})
            side = event.team_side or raw.get("team_side", "home")
            team = self.home if side == "home" else self.away
            player = self._find_rust_identity(team, raw.get("player"))
            opposing_team = self.away if side == "home" else self.home
            target_identity = raw.get("target_player")
            target_team = opposing_team if raw.get("event_type") in (
                "shot",
                "interception",
                "tackle",
            ) else team
            target = self._find_rust_identity(target_team, target_identity)
            outcome = raw.get("outcome", "")
            event_type = raw.get("event_type", event.event_type)
            if event_type == "shot":
                if outcome == "goal":
                    event_type = "goal"
                    assister = self._find_rust_identity(
                        team, raw.get("assist_player")
                    )
                    if player is not None:
                        player.goals_detailed.append(event.minute)
                        self.timeline.append(
                            (event.minute, team, player, assister)
                        )
                    target = assister
                elif outcome == "saved":
                    event_type = "save"
            self.match_events.append(MatchEvent(
                minute=event.minute,
                second=event.second,
                seq=event.seq,
                event_type=event_type,
                text=event.text,
                home_score=int((raw.get("score_before") or [0, 0])[0]),
                away_score=int((raw.get("score_before") or [0, 0])[1]),
                importance=event.importance,
                team=team,
                player=player,
                xg=float(raw.get("xg", 0) or 0),
                target=target,
                result=outcome,
            ))
        self.event_seq = max(
            (event.seq for event in self.match_events),
            default=0,
        )

    def _apply_rust_team_stats(self, team, raw_stats, score):
        team.getStats()
        possession = float(raw_stats.get("possession", 50.0))
        team.point = int(score)
        team.goals = int(score)
        team.control = int(round(possession * 54.0))
        team.shots_in_box = sum(
            1
            for player in team.players
            for shot in player.shot_log
            if shot.get("in_box")
        )
        team.shots_outside_box = max(0, team.shoots - team.shots_in_box)
        team.xg = round(sum(player.xg for player in team.players), 3)
        team.open_play_xg = team.xg
        team.set_piece_xg = 0
        team.npxg = round(sum(player.npxg for player in team.players), 3)
        team.adjusted_xg = team.xg
        team.xt = 0
        team.final_third_entries = sum(
            player.passes_into_final_third + player.carries_into_final_third
            for player in team.players
        )
        team.box_entries = sum(
            player.passes_into_box + player.carries_into_box
            for player in team.players
        )
        team.key_passes = sum(player.key_passes for player in team.players)
        team.box_touches = team.box_entries
        team.big_chances = sum(player.big_chances for player in team.players)
        team.corners = int(raw_stats.get("corners", 0))
        team.offsides_forced = int(raw_stats.get("offsides_forced", 0))
        team.possessions = max(1, team.turnovers + team.shoots + team.passes // 4)
        team.avg_possession_duration = team.control / team.possessions
        team.zone_stats = {
            "left_channel_attacks": 0,
            "center_channel_attacks": 0,
            "right_channel_attacks": 0,
            "final_third_entries": team.final_third_entries,
            "box_entries": team.box_entries,
            "shots_in_box": team.shots_in_box,
            "shots_outside_box": team.shots_outside_box,
        }

    def _save_rust_replay(self):
        replay_data = getattr(self, "_rust_replay_data", None)
        if not replay_data:
            return ""

        header = replay_data[0] if replay_data[0].get("type") == "header" else None
        if header is not None:
            header.setdefault("home", {})["name"] = self.home.coach.name
            header.setdefault("away", {})["name"] = self.away.coach.name

        replay_dir = os.path.join(
            os.environ.get("PSL_PROJECT_DIR", PROJECT_DIR), "data", "replays"
        )
        os.makedirs(replay_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        match_id = format(getattr(self, "_rust_match_seed", 0), "016x")
        score = f"{self.home.point}-{self.away.point}"
        home_name = self.home.coach.name.replace(" ", "_")
        away_name = self.away.coach.name.replace(" ", "_")
        filename = f"{timestamp}_{match_id}_{home_name}_{away_name}_{score}.jsonl"
        filepath = os.path.join(replay_dir, filename)
        with open(filepath, "w", encoding="utf-8") as replay_file:
            for frame in replay_data:
                replay_file.write(json.dumps(frame, ensure_ascii=False) + "\n")
        replay_files = sorted(
            (
                (os.path.getmtime(os.path.join(replay_dir, name)), os.path.join(replay_dir, name))
                for name in os.listdir(replay_dir)
                if name.endswith(".jsonl")
                and os.path.isfile(os.path.join(replay_dir, name))
            ),
            key=lambda item: item[0],
        )
        for _, old_path in replay_files[:-100]:
            os.remove(old_path)
        return filepath

    def _run_rust_match(self):
        from psl_core.engine_v2.match import MatchV2
        from psl_core.presentation import build_match_presentation

        config = self._load_engine_config()
        self._rust_match_seed = (
            self.seed if self.seed is not None else self.rng.getrandbits(64)
        )
        match = MatchV2(
            [self._rust_card_payload(player) for player in self.home.players],
            [self._rust_card_payload(player) for player in self.away.players],
            self._formation_key(self.home),
            self._formation_key(self.away),
            config=config,
            seed=self._rust_match_seed,
        )
        result = match.run()
        self.engine_trace_id = result.trace_id
        self.engine_backend = "rust_match_v2"
        self._rust_replay_data = match.get_replay_data()
        self._rust_result = result
        self.match_presentation = build_match_presentation(
            result,
            self.home.coach.name,
            self.away.coach.name,
        )
        self._apply_rust_player_stats(self.home, result.home_player_stats)
        self._apply_rust_player_stats(self.away, result.away_player_stats)
        self._apply_rust_events(result, self.match_presentation)
        self._apply_rust_team_stats(self.home, result.home_stats, result.home_score)
        self._apply_rust_team_stats(self.away, result.away_stats, result.away_score)
        self.half = "下半时"
        self.time = 45 * 60
        return result


    async def start(self, mode):
        return await self._start_rust_match(mode)

    async def _start_rust_match(self, mode):
        self.mode = mode
        if self.mode != Const.MODE_QUICK:
            await self.send(
                "主 " + self.home.coach.name + " : "
                + self.away.coach.name + " 客\n比赛开始"
            )

        self._run_rust_match()

        if self.mode not in (Const.MODE_QUICK, Const.MODE_SILENCE):
            for lines in self.match_presentation.broadcasts:
                await self.send("\n".join(lines))

        stats = await self.printStats()
        if self.mode in (Const.MODE_NORMAL, Const.MODE_QUICK):
            self.replay_path = self._save_rust_replay()
        else:
            self.replay_path = ""
        return stats


    async def send(self, str):
        if self.mode == Const.MODE_QUICK or self.mode == Const.MODE_SILENCE:
            return
        await self.matcher.send(toImage(str))


    async def printStats(self):
        self.home.getStats()
        self.away.getStats()

        if self.mode == Const.MODE_SILENCE:
            return

        report = self.match_presentation.report
        if report:
            await self.matcher.send(toImage("[比赛战报]\n" + report))

        detail_msg = self.match_presentation.stats_text
        await self.matcher.send(toImage(detail_msg))
        return detail_msg


    def run_simulation(self):
        """Run the full match simulation without any IO. Returns MatchResult."""
        self.mode = Const.MODE_SILENCE
        self._run_rust_match()
        result = self.to_result()
        self.replay_path = self._save_rust_replay()
        result.replay_path = self.replay_path
        return result

    def to_result(self) -> MatchResult:
        """Convert internal game state to a pure MatchResult data object."""
        self.home.getStats()
        self.away.getStats()

        def _team_stats(team) -> TeamStats:
            return TeamStats(
                name=team.coach.name,
                point=team.point,
                control=team.control,
                shoots=team.shoots,
                shoots_in_target=team.shoots_in_target,
                goals=team.goals,
                shots_in_box=team.shots_in_box,
                shots_outside_box=team.shots_outside_box,
                passes=team.passes,
                successful_passes=team.successful_passes,
                progressive_passes=team.progressive_passes,
                passes_into_final_third=team.passes_into_final_third,
                passes_into_box=team.passes_into_box,
                long_passes=team.long_passes,
                completed_long_passes=team.completed_long_passes,
                short_passes=team.short_passes,
                completed_short_passes=team.completed_short_passes,
                crosses=team.crosses,
                successful_crosses=team.successful_crosses,
                corners=team.corners,
                final_third_entries=team.final_third_entries,
                box_entries=team.box_entries,
                dribbles=team.dribbles,
                carries=team.carries,
                progressive_carries=team.progressive_carries,
                carries_into_final_third=team.carries_into_final_third,
                carries_into_box=team.carries_into_box,
                take_ons=team.take_ons,
                successful_take_ons=team.successful_take_ons,
                assists=team.assists,
                tackles=team.tackles,
                tackle_attempts=team.tackle_attempts,
                interceptions=team.interceptions,
                blocks=team.blocks,
                clearances=team.clearances,
                pressures=team.pressures,
                successful_pressures=team.successful_pressures,
                defensive_actions=team.defensive_actions,
                turnovers=team.turnovers,
                offsides=team.offsides,
                offsides_forced=team.offsides_forced,
                saves=team.saves,
                xg=team.xg,
                open_play_xg=team.open_play_xg,
                set_piece_xg=team.set_piece_xg,
                npxg=team.npxg,
                post_shot_xg=team.post_shot_xg,
                psxg_faced=team.psxg_faced,
                goals_prevented=team.goals_prevented,
                adjusted_xg=team.adjusted_xg,
                xt=team.xt,
                key_passes=team.key_passes,
                box_touches=team.box_touches,
                big_chances=team.big_chances,
                possessions=team.possessions,
                avg_possession_duration=team.avg_possession_duration,
                goals_detailed=team.goals_detailed,
                player_stats=team.player_stats,
                position_stats=team.position_stats,
                zone_stats=team.zone_stats,
            )

        events = []
        for ev in self.match_events:
            team_side = "home" if ev.team == self.home else "away"
            player_name = ev.player.getName() if ev.player else ""
            target_name = ev.target.getName() if ev.target else ""
            events.append(PureMatchEvent(
                minute=ev.minute,
                second=ev.second,
                seq=ev.seq,
                event_type=ev.event_type,
                text=ev.text,
                home_score=ev.home_score,
                away_score=ev.away_score,
                importance=ev.importance,
                team_side=team_side,
                player_name=player_name,
                xg=ev.xg,
                target_name=target_name,
                result=ev.result,
            ))

        timeline = []
        for item in self.timeline:
            team_side = "home" if item[1] == self.home else "away"
            scorer_name = item[2].getName() if item[2] else ""
            assister_name = item[3].getName() if item[3] else None
            timeline.append(GoalRecord(
                minute=item[0],
                team_side=team_side,
                scorer_name=scorer_name,
                assister_name=assister_name,
            ))

        return MatchResult(
            home_stats=_team_stats(self.home),
            away_stats=_team_stats(self.away),
            events=events,
            timeline=timeline,
        )
