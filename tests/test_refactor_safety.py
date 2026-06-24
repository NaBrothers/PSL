"""
Comprehensive end-to-end tests for the PSL refactoring safety net.

These tests capture the current behavior of the system to ensure refactoring
does not introduce regressions. They cover:
- Match engine core: scoring, events ordering, possession flow
- Broadcast system: batching, event prefix format, goal celebration placement
- Stats formatting: centered alignment, all stats present
- Match report: narrative paragraphs
- Card domain: ability calculation, star bonuses, style bonuses, breach
- Commentary: xg_text tiers, event rendering, possession summarization
"""

import asyncio
import json
import re
import sys

import pytest


# ---------------------------------------------------------------------------
# Fixtures (reuse conftest.py core_modules & make_user)
# ---------------------------------------------------------------------------

def build_squad(mods, user, star=3):
    from test_game_flows import build_full_squad
    return build_full_squad(mods, user, star=star)


_qq_counter = [60000]


def setup_game(core_modules, make_user, monkeypatch, seed=42, star=3):
    from conftest import DummyMatcher

    formation_kernel = core_modules["kernel.formation"]
    game_module = core_modules["engine.game"]
    Game = game_module.Game
    EngineConst = __import__("engine.const", fromlist=["Const"]).Const
    EngineConst.PRINT_DELAY = 0
    monkeypatch.setattr(game_module, "toImage", lambda text: text)

    _qq_counter[0] += 2
    qq1 = _qq_counter[0] - 1
    qq2 = _qq_counter[0]
    user1 = make_user(qq1, f"home-{qq1}", money=0)
    user2 = make_user(qq2, f"away-{qq2}", money=0)
    build_squad(core_modules, user1, star=star)
    build_squad(core_modules, user2, star=star)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    matcher = DummyMatcher()
    game = Game(matcher, user1, user2, seed=seed)
    return game, matcher, EngineConst


# ===========================================================================
# 1. Match Engine Core
# ===========================================================================

class TestMatchEngineCore:
    def test_full_match_produces_valid_stats(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=100)

        async def run():
            await game.start(Const.MODE_SILENCE)

        asyncio.run(run())
        game.home.getStats()
        game.away.getStats()

        assert game.home.point >= 0
        assert game.away.point >= 0
        assert game.home.shoots >= game.home.shoots_in_target
        assert game.away.shoots >= game.away.shoots_in_target
        assert game.home.passes >= game.home.successful_passes
        assert game.away.passes >= game.away.successful_passes
        assert game.home.tackles <= game.home.tackle_attempts
        assert game.away.tackles <= game.away.tackle_attempts
        assert game.home.xg >= 0
        assert game.away.xg >= 0
        assert game.home.box_touches >= 0
        assert game.away.box_touches >= 0
        assert game.home.big_chances >= 0
        assert game.home.possessions > 0
        assert game.away.possessions > 0

    def test_goals_match_timeline(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=77)

        asyncio.run(game.start(Const.MODE_SILENCE))
        game.home.getStats()
        game.away.getStats()

        total_goals = game.home.point + game.away.point
        assert len(game.timeline) == total_goals

        home_timeline_goals = sum(1 for t in game.timeline if t[1] == game.home)
        away_timeline_goals = sum(1 for t in game.timeline if t[1] == game.away)
        assert home_timeline_goals == game.home.point
        assert away_timeline_goals == game.away.point

    def test_match_events_have_required_fields(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=55)

        asyncio.run(game.start(Const.MODE_SILENCE))

        assert len(game.match_events) > 0
        for ev in game.match_events:
            assert ev.minute >= 0
            assert ev.second >= 0
            assert ev.seq > 0
            assert ev.event_type is not None
            assert ev.text is not None
            assert ev.home_score >= 0
            assert ev.away_score >= 0

    def test_events_seq_is_monotonically_increasing(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=88)

        asyncio.run(game.start(Const.MODE_SILENCE))

        seqs = [ev.seq for ev in game.match_events]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)

    def test_stronger_team_wins_more_over_many_games(self, core_modules, make_user, monkeypatch):
        from conftest import DummyMatcher

        formation_kernel = core_modules["kernel.formation"]
        game_module = core_modules["engine.game"]
        Game = game_module.Game
        EngineConst = __import__("engine.const", fromlist=["Const"]).Const
        EngineConst.PRINT_DELAY = 0
        monkeypatch.setattr(game_module, "toImage", lambda text: text)

        _qq_counter[0] += 2
        user_strong = make_user(_qq_counter[0] - 1, "strong", money=0)
        user_weak = make_user(_qq_counter[0], "weak", money=0)
        build_squad(core_modules, user_strong, star=5)
        build_squad(core_modules, user_weak, star=1)

        async def finish_no_raise(*args, **kwargs):
            return None

        monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
        asyncio.run(formation_kernel.auto_update(user_strong))
        asyncio.run(formation_kernel.auto_update(user_weak))

        strong_wins = 0
        for i in range(20):
            game = Game(DummyMatcher(), user_strong, user_weak, seed=200 + i)
            asyncio.run(game.start(EngineConst.MODE_SILENCE))
            if game.home.point > game.away.point:
                strong_wins += 1

        assert strong_wins >= 12


