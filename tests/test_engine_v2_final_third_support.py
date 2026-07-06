from server.database import Database
from server.services.bag import BagService
from server.services.squad import SquadService

import random

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.physics import distance
from psl_core.engine_v2.player import PlayerState
from psl_core.engine_v2.value_model import state_value


def _db_cards(qq: int):
    db = Database("psl.db")
    squad = SquadService(db).get_squad(qq)
    bag = BagService(db)
    cards = []
    for card_info in squad.cards:
        detail = bag.get_card_detail(card_info.id, qq)
        cards.append({
            "name": card_info.name,
            "player_id": card_info.player_id,
            "position": card_info.position,
            "color": "silver",
            "overall": card_info.real_overall,
            "abilities": {key: value["value"] for key, value in detail["abilities"].items()},
        })
    return squad.formation, cards


def test_final_third_striker_has_nearby_layoff_support_from_midfield_line():
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    ball = (90.0, 34.0)
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    holder.pos = ball
    holder.target_pos = ball
    holder.state = PlayerState.ON_BALL

    match.home.update_phase(True, False, match.config)
    match.away.update_phase(False, False, match.config)
    match.home.compute_dynamic_positions(ball, match.config, match.pitch, opponent_players=match.away.players)

    support_distances = []
    for player in match.home.players:
        if player.index == holder.index or player.is_goalkeeper or player.is_defender:
            continue
        target = player.choose_off_ball_attack(
            ball,
            match.config,
            match.pitch,
            match.home.attacking_right,
            ball_carrier=holder,
            opponents=match.away.players,
            teammates=match.home.players,
        )
        support_distances.append(distance(target, ball))

    assert min(support_distances) < 27.0


def test_final_third_wide_carrier_gets_early_inside_support_angles():
    random.seed(20260706)
    home_formation, home_cards = _db_cards(10002)
    away_formation, away_cards = _db_cards(10001)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.position == "LW")
    ball = (76.0, 22.0)
    holder.pos = ball
    holder.target_pos = ball
    holder.state = PlayerState.ON_BALL

    match.home.update_phase(True, False, match.config)
    match.away.update_phase(False, False, match.config)
    match.home.compute_dynamic_positions(ball, match.config, match.pitch, opponent_players=match.away.players)

    support_targets = []
    for player in match.home.players:
        if player.index == holder.index or player.is_goalkeeper or player.is_defender:
            continue
        target = player.target_pos
        for _ in range(3):
            target = player.choose_off_ball_attack(
                ball,
                match.config,
                match.pitch,
                match.home.attacking_right,
                ball_carrier=holder,
                opponents=match.away.players,
                teammates=match.home.players,
            )
        target_progress = target[0] / match.pitch.length
        if (
            target[0] < ball[0] - 2.0
            and target_progress > 0.64
            and abs(target[1] - match.pitch.width / 2.0) < abs(ball[1] - match.pitch.width / 2.0)
        ):
            support_targets.append(target)

    assert support_targets
    assert min(distance(target, ball) for target in support_targets) < 24.0


def test_wide_final_third_support_can_target_arc_second_line_space():
    random.seed(202607061)
    home_formation, home_cards = _db_cards(10002)
    away_formation, away_cards = _db_cards(10001)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.position in ("RM", "LM", "RW", "LW"))
    ball = (80.0, 56.0)
    holder.pos = ball
    holder.target_pos = ball
    holder.state = PlayerState.ON_BALL

    match.home.update_phase(True, False, match.config)
    match.away.update_phase(False, False, match.config)
    match.home.compute_dynamic_positions(ball, match.config, match.pitch, opponent_players=match.away.players)

    arc = (match.pitch.length * 0.80, match.pitch.width / 2.0)
    targets = []
    for player in match.home.players:
        if player.index == holder.index or player.is_goalkeeper or player.is_defender:
            continue
        target = player.choose_off_ball_attack(
            ball,
            match.config,
            match.pitch,
            match.home.attacking_right,
            ball_carrier=holder,
            opponents=match.away.players,
            teammates=match.home.players,
        )
        targets.append(target)

    assert min(distance(target, arc) for target in targets) < 11.0


def test_wide_cut_inside_has_nearby_natural_support_without_scripted_goal():
    random.seed(20260707)
    home_formation, home_cards = _db_cards(10002)
    away_formation, away_cards = _db_cards(10001)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.position in ("RM", "LM", "RW", "LW"))
    ball = (78.0, 56.0)
    holder.pos = ball
    holder.target_pos = ball
    holder.state = PlayerState.ON_BALL

    match.home.update_phase(True, False, match.config)
    match.away.update_phase(False, False, match.config)
    match.home.compute_dynamic_positions(ball, match.config, match.pitch, opponent_players=match.away.players)

    cut_lane = (84.0, 42.0)
    support_distances = []
    for player in match.home.players:
        if player.index == holder.index or player.is_goalkeeper or player.is_defender:
            continue
        target = player.choose_off_ball_attack(
            ball,
            match.config,
            match.pitch,
            match.home.attacking_right,
            ball_carrier=holder,
            opponents=match.away.players,
            teammates=match.home.players,
        )
        support_distances.append(distance(target, cut_lane))

    assert min(support_distances) < 13.0


