import random

from psl_core.engine_v2.ball import BallFlight, FlightType
from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.physics import distance
from tests.test_engine_v2_shape import _cards


def test_incomplete_pass_keeps_residual_loose_ball_roll():
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    # Put the target far enough from everyone so it becomes a 50/50 ball.
    flight = BallFlight(
        origin=(30.0, 10.0),
        target=(65.0, 12.0),
        flight_type=FlightType.SHORT_PASS,
        speed=config.ball_pass_speed,
        ticks_total=1,
        ticks_elapsed=1,
        passer_idx=1,
        passer_team="home",
    )
    match.ball.flight = flight
    match.ball.position = flight.target

    match._resolve_flight_arrival()
    first_pos = match.ball.position
    first_velocity = match.ball.loose_velocity

    assert match.ball.state.value == "contested"
    assert distance(first_velocity, (0.0, 0.0)) > 0.1

    match._tick_contested()
    second_pos = match.ball.position

    assert distance(first_pos, second_pos) > 0.1


def test_residual_loose_ball_roll_scales_with_flight_speed():
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    slow_flight = BallFlight(
        origin=(20.0, 20.0),
        target=(55.0, 20.0),
        flight_type=FlightType.SHORT_PASS,
        speed=10.0,
        ticks_total=1,
        ticks_elapsed=1,
        passer_idx=1,
        passer_team="home",
    )
    fast_flight = BallFlight(
        origin=(20.0, 24.0),
        target=(55.0, 24.0),
        flight_type=FlightType.LONG_PASS,
        speed=24.0,
        ticks_total=1,
        ticks_elapsed=1,
        passer_idx=1,
        passer_team="home",
    )

    slow_velocity = match._residual_ball_velocity(slow_flight, 0.30)
    fast_velocity = match._residual_ball_velocity(fast_flight, 0.30)

    assert distance(fast_velocity, (0.0, 0.0)) > distance(slow_velocity, (0.0, 0.0)) * 1.7


def test_ball_flight_does_not_pull_full_team_to_landing_point():
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    flight = BallFlight(
        origin=(30.0, 10.0),
        target=(78.0, 52.0),
        flight_type=FlightType.SHORT_PASS,
        speed=config.ball_pass_speed,
        ticks_total=3,
        ticks_elapsed=1,
        passer_idx=1,
        passer_team="home",
    )
    match.ball.set_flight(flight)
    before = [player.target_pos for player in match.home.players + match.away.players]

    match._move_all_players_flight()
    players = match.home.players + match.away.players
    distances = [
        distance(player.target_pos, flight.target)
        for player in players
        if not player.is_goalkeeper
    ]
    near_target = [d for d in distances if d < 14.0]
    shape_players = [d for d in distances if d >= 14.0]

    assert [player.target_pos for player in players] != before
    assert near_target
    assert len(shape_players) > len(near_target)


def test_pass_to_space_arrival_uses_receiver_run_intent():
    random.seed(3)
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    receiver = match.home.players[8]
    defender = match.away.players[2]
    target = (74.0, 34.0)
    receiver.pos = (66.0, 34.0)
    receiver.target_pos = target
    receiver.tactical_anchor = target
    defender.pos = (69.0, 34.0)
    defender.target_pos = defender.pos
    flight = BallFlight(
        origin=(52.0, 48.0),
        target=target,
        flight_type=FlightType.SHORT_PASS,
        speed=config.ball_pass_speed,
        ticks_total=2,
        ticks_elapsed=2,
        passer_idx=7,
        passer_team="home",
        is_pass_to_space=True,
        intended_receiver_idx=receiver.index,
    )
    match.ball.flight = flight
    match.ball.position = flight.target

    match._resolve_flight_arrival()

    assert match.ball.holder_team == "home"
    assert match.ball.holder_idx == receiver.index


def test_normal_pass_arrival_can_be_intercepted_when_target_is_occupied():
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    passer = match.home.players[7]
    receiver = match.home.players[8]
    defender = match.away.players[2]
    target = (74.0, 34.0)
    passer.pos = (58.0, 34.0)
    receiver.pos = (80.0, 34.0)
    defender.pos = (73.0, 34.0)
    flight = BallFlight(
        origin=passer.pos,
        target=target,
        flight_type=FlightType.SHORT_PASS,
        speed=config.ball_pass_speed,
        ticks_total=2,
        ticks_elapsed=2,
        passer_idx=passer.index,
        passer_team="home",
        is_pass_to_space=False,
        intended_receiver_idx=receiver.index,
    )
    match.ball.flight = flight
    match.ball.position = flight.target

    match._resolve_flight_arrival()

    assert match.ball.holder_team == "away"
    assert match.ball.holder_idx == defender.index
    assert defender.interceptions == 1


def test_pass_events_are_unified_with_target_kind_metadata():
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    passer = match.home.players[7]
    receiver = match.home.players[8]
    passer.pos = (58.0, 34.0)
    receiver.pos = (74.0, 34.0)
    receiver.target_pos = receiver.pos
    receiver.abilities["IQ"] = 100

    match._execute_pass_phase3(
        passer,
        {
            "target": receiver.pos,
            "target_player_idx": receiver.index,
            "is_long": False,
            "lane_risk": 0.0,
            "components": {"target_kind": "feet"},
        },
        match.home,
        match.away,
        interception_interaction=None,
    )
    pass_event = match.trace.entries[-1].data

    assert pass_event["action"] == "pass"
    assert pass_event["pass_type"] == "short_pass"
    assert pass_event["target_kind"] == "feet"

    match.ball.flight.ticks_elapsed = match.ball.flight.ticks_total
    match.ball.position = receiver.pos
    match._resolve_flight_arrival()
    receive_event = match.trace.entries[-1].data

    assert receive_event["action"] == "receive"
    assert receive_event["receive_kind"] == "feet"