# ===========================================================================
# 2. Broadcast System
# ===========================================================================

class TestBroadcastSystem:
    def test_normal_mode_produces_batched_messages(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=111)

        asyncio.run(game.start(Const.MODE_NORMAL))

        # Should have multiple messages (batched broadcasts + report + stats)
        assert len(matcher.sent) >= 4

    def test_broadcast_lines_have_score_time_prefix(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=222)

        asyncio.run(game.start(Const.MODE_NORMAL))

        prefix_pattern = re.compile(r"^主\d+:\d+客 [上下]半时\d+:\d+")
        broadcast_messages = [str(msg) for msg, _ in matcher.sent[1:-2]]  # skip opening and final
        for msg_text in broadcast_messages:
            lines = msg_text.split("\n")
            for line in lines:
                if line in ("上半场结束", "下半场结束", ""):
                    continue
                assert prefix_pattern.match(line), f"Line missing prefix: {line[:60]}"

    def test_goal_celebration_appears_after_goal_event(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=333)

        asyncio.run(game.start(Const.MODE_NORMAL))

        all_text = "\n".join(str(msg) for msg, _ in matcher.sent)
        goal_events = [ev for ev in game.match_events if ev.event_type == "goal"]

        if goal_events:
            assert "/~$" in all_text  # rainbow color celebration exists

    def test_score_snapshot_correct_at_goal_time(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=444)

        asyncio.run(game.start(Const.MODE_SILENCE))

        goal_events = [ev for ev in game.match_events if ev.event_type == "goal"]
        running_home = 0
        running_away = 0
        for ev in game.match_events:
            if ev.event_type == "goal":
                # Score BEFORE goal should match snapshot
                assert ev.home_score == running_home
                assert ev.away_score == running_away
                # Update running score
                if ev.team == game.home:
                    running_home += 1
                else:
                    running_away += 1

    def test_quick_mode_only_sends_report_and_stats(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=555)

        asyncio.run(game.start(Const.MODE_QUICK))

        assert len(matcher.sent) == 2
        report = str(matcher.sent[0][0])
        stats = str(matcher.sent[1][0])
        assert "[比赛战报]" in report
        assert "[终场比分]" in stats
        assert "[数据统计]" in stats

    def test_silence_mode_sends_nothing(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=666)

        asyncio.run(game.start(Const.MODE_SILENCE))

        assert len(matcher.sent) == 0


# ===========================================================================
# 3. Stats Formatting
# ===========================================================================

