import asyncio


def test_probability_helpers_are_bounded_and_monotonic():
    from engine.probability import logistic_probability, shot_on_target_probability

    weak = logistic_probability(70, 90)
    even = logistic_probability(80, 80)
    strong = logistic_probability(90, 70)
    assert 0 < weak < even < strong < 1

    close = shot_on_target_probability(distance=10, shoot_ability=90, pressure=0)
    far = shot_on_target_probability(distance=35, shoot_ability=90, pressure=0)
    pressured = shot_on_target_probability(distance=10, shoot_ability=90, pressure=3)
    assert close > far
    assert close > pressured


def test_seeded_match_is_reproducible(core_modules, make_user, monkeypatch):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    Formation = core_modules["model.formation"].Formation
    formation_kernel = core_modules["kernel.formation"]
    Game = core_modules["engine.game"].Game
    EngineConst = __import__("engine.const", fromlist=["Const"]).Const

    user1 = make_user(40001, "seed-home", money=0)
    user2 = make_user(40002, "seed-away", money=0)
    for user in (user1, user2):
        build_full_squad(core_modules, user, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    async def run_game(seed):
        monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
        await formation_kernel.auto_update(user1)
        await formation_kernel.auto_update(user2)
        assert Formation.getFormation(user1).isValid()
        assert Formation.getFormation(user2).isValid()
        game = Game(DummyMatcher(), user1, user2, seed=seed)
        await game.start(EngineConst.MODE_SILENCE)
        game.home.getStats()
        game.away.getStats()
        return (
            game.home.point,
            game.away.point,
            game.home.shoots,
            game.away.shoots,
            game.home.passes,
            game.away.passes,
            round(game.home.xg, 4),
            round(game.away.xg, 4),
            round(game.home.adjusted_xg, 4),
            round(game.away.adjusted_xg, 4),
            round(game.home.xt, 4),
            round(game.away.xt, 4),
            [(item[0], item[1].coach, item[2].card.id) for item in game.timeline],
        )

    first = asyncio.run(run_game(12345))
    second = asyncio.run(run_game(12345))
    assert first == second


def test_print_stats_handles_zero_passes(core_modules, make_user):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    Game = core_modules["engine.game"].Game
    EngineConst = __import__("engine.const", fromlist=["Const"]).Const
    formation_kernel = core_modules["kernel.formation"]

    user1 = make_user(40101, "zero-pass-home", money=0)
    user2 = make_user(40102, "zero-pass-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    old_finish = formation_kernel.get_team.finish
    formation_kernel.get_team.finish = finish_no_raise
    try:
        asyncio.run(formation_kernel.auto_update(user1))
        asyncio.run(formation_kernel.auto_update(user2))
    finally:
        formation_kernel.get_team.finish = old_finish

    game = Game(DummyMatcher(), user1, user2, seed=1)
    game.mode = EngineConst.MODE_NORMAL
    game.home.control = 1
    game.away.control = 1
    message = asyncio.run(game.printStats())
    assert "传球成功率：0%:0%" in message
    assert "xG：" in message
    assert "xT：" in message


def test_shot_context_is_independent_from_random_shot_location(core_modules, make_user, monkeypatch):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    Game = core_modules["engine.game"].Game
    Formation = core_modules["model.formation"].Formation
    formation_kernel = core_modules["kernel.formation"]

    user1 = make_user(40201, "shot-home", money=0)
    user2 = make_user(40202, "shot-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))
    assert Formation.getFormation(user1).isValid()

    game = Game(DummyMatcher(), user1, user2, seed=1)
    shooter = game.ball_holder
    first = game.create_shot(shooter, pressure=2)
    # Generate several random shot locations; context should still be deterministic from position.
    for _ in range(5):
        shooter.shooting(first.on_target_probability, game.rng)
    second = game.create_shot(shooter, pressure=2)

    assert first.distance == second.distance
    assert first.angle == second.angle
    assert first.shoot_ability == second.shoot_ability
    assert first.raw_xg == second.raw_xg
    assert first.goal_probability == second.goal_probability
    assert first.on_target_probability == second.on_target_probability


def test_monte_carlo_smoke_and_strength_signal(core_modules):
    import scripts.simulate_matches as simulator

    even = asyncio.run(simulator.run_matches(count=20, seed=100, home_star=3, away_star=3))
    stronger = asyncio.run(simulator.run_matches(count=20, seed=100, home_star=5, away_star=1))

    assert even["matches"] == 20
    assert even["home_goals"] + even["away_goals"] >= 0
    assert stronger["home_adjusted_xg"] > stronger["away_adjusted_xg"]
    assert stronger["home_xt"] > stronger["away_xt"]
    assert even["home_possessions"] > 0
    assert even["away_possessions"] > 0
    assert even["home_xg"] + even["away_xg"] >= 0
    assert even["home_adjusted_xg"] + even["away_adjusted_xg"] >= 0
    assert even["home_xt"] + even["away_xt"] > 0
