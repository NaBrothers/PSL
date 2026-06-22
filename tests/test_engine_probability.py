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


def test_monte_carlo_smoke_and_strength_signal(core_modules):
    import scripts.simulate_matches as simulator

    even = asyncio.run(simulator.run_matches(count=8, seed=100, home_star=3, away_star=3))
    stronger = asyncio.run(simulator.run_matches(count=8, seed=100, home_star=5, away_star=1))

    assert even["matches"] == 8
    assert even["home_goals"] + even["away_goals"] >= 0
    assert stronger["home_wins"] >= stronger["away_wins"]
    assert stronger["home_goals"] >= stronger["away_goals"]