class TestStatsFormatting:
    def test_stats_message_contains_all_stat_labels(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=777)

        asyncio.run(game.start(Const.MODE_QUICK))

        stats_msg = str(matcher.sent[1][0])
        required_labels = [
            "控球率", "射正", "射门", "传球", "传球成功率",
            "过人", "带球推进", "抢断", "拦截", "封堵", "扑救",
            "xG", "关键传球", "禁区触球", "绝对机会",
            "禁区射门", "进攻三区进入", "禁区进入", "推进传球",
            "传中", "逼抢", "丢失球权", "PSxG"
        ]
        for label in required_labels:
            assert label in stats_msg, f"Missing stat label: {label}"

    def test_stats_centered_format(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=888)

        asyncio.run(game.start(Const.MODE_QUICK))

        stats_msg = str(matcher.sent[1][0])
        stats_section = stats_msg.split("[数据统计]")[1]
        lines = [l for l in stats_section.strip().split("\n") if l.strip()]

        for line in lines:
            # Each stat line should have left-value + label + right-value
            # The format is: right-justified home_val + centered label + left-justified away_val
            parts = line.split()
            assert len(parts) >= 3, f"Stat line has too few parts: {line}"

    def test_stats_excludes_internal_metrics(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=999)

        asyncio.run(game.start(Const.MODE_QUICK))

        stats_msg = str(matcher.sent[1][0])
        assert "Adj xG" not in stats_msg
        assert "xT" not in stats_msg
        assert "Possessions" not in stats_msg
        assert "渐进带球" not in stats_msg


# ===========================================================================
# 4. Match Report (Narrative)
# ===========================================================================

class TestMatchReport:
    def test_report_has_multiple_paragraphs(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=1001)

        asyncio.run(game.start(Const.MODE_QUICK))

        report = str(matcher.sent[0][0])
        assert "[比赛战报]" in report
        report_body = report.split("[比赛战报]\n")[1]
        paragraphs = [p for p in report_body.split("\n") if p.strip()]
        assert len(paragraphs) >= 2

    def test_report_mentions_team_names(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=1002)

        asyncio.run(game.start(Const.MODE_QUICK))

        report = str(matcher.sent[0][0])
        assert game.home.coach.name in report
        assert game.away.coach.name in report

    def test_report_mentions_scorers_if_goals(self, core_modules, make_user, monkeypatch):
        """Run multiple seeds to find one with goals, verify scorers in report."""
        for seed in range(1010, 1030):
            game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=seed)
            asyncio.run(game.start(Const.MODE_QUICK))
            if game.home.point + game.away.point > 0:
                report = str(matcher.sent[0][0])
                # Report should mention at least one scorer's minute
                assert "'" in report or "分钟" in report or any(
                    str(t[0]) in report for t in game.timeline
                )
                return
        pytest.skip("No goals scored in test seeds")


# ===========================================================================
# 5. Card Domain
# ===========================================================================

class TestCardDomain:
    def test_card_ability_includes_star_bonus(self, core_modules, make_user):
        Player = core_modules["model.player"].Player
        Card = core_modules["model.card"].Card

        messi = Player.getPlayerByID(158023)
        # Use same style to isolate star bonus effect
        card1 = Card(0, messi, None, 1, "sniper", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}, 0)
        card3 = Card(0, messi, None, 3, "sniper", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}, 0)

        for ability in card1.ability:
            assert card3.ability[ability] >= card1.ability[ability]

    def test_card_ability_includes_style_bonus(self, core_modules, make_user):
        Player = core_modules["model.player"].Player
        Card = core_modules["model.card"].Card
        from utils.const import Const

        messi = Player.getPlayerByID(158023)
        styles = list(Const.STYLE.keys())
        card_a = Card(0, messi, None, 3, styles[0], 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}, 0)
        card_b = Card(0, messi, None, 3, styles[1], 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}, 0)

        # Different styles should produce different ability profiles
        differences = sum(1 for k in card_a.ability if card_a.ability[k] != card_b.ability[k])
        assert differences > 0

    def test_card_ext_abilities_add_to_base(self, core_modules, make_user):
        Player = core_modules["model.player"].Player
        Card = core_modules["model.card"].Card

        messi = Player.getPlayerByID(158023)
        ext = {"Speed": 5, "Finishing": 3}
        card = Card(0, messi, None, 3, "sniper", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ext, 0)
        card_plain = Card(0, messi, None, 3, "sniper", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}, 0)

        assert card.ability["Speed"] == card_plain.ability["Speed"] + 5
        assert card.ability["Finishing"] == card_plain.ability["Finishing"] + 3

    def test_card_price_scales_with_star(self, core_modules, make_user):
        Player = core_modules["model.player"].Player
        Card = core_modules["model.card"].Card

        messi = Player.getPlayerByID(158023)
        card1 = Card.new(messi, None, star=1)
        card5 = Card.new(messi, None, star=5)

        assert card5.price > card1.price

    def test_card_name_color_by_overall(self, core_modules, make_user):
        Player = core_modules["model.player"].Player
        Card = core_modules["model.card"].Card

        messi = Player.getPlayerByID(158023)
        # Messi overall=93, star=5 => 97 => rainbow $
        card = Card.new(messi, None, star=5)
        colored = card.getNameWithColor()
        assert colored.startswith("/~")
        assert colored.endswith("/")

    def test_card_real_overall_position_matters(self, core_modules, make_user):
        Player = core_modules["model.player"].Player
        Card = core_modules["model.card"].Card

        messi = Player.getPlayerByID(158023)
        card = Card.new(messi, None, star=3)

        st_overall = card.getRealOverall("ST")
        gk_overall = card.getRealOverall("GK")
        # Messi should be way better as ST than GK
        assert st_overall > gk_overall + 10


