from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.value_model import evaluate_shot, shot_quality_at
from tests.test_engine_v2_shape import _cards


def test_shot_box_zone_uses_penalty_area_geometry():
    match = MatchV2(_cards(), _cards(), "433", "433", config=EngineConfig(total_ticks=10, half_ticks=5))

    assert match._is_attacking_box_pos((89.0, 34.0), attacking_right=True)
    assert not match._is_attacking_box_pos((87.0, 34.0), attacking_right=True)
    assert not match._is_attacking_box_pos((89.0, 5.0), attacking_right=True)

    assert match._is_attacking_box_pos((16.0, 34.0), attacking_right=False)
    assert not match._is_attacking_box_pos((18.0, 34.0), attacking_right=False)
    assert not match._is_attacking_box_pos((16.0, 63.0), attacking_right=False)


def test_outside_box_shot_loses_close_central_bonus():
    config = EngineConfig()
    abilities = {
        "Finishing": 95,
        "Long_Shot": 95,
        "Short_Passing": 80,
        "Long_Passing": 80,
        "Dribbling": 90,
        "Tackling": 50,
        "Defence": 50,
        "Speed": 90,
        "IQ": 90,
        "Heading": 80,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(9, "Shooter", "ST", "gold", abilities=abilities, overall=95)
    opponents = []

    inside = (89.0, 34.0)
    outside = (87.0, 34.0)
    shooter.pos = inside
    inside_xg = shot_quality_at(inside, shooter, opponents, config, True)
    shooter.pos = outside
    outside_xg = shot_quality_at(outside, shooter, opponents, config, True)

    assert outside_xg < inside_xg

    value = evaluate_shot(
        shooter,
        (config.pitch_length, config.pitch_width / 2.0),
        config,
        opponents,
        ((config.pitch_length - outside[0]) ** 2 + (config.pitch_width / 2.0 - outside[1]) ** 2) ** 0.5,
        1.0,
        1.0,
        1.0,
        1.0,
    )
    assert value.components["outside_box"] is True


def test_shot_lane_closure_materially_reduces_xg():
    config = EngineConfig()
    abilities = {
        "Finishing": 90,
        "Long_Shot": 84,
        "Short_Passing": 80,
        "Long_Passing": 80,
        "Dribbling": 88,
        "Tackling": 50,
        "Defence": 50,
        "Speed": 86,
        "IQ": 86,
        "Heading": 80,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(9, "Shooter", "ST", "gold", abilities=abilities, overall=90)
    shooter.pos = (90.0, 34.0)
    defenders = [
        Player(2, "CB1", "CB", "gold", abilities={**abilities, "Defence": 90}, overall=90),
        Player(3, "CB2", "CB", "gold", abilities={**abilities, "Defence": 90}, overall=90),
    ]
    defenders[0].pos = (94.0, 31.5)
    defenders[1].pos = (94.0, 36.5)

    open_xg = shot_quality_at(shooter.pos, shooter, [], config, True)
    closed_xg = shot_quality_at(shooter.pos, shooter, defenders, config, True)

    assert closed_xg < open_xg * 0.62


def test_repeated_carry_under_pressure_adds_shot_opportunity_cost():
    config = EngineConfig()
    abilities = {
        "Finishing": 95,
        "Long_Shot": 95,
        "Short_Passing": 80,
        "Long_Passing": 80,
        "Dribbling": 90,
        "Tackling": 50,
        "Defence": 50,
        "Speed": 90,
        "IQ": 90,
        "Heading": 80,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(9, "Shooter", "ST", "gold", abilities=abilities, overall=95)
    opponents = [
        Player(1, "CB1", "CB", "gold", abilities={**abilities, "Tackling": 90, "Defence": 90}, overall=90),
        Player(2, "CB2", "CB", "gold", abilities={**abilities, "Tackling": 90, "Defence": 90}, overall=90),
    ]
    shooter.pos = (90.0, 34.0)
    opponents[0].pos = (91.0, 31.5)
    opponents[1].pos = (91.0, 36.5)
    goal = (config.pitch_length, config.pitch_width / 2.0)
    dist = ((goal[0] - shooter.pos[0]) ** 2 + (goal[1] - shooter.pos[1]) ** 2) ** 0.5

    shooter.consecutive_carries = 0
    fresh = evaluate_shot(shooter, goal, config, opponents, dist, 1.0, 0.70, 1.0, 1.0)
    shooter.consecutive_carries = 4
    stale = evaluate_shot(shooter, goal, config, opponents, dist, 1.0, 0.70, 1.0, 1.0)

    assert stale.score < fresh.score
    assert stale.components["repeated_carry_pressure"] > fresh.components["repeated_carry_pressure"]


def test_clean_second_line_first_time_shot_gets_readiness_bonus():
    config = EngineConfig()
    abilities = {
        "Finishing": 82,
        "Long_Shot": 88,
        "Short_Passing": 84,
        "Long_Passing": 84,
        "Dribbling": 84,
        "Tackling": 60,
        "Defence": 60,
        "Speed": 82,
        "IQ": 88,
        "Heading": 70,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(8, "Midfielder", "RCM", "gold", abilities=abilities, overall=88)
    shooter.pos = (80.0, 34.0)
    goal = (config.pitch_length, config.pitch_width / 2.0)
    dist = ((goal[0] - shooter.pos[0]) ** 2 + (goal[1] - shooter.pos[1]) ** 2) ** 0.5

    shooter.possession_ticks = 1
    first_time = evaluate_shot(shooter, goal, config, [], dist, 1.0, 1.0, 1.0, 1.0, current_state_value=0.34)
    shooter.possession_ticks = 6
    delayed = evaluate_shot(shooter, goal, config, [], dist, 1.0, 1.0, 1.0, 1.0, current_state_value=0.34)

    assert first_time.score > delayed.score
    assert first_time.components["clean_second_line_shot"] > delayed.components["clean_second_line_shot"]


def test_layoff_to_second_line_gets_first_time_shot_window():
    config = EngineConfig()
    abilities = {
        "Finishing": 82,
        "Long_Shot": 88,
        "Short_Passing": 84,
        "Long_Passing": 84,
        "Dribbling": 84,
        "Tackling": 60,
        "Defence": 60,
        "Speed": 82,
        "IQ": 88,
        "Heading": 70,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(8, "Midfielder", "RCM", "gold", abilities=abilities, overall=88)
    shooter.pos = (82.0, 34.0)
    shooter.last_receive_origin = (90.0, 34.0)
    goal = (config.pitch_length, config.pitch_width / 2.0)
    dist = ((goal[0] - shooter.pos[0]) ** 2 + (goal[1] - shooter.pos[1]) ** 2) ** 0.5

    from_layoff = evaluate_shot(shooter, goal, config, [], dist, 1.0, 1.0, 1.0, 1.0, current_state_value=0.34)
    shooter.last_receive_origin = shooter.pos
    ordinary = evaluate_shot(shooter, goal, config, [], dist, 1.0, 1.0, 1.0, 1.0, current_state_value=0.34)

    assert from_layoff.score > ordinary.score
    assert from_layoff.components["layoff_second_line_window"] > ordinary.components["layoff_second_line_window"]


def test_open_medium_range_shot_gets_small_readiness_window():
    config = EngineConfig()
    abilities = {
        "Finishing": 78,
        "Long_Shot": 84,
        "Short_Passing": 84,
        "Long_Passing": 84,
        "Dribbling": 84,
        "Tackling": 60,
        "Defence": 60,
        "Speed": 82,
        "IQ": 88,
        "Heading": 70,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(7, "WideMid", "RM", "gold", abilities=abilities, overall=84)
    shooter.pos = (83.0, 39.0)
    goal = (config.pitch_length, config.pitch_width / 2.0)
    dist = ((goal[0] - shooter.pos[0]) ** 2 + (goal[1] - shooter.pos[1]) ** 2) ** 0.5

    value = evaluate_shot(shooter, goal, config, [], dist, 0.85, 1.0, 1.0, 1.0, current_state_value=0.32)

    assert 20.0 < value.components["distance"] < 25.0
    assert value.components["open_medium_window"] > 0.0
    assert value.components["shot_readiness"] > 0.0


def test_very_long_low_quality_shot_stays_suppressed():
    config = EngineConfig()
    abilities = {
        "Finishing": 82,
        "Long_Shot": 88,
        "Short_Passing": 84,
        "Long_Passing": 84,
        "Dribbling": 84,
        "Tackling": 60,
        "Defence": 60,
        "Speed": 82,
        "IQ": 88,
        "Heading": 70,
        "GK_Saving": 20,
        "GK_Positioning": 20,
        "GK_Reaction": 20,
    }
    shooter = Player(8, "Midfielder", "RCM", "gold", abilities=abilities, overall=88)
    shooter.pos = (62.0, 34.0)
    goal = (config.pitch_length, config.pitch_width / 2.0)
    dist = ((goal[0] - shooter.pos[0]) ** 2 + (goal[1] - shooter.pos[1]) ** 2) ** 0.5

    value = evaluate_shot(shooter, goal, config, [], dist, 1.0, 1.0, 1.0, 1.0, current_state_value=0.30)

    assert value.components["clean_second_line_shot"] == 0
    assert value.score < 0.02
