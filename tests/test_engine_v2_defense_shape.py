import random

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.physics import distance
from psl_core.engine_v2.trace import MatchTrace
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.goal import PlayerGoal


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


def test_defensive_choice_records_goal_trace_state():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()
    config.trace.detail = "full"
    config.trace.include_defense = True
    defender = defenders[6]
    trace = MatchTrace()

    action, details = defender.choose_off_ball_defend(
        ball,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=holder,
        opponents=attackers,
        teammates=defenders,
        tick=12,
        team_side="away",
        trace=trace,
    )

    assert action in ("approach", "tackle", "mark_runner", "block_lane", "hold_position")
    assert defender.current_goal is not None
    assert defender.current_goal.goal_type.startswith("defend_")
    assert defender.current_goal.target_pos == details["target"]
    assert trace.decisions[-1]["goal"]["goal"]["goal_type"].startswith("defend_")


def test_defensive_goal_continuity_keeps_close_existing_target():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()
    random.seed(10)
    config.goal_noise_scale = 0.0
    config.trace.detail = "full"
    config.trace.include_defense = True
    defender = defenders[6]
    existing_target = (82.0, 33.0)
    defender.current_goal = PlayerGoal(
        goal_type="defend_mark_runner",
        target_pos=existing_target,
        value=0.625,
        confidence=0.625,
        created_tick=8,
        last_updated_tick=9,
        context={"action": "mark_runner"},
    )
    defender.last_def_action = "mark_runner"
    defender.last_def_target = existing_target
    trace = MatchTrace()

    action, details = defender.choose_off_ball_defend(
        ball,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=holder,
        opponents=attackers,
        teammates=defenders,
        tick=12,
        team_side="away",
        trace=trace,
    )

    goal_trace = trace.decisions[-1]["goal"]
    assert goal_trace["switched"]
    assert goal_trace["reason"] == "current_defensive_goal_updated"
    assert action in ("approach", "tackle", "mark_runner", "block_lane")
    assert defender.current_goal is not None
    assert defender.current_goal.goal_type.startswith("defend_")


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


def test_post_carry_pressure_adjust_rust_plan_matches_legacy_formula():
    from psl_core.engine_v2.match import MatchV2
    from psl_core.engine_v2.rust_adapter import defensive_pressure_adjust_plan_rust

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
    center_back.movement_intent = "defend_shape"

    rust_plan = defensive_pressure_adjust_plan_rust(
        holder,
        match.home.attacking_right,
        match.away.attacking_right,
        "carry",
        True,
        [p for p in match.away.players if not p.is_goalkeeper and p.state.value != "stunned"],
        config,
    )

    match._adjust_defensive_pressure_targets_after_carry_legacy(match.home, match.away, holder, "carry")
    assert center_back.index in rust_plan
    assert distance(rust_plan[center_back.index]["target"], center_back.target_pos) < 1e-9
    assert rust_plan[center_back.index]["movement_intent"] == center_back.movement_intent


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


def _match_cards(formation: str):
    from psl_core.constants import FORMATION

    cards = []
    for idx, position in enumerate(FORMATION[formation]["positions"]):
        abilities = {key: 76 for key in ABILITY_KEYS}
        abilities.update({"Tackling": 78, "Defence": 78, "Speed": 78, "IQ": 80})
        if position == "GK":
            abilities.update({"GK_Saving": 80, "GK_Positioning": 80, "GK_Reaction": 80})
        cards.append({
            "name": f"{position}{idx}",
            "player_id": idx,
            "position": position,
            "color": "gold",
            "overall": 76,
            "abilities": abilities,
        })
    return cards


def test_kickoff_defense_creates_more_than_one_front_pressure_angle():
    from psl_core.engine_v2.match import MatchV2

    config = EngineConfig()
    match = MatchV2(_match_cards("433"), _match_cards("433"), "433", "433", config=config)
    match._kickoff("home")
    holder = match.home.players[match.ball.holder_idx]

    match.home.update_phase(has_possession=True, ball_contested=False, config=config)
    match.away.update_phase(has_possession=False, ball_contested=False, config=config)
    match.home.compute_dynamic_positions(match.ball.position, config, match.pitch, opponent_players=match.away.players)
    match.away.compute_dynamic_positions(match.ball.position, config, match.pitch, opponent_players=match.home.players)

    random.seed(3)
    front_actions = []
    for player in match.away.players:
        if player.position not in ("LW", "ST", "RW"):
            continue
        action, _ = player.choose_off_ball_defend(
            match.ball.position,
            config,
            match.pitch,
            attacking_right=match.away.attacking_right,
            ball_carrier=holder,
            opponents=match.home.players,
            teammates=match.away.players,
        )
        front_actions.append(action)

    assert sum(action in ("approach", "tackle") for action in front_actions) >= 2


def test_center_backs_close_central_shot_lane_without_needing_a_tackle():
    config, pitch, ball, holder, attackers, defenders = _box_defense_context()
    random.seed(5)

    lane_distances = []
    for defender in (defenders[2], defenders[3]):
        defender.target_pos = defender.pos
        defender.last_def_action = ""
        defender.current_goal = None
        action, details = defender.choose_off_ball_defend(
            ball,
            config,
            pitch,
            attacking_right=False,
            ball_carrier=holder,
            opponents=attackers,
            teammates=defenders,
        )
        target = details["target"]
        assert action in ("approach", "tackle", "block_lane", "mark_runner")
        assert ball[0] <= target[0] <= pitch.length - 0.5
        lane_distances.append(abs(target[1] - pitch.width / 2.0))

    assert min(lane_distances) < 4.5


def test_dangerous_off_ball_runner_gets_goalside_marking_attention():
    config = EngineConfig()
    pitch = Pitch(config=config)
    ball = (88.0, 56.0)
    holder = _attacker(8, "RW", *ball)
    striker = _attacker(9, "ST", 93.0, 34.0)
    cam = _attacker(7, "CAM", 82.0, 34.0)
    attackers = [holder, striker, cam]
    defenders = [
        _defender(0, "GK", 102.0, 34.0),
        _defender(2, "CB", 96.0, 37.0),
        _defender(3, "CB", 96.0, 31.0),
        _defender(5, "CM", 84.0, 34.0),
        _defender(1, "RB", 92.0, 52.0),
        _defender(4, "LB", 91.0, 17.0),
    ]

    for seed in range(6):
        random.seed(seed)
        marked_by_center_back = []
        for defender in defenders:
            if defender.is_goalkeeper:
                continue
            defender.target_pos = defender.pos
            defender.last_def_action = ""
            defender.current_goal = None
            action, details = defender.choose_off_ball_defend(
                ball,
                config,
                pitch,
                attacking_right=False,
                ball_carrier=holder,
                opponents=attackers,
                teammates=defenders,
            )
            if defender.position == "CB" and distance(details["target"], striker.pos) < 5.5:
                marked_by_center_back.append((action, defender.current_goal.goal_type if defender.current_goal else ""))

        assert marked_by_center_back
        assert any(goal == "defend_mark_runner" or action == "mark_runner" for action, goal in marked_by_center_back)