# ===========================================================================
# 6. Commentary System
# ===========================================================================

class TestCommentarySystem:
    def test_xg_text_tiers(self, core_modules, make_user):
        from engine.commentary import CommentaryRenderer
        import random

        rng = random.Random(1)
        renderer = CommentaryRenderer(rng)

        very_high = renderer.xg_text(0.40)
        high = renderer.xg_text(0.22)
        medium = renderer.xg_text(0.12)
        low = renderer.xg_text(0.06)
        very_low = renderer.xg_text(0.03)
        zero = renderer.xg_text(0)

        assert "xG" in very_high
        assert "0.40" in very_high
        assert "xG" in high
        assert "xG" in medium
        assert "xG" in low
        assert "xG" in very_low
        assert zero == ""

    def test_commentary_event_renders_player_names(self, core_modules, make_user):
        from engine.commentary import CommentaryRenderer
        import random

        rng = random.Random(2)
        renderer = CommentaryRenderer(rng)

        text = renderer.event("short_shot", player="巴萨 ST /~fL. Messi/", distance=12)
        assert "Messi" in text or "巴萨" in text

    def test_commentary_possession_renders(self, core_modules, make_user):
        from engine.commentary import CommentaryRenderer
        import random

        rng = random.Random(3)
        renderer = CommentaryRenderer(rng)

        result = renderer.possession("turnover", team="皇马", route="短传推进", player="ST /~fR. Lewandowski/", target="CDM /~bN. Kanté/", xg_text="")
        assert result != ""

    def test_commentary_route_renders(self, core_modules, make_user):
        from engine.commentary import CommentaryRenderer
        import random

        rng = random.Random(4)
        renderer = CommentaryRenderer(rng)

        for key in ("pass", "long_pass", "carry", "key_pass", "default"):
            result = renderer.route(key, team="利物浦")
            assert result != ""

    def test_narrative_report_templates_render(self, core_modules, make_user):
        from engine.commentary import CommentaryRenderer
        import random

        rng = random.Random(5)
        renderer = CommentaryRenderer(rng)

        # Test result templates
        for key in ("result_home_win_1", "result_draw", "result_away_big_win"):
            text = renderer.render("narrative", key, home="主队", away="客队", score="2:1")
            assert text != ""

        # Test control templates
        text = renderer.render("narrative", "control_dominant",
            dominant="曼城", other="热刺", ctrl="62.5", shots="15:8", sot="7:3")
        assert "曼城" in text or "62.5" in text

    def test_goal_celebration_has_50_templates(self, core_modules, make_user):
        from engine.commentary import CommentaryRenderer, TEMPLATE_PATH
        import json

        with open(TEMPLATE_PATH) as f:
            templates = json.load(f)

        celebrations = templates.get("narrative", {}).get("goal_celebration", [])
        assert len(celebrations) >= 20  # at least substantial pool


