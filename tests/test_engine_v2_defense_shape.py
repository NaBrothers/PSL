import random

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.physics import distance
from psl_core.engine_v2.player import Player


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _defender(index: int, position: str, x: float, y: float) -> Player:
    abilities = {key: 72 for key in ABILITY_KEYS}
    abilities.update({"Tackling": 78, "Defence": 78, "Speed": 76, "IQ": 78})
    if position == "GK":
        abilities.update({"GK_Saving": 80, "GK_Positioning": 80, "GK_Reaction": 80})
    player = Player(
        index=index,
        name=f"D{position}{index}",
        position=position,
        color="gold",
        overall=76,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    player.tactical_anchor = (x, y)
    player.formation_pos = (x, y)
    player.base_formation_pos = (x, y)
    return player


def _attacker(index: int, position: str, x: float, y: float) -> Player:
    abilities = {key: 76 for key in ABILITY_KEYS}
    abilities.update({"Finishing": 82, "Dribbling": 82, "Speed": 80, "IQ": 80})
    player = Player(
        index=index,
        name=f"A{position}{index}",
        position=position,
        color="gold",
        overall=78,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    player.tactical_anchor = (x, y)
    player.formation_pos = (x, y)
    player.base_formation_pos = (x, y)
    return player


def _box_defense_context():
    config = EngineConfig()
    pitch = Pitch(config=config)
    defenders = [
        _defender(0, "GK", 102.0, 34.0),
        _defender(1, "RB", 92.0, 52.0),
        _defender(2, "CB", 94.0, 30.0),
        _defender(3, "CB", 95.0, 39.0),
        _defender(4, "LB", 91.0, 17.0),
        _defender(5, "CM", 84.0, 28.0),
        _defender(6, "CM", 83.0, 36.0),
        _defender(7, "CM", 84.0, 44.0),
        _defender(8, "RW", 78.0, 51.0),
        _defender(9, "ST", 79.0, 34.0),
        _defender(10, "LW", 78.0, 17.0),
    ]
    ball = (88.0, 34.0)
    holder = _attacker(9, "ST", *ball)
    attackers = [
        holder,
        _attacker(7, "CAM", 82.0, 30.0),
        _attacker(10, "LW", 86.0, 46.0),
        _attacker(8, "RW", 86.0, 17.0),
    ]
    return config, pitch, ball, holder, attackers, defenders


def test_box_defense_assigns_pressure_without_whole_team_swarming():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()
    random.seed(1)
    actions = {}

    for player in defenders:
        if player.is_goalkeeper:
            continue
        action, details = player.choose_off_ball_defend(
            ball,
            config,
            pitch,
            attacking_right=False,
            ball_carrier=holder,
            opponents=attackers,
            teammates=defenders,
        )
        actions[player.index] = (action, details["target"])

    pressure_actions = {
        idx: action for idx, (action, _) in actions.items()
        if action in ("approach", "tackle")
    }
    support_actions = {
        idx: action for idx, (action, _) in actions.items()
        if action in ("block_lane", "mark_runner")
    }

    assert 1 <= len(pressure_actions) <= 3
    assert len(support_actions) >= 5
    assert actions[6][0] in ("approach", "tackle")
    assert actions[1][0] in ("block_lane", "mark_runner", "hold_position")


def test_stale_ball_carrier_keeps_defensive_attention():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()

    def action_counts(possession_ticks: int):
        holder.possession_ticks = possession_ticks
        counts = {"pressure": 0, "support": 0}
        random.seed(1)
        for player in defenders:
            if player.is_goalkeeper:
                continue
            player.target_pos = player.pos
            player.last_def_action = ""
            action, _ = player.choose_off_ball_defend(
                ball,
                config,
                pitch,
                attacking_right=False,
                ball_carrier=holder,
                opponents=attackers,
                teammates=defenders,
            )
            if action in ("approach", "tackle"):
                counts["pressure"] += 1
            elif action in ("block_lane", "mark_runner"):
                counts["support"] += 1
        return counts

    fresh = action_counts(1)
    stale = action_counts(8)

    assert stale["pressure"] + stale["support"] >= fresh["pressure"] + fresh["support"]


def test_repeated_final_third_carrier_pulls_nearest_defender_closer():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()
    holder.consecutive_carries = 5
    random.seed(2)

    before = {}
    after = {}
    actions = {}
    for player in defenders:
        if player.is_goalkeeper:
            continue
        action, details = player.choose_off_ball_defend(
            ball,
            config,
            pitch,
            attacking_right=False,
            ball_carrier=holder,
            opponents=attackers,
            teammates=defenders,
        )
        before[player.index] = distance(player.pos, ball)
        after[player.index] = distance(details["target"], ball)
        actions[player.index] = action

    nearest_idx = min(before, key=before.get)

    assert actions[nearest_idx] in ("approach", "tackle")
    assert after[nearest_idx] < before[nearest_idx]


def test_pressure_tracking_is_separate_from_tackle_stats():
    from psl_core.engine_v2.match import MatchV2

    config, _, ball, holder, _, defenders = _box_defense_context()
    dummy_cards = [
        {
            "name": player.name,
            "player_id": player.index,
            "position": player.position,
            "color": "gold",
            "overall": player.overall,
            "abilities": player.abilities,
        }
        for player in defenders
    ]
    match = MatchV2(dummy_cards, dummy_cards, "433", "433", config=config)
    match.home.players = [holder]
    match.away.players = defenders
    match.ball.position = ball

    defender_actions = {player.index: "hold_position" for player in defenders}
    defender_actions[6] = "approach"
    defender_new_positions = {6: (89.0, 36.0)}

    match._track_defensive_pressures(
        holder,
        "pass",
        match.away,
        defender_actions,
        defender_new_positions,
        duel_detected=False,
        interception_detected=False,
    )

    presser = defenders[6]
    assert presser.pressures == 1
    assert presser.successful_pressures == 1
    assert presser.tackles_attempted == 0


def test_pressure_tracking_has_short_sequence_cooldown():
    from psl_core.engine_v2.match import MatchV2

    config, _, ball, holder, _, defenders = _box_defense_context()
    dummy_cards = [
        {
            "name": player.name,
            "player_id": player.index,
            "position": player.position,
            "color": "gold",
            "overall": player.overall,
            "abilities": player.abilities,
        }
        for player in defenders
    ]
    match = MatchV2(dummy_cards, dummy_cards, "433", "433", config=config)
    match.home.players = [holder]
    match.away.players = defenders
    match.ball.position = ball

    defender_actions = {player.index: "hold_position" for player in defenders}
    defender_actions[6] = "approach"
    defender_new_positions = {6: (89.0, 36.0)}
    presser = defenders[6]

    match.tick = 10
    match._track_defensive_pressures(holder, "pass", match.away, defender_actions, defender_new_positions, False, False)
    match.tick = 11
    match._track_defensive_pressures(holder, "pass", match.away, defender_actions, defender_new_positions, False, False)
    match.tick = 13
    match._track_defensive_pressures(holder, "pass", match.away, defender_actions, defender_new_positions, False, False)

    assert presser.pressures == 2
    assert presser.successful_pressures == 2


def test_post_carry_pressure_target_gets_local_responsibility_nudge():
    from psl_core.engine_v2.match import MatchV2

    config, _, _, holder, attackers, defenders = _box_defense_context()
    dummy_cards = [
        {
            "name": player.name,
            "player_id": player.index,
            "position": player.position,
            "color": "gold",
            "overall": player.overall,
            "abilities": player.abilities,
        }
        for player in defenders
    ]
    attacker_cards = [
        {
            "name": player.name,
            "player_id": player.index,
            "position": player.position,
            "color": "gold",
            "overall": player.overall,
            "abilities": player.abilities,
        }
        for player in attackers
    ]
    attacker_cards.extend(dummy_cards[: 11 - len(attacker_cards)])
    match = MatchV2(attacker_cards, dummy_cards, "433", "433", config=config)
    match.home.players = attackers
    match.away.players = defenders
    holder = match.home.players[0]
    holder.pos = (90.0, 34.0)
    holder.consecutive_carries = 5
    match.ball.set_held(holder.index, match.home.side, holder.pos)
    center_back = match.away.players[2]
    center_back.pos = (96.0, 32.0)
    center_back.target_pos = (100.0, 28.0)
    before = distance(center_back.target_pos, holder.pos)

    match._adjust_defensive_pressure_targets_after_carry(match.home, match.away, holder, "carry")

    assert distance(center_back.target_pos, holder.pos) < before


def test_arc_protection_keeps_midfield_cover_from_crowding_center_backs():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()
    holder.pos = (89.0, 34.0)
    attackers[1].pos = (82.0, 34.0)
    center_back = defenders[2]
    center_back.pos = (89.5, 32.0)
    midfielder = defenders[6]
    midfielder.pos = (82.0, 34.0)
    random.seed(4)

    cb_action, cb_details = center_back.choose_off_ball_defend(
        ball,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=holder,
        opponents=attackers,
        teammates=defenders,
    )
    mid_action, mid_details = midfielder.choose_off_ball_defend(
        ball,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=holder,
        opponents=attackers,
        teammates=defenders,
    )

    assert cb_action in ("approach", "tackle", "mark_runner", "block_lane")
    assert distance(mid_details["target"], cb_details["target"]) > 4.0

