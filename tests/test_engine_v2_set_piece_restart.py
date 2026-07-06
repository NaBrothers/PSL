from psl_core.engine_v2.ball import BallState
from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from tests.test_engine_v2_shape import _cards


def test_goal_kick_dead_ball_wait_moves_players_toward_restart_shape():
    config = EngineConfig(total_ticks=20, half_ticks=10, goal_kick_restart_ticks=4)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("goal_kick", "home", restart_ticks=4)
    match.ball.position = (0.5, match.pitch.width / 2.0)

    striker = next(player for player in match.away.players if player.position == "ST")
    striker.pos = (8.0, match.pitch.width / 2.0)
    striker.target_pos = striker.pos
    home_cb = next(player for player in match.home.players if player.position == "LCB")
    home_cb.pos = (92.0, match.pitch.width / 2.0)
    home_cb.target_pos = home_cb.pos

    match._tick()
    match._tick()

    assert match.ball.state == BallState.DEAD
    assert striker.pos[0] > 12.0
    assert home_cb.pos[0] < 90.0


def test_goal_kick_restart_uses_prepared_shape_before_keeper_distribution():
    config = EngineConfig(total_ticks=20, half_ticks=10, goal_kick_restart_ticks=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("goal_kick", "home", restart_ticks=1)
    match.ball.position = (0.5, match.pitch.width / 2.0)

    away_st = next(player for player in match.away.players if player.position == "ST")
    away_st.pos = (7.0, match.pitch.width / 2.0)
    away_st.target_pos = away_st.pos
    home_gk = match.home.goalkeeper

    match._tick()

    assert match.ball.state == BallState.HELD
    assert match.ball.holder_team == "home"
    assert match.ball.holder_idx == home_gk.index
    assert home_gk.pos[0] < 10.0
    assert away_st.pos[0] > 16.5


def test_goal_kick_shape_spreads_short_and_long_options():
    config = EngineConfig(total_ticks=20, half_ticks=10, goal_kick_restart_ticks=4)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("goal_kick", "home", restart_ticks=4)

    match._prepare_restart_shape(force=True)

    defenders = [player for player in match.home.players if player.position in ("LB", "LCB", "RCB", "RB")]
    attackers = [player for player in match.home.players if player.position in ("LW", "ST", "RW")]
    opponents = [player for player in match.away.players if not player.is_goalkeeper]

    assert min(player.target_pos[0] for player in defenders) > 18.0
    assert max(player.target_pos[0] for player in attackers) > 62.0
    assert min(player.target_pos[0] for player in opponents) >= 30.0
    assert max(player.target_pos[1] for player in defenders) - min(player.target_pos[1] for player in defenders) > 34.0


def test_away_goal_kick_defending_shape_does_not_collapse_near_box():
    config = EngineConfig(total_ticks=20, half_ticks=10, goal_kick_restart_ticks=4)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("goal_kick", "away", restart_ticks=4)

    match._prepare_restart_shape(force=True)

    home_outfield = [player for player in match.home.players if not player.is_goalkeeper]
    home_forwards = [player for player in match.home.players if player.position in ("LW", "ST", "RW")]
    away_defenders = [player for player in match.away.players if player.position in ("LB", "LCB", "RCB", "RB")]

    assert max(player.target_pos[0] for player in home_outfield) <= match.pitch.length - 30.0
    assert min(player.target_pos[0] for player in home_forwards) <= match.pitch.length - 34.0
    assert max(player.target_pos[1] for player in away_defenders) - min(player.target_pos[1] for player in away_defenders) > 34.0


def test_goalkeeper_goal_kick_distribution_uses_valued_teammate_target():
    config = EngineConfig(total_ticks=20, half_ticks=10, goal_kick_restart_ticks=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("goal_kick", "home", restart_ticks=1)
    match._prepare_restart_shape(force=True)
    gk = match.home.goalkeeper

    action, details = gk.choose_on_ball(
        match.home.players,
        match.away.players,
        match.config,
        match.pitch,
        match.home.attacking_right,
    )
    target_idx = details.get("target_player_idx", -1)
    nearest_opp = min(
        ((opp.pos[0] - details["target"][0]) ** 2 + (opp.pos[1] - details["target"][1]) ** 2) ** 0.5
        for opp in match.away.players
        if not opp.is_goalkeeper
    )

    assert action == "pass"
    assert 0 <= target_idx < len(match.home.players)
    assert details["success_prob"] > 0.15
    assert nearest_opp > 5.0


def test_kickoff_dead_ball_wait_returns_players_to_own_halves():
    config = EngineConfig(total_ticks=20, half_ticks=10)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("kickoff", "away", restart_ticks=2)
    match.ball.position = match.pitch.center

    home_st = next(player for player in match.home.players if player.position == "ST")
    away_st = next(player for player in match.away.players if player.position == "ST")
    home_st.pos = (92.0, match.pitch.width / 2.0)
    home_st.target_pos = home_st.pos
    away_st.pos = (12.0, match.pitch.width / 2.0)
    away_st.target_pos = away_st.pos

    match._tick()
    match._tick()

    assert home_st.pos[0] < match.pitch.length / 2.0
    assert away_st.pos[0] > match.pitch.length / 2.0
    assert match.ball.state == BallState.HELD
    assert match.ball.holder_team == "away"
