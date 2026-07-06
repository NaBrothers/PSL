from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.physics import distance
from tests.test_engine_v2_shape import _cards


def test_contested_ball_uses_local_race_not_full_team_swarm():
    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    ball_pos = (65.0, match.pitch.width / 2.0)
    match.ball.set_contested(ball_pos)

    before_targets = [player.target_pos for player in match.home.players + match.away.players]
    match._tick_contested()
    after_players = match.home.players + match.away.players
    after_targets = [player.target_pos for player in after_players]

    ball_runners = [
        player for player in after_players
        if not player.is_goalkeeper and distance(player.target_pos, ball_pos) < 0.2
    ]
    support_players = [
        player for player in after_players
        if not player.is_goalkeeper and distance(player.target_pos, ball_pos) >= 0.2
    ]

    assert after_targets != before_targets
    assert ball_runners
    assert len(ball_runners) < len([player for player in after_players if not player.is_goalkeeper])
    assert len(support_players) > len(ball_runners)
    assert all(player.movement_intent in ("contest", "recover_shape") for player in after_players)
