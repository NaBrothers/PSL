"""Tests for the presentation layer - formatting MatchResult into display text."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from engine.types import MatchResult, TeamStats, GoalRecord, MatchEvent


def make_result():
    home = TeamStats(
        name="皇马", point=2, control=2800, shoots=12, shoots_in_target=6,
        goals=2, passes=350, successful_passes=310, dribbles=8, carries=15,
        tackles=14, interceptions=10, blocks=3, saves=3, xg=1.85,
        adjusted_xg=1.6, xt=5.2, key_passes=6, box_touches=22, big_chances=3,
        possessions=95, goals_detailed=[("ST /~fR. Lewandowski/", [12, 67])],
    )
    away = TeamStats(
        name="巴萨", point=1, control=2400, shoots=9, shoots_in_target=4,
        goals=1, passes=280, successful_passes=240, dribbles=6, carries=12,
        tackles=11, interceptions=8, blocks=2, saves=4, xg=1.2,
        adjusted_xg=1.1, xt=4.0, key_passes=4, box_touches=18, big_chances=2,
        possessions=85,
        goals_detailed=[("CAM /~fL. Messi/", [35])],
    )
    timeline = [
        GoalRecord(minute=12, team_side="home", scorer_name="ST /~fR. Lewandowski/", assister_name="CAM /~bK. De Bruyne/"),
        GoalRecord(minute=35, team_side="away", scorer_name="CAM /~fL. Messi/", assister_name=None),
        GoalRecord(minute=67, team_side="home", scorer_name="ST /~fR. Lewandowski/", assister_name="LW /~rNeymar/"),
    ]
    return MatchResult(home_stats=home, away_stats=away, timeline=timeline, events=[])


class TestStatsFormatting:
    def test_contains_all_labels(self):
        from presentation.stats import format_stats
        result = make_result()
        text = format_stats(result)
        for label in ["控球率", "射正", "射门", "传球", "传球成功率", "过人",
                      "带球推进", "抢断", "拦截", "封堵", "扑救", "xG",
                      "关键传球", "禁区触球", "绝对机会", "禁区射门",
                      "进攻三区进入", "禁区进入", "推进传球", "传中",
                      "角球", "逼抢", "丢失球权", "PSxG"]:
            assert label in text

    def test_contains_score(self):
        from presentation.stats import format_stats
        result = make_result()
        text = format_stats(result)
        assert "2:1" in text
        assert "皇马" in text
        assert "巴萨" in text

    def test_contains_goal_events(self):
        from presentation.stats import format_stats
        result = make_result()
        text = format_stats(result)
        assert "⚽" in text
        assert "12'" in text
        assert "35'" in text

    def test_excludes_internal_metrics(self):
        from presentation.stats import format_stats
        result = make_result()
        text = format_stats(result)
        assert "Adj xG" not in text
        assert "xT" not in text
        assert "Possessions" not in text

    def test_centered_alignment(self):
        from presentation.stats import format_stats
        result = make_result()
        text = format_stats(result)
        stats_section = text.split("[数据统计]\n")[1]
        lines = [l for l in stats_section.strip().split("\n") if l.strip()]
        for line in lines:
            assert len(line) > 10


class TestReportFormatting:
    def test_report_has_content(self):
        import random
        from presentation.report import build_report
        from engine.commentary import CommentaryRenderer
        rng = random.Random(42)
        commentary = CommentaryRenderer(rng)
        result = make_result()
        # Add some goal events to the result
        result.events = [
            MatchEvent(12, 30, 1, "goal", "进球", 0, 0, 5, "home", "ST /~fR. Lewandowski/", 0.15, "CAM /~bK. De Bruyne/"),
            MatchEvent(35, 15, 2, "goal", "进球", 1, 0, 5, "away", "CAM /~fL. Messi/", 0.12, ""),
        ]
        report = build_report(result, commentary)
        assert len(report) > 50
        assert "皇马" in report or "巴萨" in report

    def test_report_multiple_paragraphs(self):
        import random
        from presentation.report import build_report
        from engine.commentary import CommentaryRenderer
        rng = random.Random(42)
        commentary = CommentaryRenderer(rng)
        result = make_result()
        result.events = [
            MatchEvent(12, 30, 1, "goal", "进球", 0, 0, 5, "home", "Lewandowski", 0.15, "De Bruyne"),
        ]
        report = build_report(result, commentary)
        paragraphs = [p for p in report.split("\n") if p.strip()]
        assert len(paragraphs) >= 2