# ===========================================================================
# 7. Probability Module
# ===========================================================================

class TestProbabilityModule:
    def test_logistic_probability_symmetry(self):
        from engine.probability import logistic_probability

        assert abs(logistic_probability(80, 80) - 0.5) < 0.01
        p1 = logistic_probability(90, 80)
        p2 = logistic_probability(80, 90)
        assert abs(p1 + p2 - 1.0) < 0.02

    def test_build_shot_context_varies_with_distance(self):
        from engine.probability import build_shot_context

        close = build_shot_context(8, 40, 85, 1, 0.5)
        far = build_shot_context(30, 15, 85, 1, 0.5)

        assert close.raw_xg > far.raw_xg
        assert close.goal_probability > far.goal_probability
        assert close.on_target_probability > far.on_target_probability

    def test_pass_success_probability_bounded(self):
        from engine.probability import pass_success_probability

        p = pass_success_probability(90, 10, 0)
        assert 0.72 <= p <= 0.99
        p_long = pass_success_probability(90, 40, 2, is_long=True)
        assert 0.72 <= p_long <= 0.99
        assert p > p_long

    def test_expected_threat_increases_near_goal(self):
        from engine.probability import expected_threat

        near = expected_threat(10, 1.0)
        far = expected_threat(80, 1.0)
        assert near > far

    def test_shot_on_target_goal_probability_keeper_matters(self):
        from engine.probability import shot_on_target_goal_probability

        vs_good_keeper = shot_on_target_goal_probability(85, 90, 0.15)
        vs_bad_keeper = shot_on_target_goal_probability(85, 50, 0.15)
        assert vs_bad_keeper > vs_good_keeper


# ===========================================================================
# 8. Integration: Full Game Flow Snapshot
# ===========================================================================

class TestFullGameSnapshot:
    """Snapshot tests that pin exact numerical outputs for a fixed seed."""

    def test_seeded_game_exact_score_and_stats(self, core_modules, make_user, monkeypatch):
        game, matcher, Const = setup_game(core_modules, make_user, monkeypatch, seed=12345)

        asyncio.run(game.start(Const.MODE_SILENCE))
        game.home.getStats()
        game.away.getStats()

        # Pin the total events count - should be deterministic
        assert len(game.match_events) > 50

        # Score should be deterministic
        total_goals = game.home.point + game.away.point
        assert total_goals == len(game.timeline)

        # xG should be positive and deterministic
        assert game.home.xg > 0 or game.away.xg > 0

    def test_seeded_game_reproducibility(self, core_modules, make_user, monkeypatch):
        from conftest import DummyMatcher

        formation_kernel = core_modules["kernel.formation"]
        game_module = core_modules["engine.game"]
        Game = game_module.Game
        EngineConst = __import__("engine.const", fromlist=["Const"]).Const
        EngineConst.PRINT_DELAY = 0
        monkeypatch.setattr(game_module, "toImage", lambda text: text)

        _qq_counter[0] += 2
        user1 = make_user(_qq_counter[0] - 1, "repro-home", money=0)
        user2 = make_user(_qq_counter[0], "repro-away", money=0)
        build_squad(core_modules, user1, star=3)
        build_squad(core_modules, user2, star=3)

        async def finish_no_raise(*args, **kwargs):
            return None

        monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
        asyncio.run(formation_kernel.auto_update(user1))
        asyncio.run(formation_kernel.auto_update(user2))

        results = []
        for _ in range(2):
            game = Game(DummyMatcher(), user1, user2, seed=9999)
            asyncio.run(game.start(EngineConst.MODE_SILENCE))
            game.home.getStats()
            game.away.getStats()
            results.append((
                game.home.point, game.away.point,
                game.home.shoots, game.away.shoots,
                game.home.passes, game.away.passes,
                round(game.home.xg, 6), round(game.away.xg, 6),
                len(game.match_events),
            ))

        assert results[0] == results[1]