def test_striker_low_quality_window_prefers_support_over_immediate_shot():
    random.seed(202607062)
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    holder.pos = (76.0, 34.0)
    holder.target_pos = holder.pos
    holder.state = PlayerState.ON_BALL
    holder.possession_ticks = 1
    holder.consecutive_carries = 0

    support = next(player for player in match.home.players if player.name == "Vitinha")
    support.pos = (70.0, 42.0)
    support.target_pos = (80.0, 38.0)
    support.tactical_anchor = support.target_pos
    support.base_formation_pos = (52.0, 36.0)

    match.home.update_phase(True, False, match.config)
    match.away.update_phase(False, False, match.config)
    match.home.compute_dynamic_positions(holder.pos, match.config, match.pitch, opponent_players=match.away.players)
    for player in match.home.players:
        if player.index == holder.index or player.is_goalkeeper or player.is_defender:
            continue
        player.choose_off_ball_attack(
            holder.pos,
            match.config,
            match.pitch,
            match.home.attacking_right,
            ball_carrier=holder,
            opponents=match.away.players,
            teammates=match.home.players,
        )

    current_value = state_value(
        holder.pos,
        holder,
        match.home.players,
        match.away.players,
        match.config,
        match.pitch,
        True,
    )
    shoot_score, shoot_details = holder._score_shoot(
        (match.config.pitch_length, match.config.pitch_width / 2.0),
        match.config,
        match.pitch,
        match.away.players,
        distance(holder.pos, (match.config.pitch_length, match.config.pitch_width / 2.0)),
        current_value,
        teammates=match.home.players,
        attacking_right=True,
    )
    hold_value = holder._score_hold_value(
        match.home.players,
        match.away.players,
        match.config,
        match.pitch,
        True,
        pressure=0,
        shoot_score=shoot_score,
        pass_candidates=[],
        space_pass_candidates=[],
    )
    pass_candidates = holder._score_pass_point_options(
        match.home.players,
        match.away.players,
        match.config,
        match.pitch,
        True,
        [opp.pos for opp in match.away.players if not opp.is_goalkeeper],
        [tm.pos for tm in match.home.players if tm.index != holder.index],
        current_value,
    )
    best_support_pass = max(
        (
            item
            for item in pass_candidates
            if item[2].get("target_player_idx") == support.index
            or item[2].get("intended_receiver") == support.index
        ),
        key=lambda item: item[0],
    )

    assert shoot_details["components"]["xg"] < 0.08
    assert shoot_details["components"]["support_release_window"] > 0.0
    assert hold_value.components["opportunity_wait"] > 0.0
    assert max(hold_value.score, best_support_pass[0]) > shoot_score


def test_central_final_third_carrier_creates_second_line_support_targets():
    random.seed(202607063)
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    ball = (82.0, 34.0)
    holder.pos = ball
    holder.target_pos = ball
    holder.state = PlayerState.ON_BALL

    match.home.update_phase(True, False, match.config)
    match.away.update_phase(False, False, match.config)
    match.home.compute_dynamic_positions(ball, match.config, match.pitch, opponent_players=match.away.players)

    support_targets = []
    for player in match.home.players:
        if player.index == holder.index or player.is_goalkeeper or player.is_defender:
            continue
        target = player.choose_off_ball_attack(
            ball,
            match.config,
            match.pitch,
            match.home.attacking_right,
            ball_carrier=holder,
            opponents=match.away.players,
            teammates=match.home.players,
        )
        progress = target[0] / match.pitch.length
        centrality = 1.0 - min(1.0, abs(target[1] - match.pitch.width / 2.0) / (match.pitch.width / 2.0))
        behind_ball = ball[0] - target[0]
        if 0.64 <= progress <= 0.84 and centrality > 0.50 and 3.0 <= behind_ball <= 24.0:
            support_targets.append(target)

    assert support_targets


def test_off_ball_support_respects_neighbor_role_space():
    random.seed(202607064)
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    right_mid = next(player for player in match.home.players if player.name == "Vitinha")
    left_mid = next(player for player in match.home.players if player.name == "Grimaldo")
    ball = (82.0, 34.0)
    holder.pos = ball
    holder.target_pos = ball
    holder.state = PlayerState.ON_BALL
    right_mid.pos = (58.0, 44.0)
    right_mid.tactical_anchor = (74.0, 44.0)
    left_mid.pos = (58.0, 24.0)
    left_mid.tactical_anchor = (74.0, 24.0)

    target = right_mid.choose_off_ball_attack(
        ball,
        match.config,
        match.pitch,
        match.home.attacking_right,
        ball_carrier=holder,
        opponents=match.away.players,
        teammates=match.home.players,
    )

    assert distance(target, right_mid.tactical_anchor) < distance(target, left_mid.tactical_anchor)
