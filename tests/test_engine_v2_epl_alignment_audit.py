from scripts.audit_engine_v2_epl_alignment import aggregate_reports
from scripts.diagnose_engine_v2_match_pace import PREMIER_LEAGUE_2024_25_BENCHMARK


def test_alignment_audit_weights_counts_instead_of_averaging_rates() -> None:
    def report(matches: int, attempted: int, completed: int) -> dict:
        return {
            "match_count": matches,
            "aggregate": {
                "premier_league_alignment": {
                    "metrics": {"fouls": {"current": 22.0}},
                    "engine_scope_diagnostics": {
                        "comparable_non_cross_passes_per_match": attempted / matches,
                        "comparable_non_cross_completed_passes_per_match": completed / matches,
                        "corner_restarts_per_match": 10.0,
                        "penalty_restarts_per_match": 0.2,
                        "penalty_goals_per_match": 0.16,
                    },
                },
                "metric_integrity": {
                    "status": "ok",
                    "core_totals": {"shots": 20, "shots_on_target": 8, "stat_goals": 2},
                },
                "pass_causality": {
                    "provider_long_completion_contact": {
                        "with_opponent_contact": 1,
                        "without_opponent_contact": 4,
                        "non_goal_kick_with_opponent_contact": 1,
                    },
                    "breakdown": {
                        "by_provider_pass_scope_length": {
                            "short": {"attempted": attempted - 10, "completed": completed - 5},
                            "long": {"attempted": 10, "completed": 5},
                        },
                        "by_provider_pass_scope_distance": {
                            "0-10m": {"attempted": attempted, "completed": completed},
                        },
                        "by_restart_origin": {
                            "open_play": {"attempted": attempted - 3, "completed": completed - 2},
                            "corner": {"attempted": 3, "completed": 2},
                        },
                        "by_provider_pass_scope_restart_origin": {
                            "open_play": {"attempted": attempted, "completed": completed},
                        },
                        "by_restart_origin_and_length": {
                            "goal_kick:long": {"attempted": 3, "completed": 2},
                        },
                    }
                },
                "match_clock": {
                    "average_match_seconds": 5940.0,
                    "average_active_play_seconds": 3426.0,
                },
                "shot_outcomes": {"last_line_blocks": {"total": 1}},
            },
        }

    audit = aggregate_reports([report(1, 100, 50), report(2, 400, 360)])

    assert audit["match_count"] == 3
    assert audit["current"]["pass_success_rate"] == 82.0
    assert audit["current"]["passes_per_active_play_minute"] == round(
        500 / (3 * 3426 / 60), 6
    )
    assert audit["current"]["long_ball_share"] == 4.0
    assert audit["current"]["long_ball_accuracy"] == 20.0
    assert audit["mechanism_diagnostics"]["long_ball_accuracy_scope"] == {
        "total_long_balls": 20.0,
        "accurate_long_balls": 4.0,
        "goal_kick_long_completions_excluded_from_accurate": 4.0,
        "opponent_contact_long_completions_excluded_from_accurate": 2.0,
        "definition": (
            "Opta total_long_balls counts passes longer than 35 yards; "
            "accurate_long_balls uses successful passes over the same distance but "
            "excludes crosses, throw-ins, keeper throws, goal kicks, and any "
            "terminal opponent touch"
        ),
    }
    assert audit["targets"]["passes_per_active_play_minute"] == 15.646281
    totals = PREMIER_LEAGUE_2024_25_BENCHMARK["totals"]
    assert audit["targets"]["passes"] == round(
        totals["passes"] / 380 * (90 * 60 / 5984), 6
    )
    assert audit["targets"]["passes_per_active_play_minute"] == round(
        audit["targets"]["passes"] / audit["targets"]["ball_in_play_minutes"],
        6,
    )
    assert audit["targets"]["long_ball_share"] == round(
        totals["long_balls"] / totals["passes"] * 100, 6
    )
    assert audit["integrity"]["status"] == "ok"
    assert audit["mechanism_diagnostics"]["pass_distance_bands"]["0-10m"][
        "attempted"
    ] == 500.0
    assert audit["mechanism_diagnostics"]["pass_restart_origins"]["corner"][
        "attempted"
    ] == 6.0
    assert audit["mechanism_diagnostics"][
        "provider_scope_pass_restart_origins"
    ]["open_play"]["attempted"] == 500.0
    assert audit["mechanism_diagnostics"]["pass_distance_scope_integrity"][
        "status"
    ] == "ok"
    clock = audit["mechanism_diagnostics"]["match_clock_comparability"]
    assert clock["engine_average_match_minutes"] == 99.0
    assert clock["engine_active_play_share"] == round(3426 / 5940, 6)
    assert clock["epl_average_match_minutes"] == round(5984 / 60, 6)
    assert "normalized to a fixed 90" in clock["comparison_caveat"]
    assert audit["completion"]["achieved"] is False


def test_alignment_audit_rejects_distance_bands_outside_provider_scope() -> None:
    report = {
        "match_count": 1,
        "aggregate": {
            "premier_league_alignment": {
                "metrics": {"fouls": {"current": 20.0}},
                "engine_scope_diagnostics": {
                    "comparable_non_cross_passes_per_match": 100.0,
                    "comparable_non_cross_completed_passes_per_match": 80.0,
                    "corner_restarts_per_match": 10.0,
                    "penalty_restarts_per_match": 0.2,
                    "penalty_goals_per_match": 0.16,
                },
            },
            "metric_integrity": {
                "status": "ok",
                "core_totals": {"shots": 20, "shots_on_target": 8, "stat_goals": 2},
            },
            "pass_causality": {
                "breakdown": {
                    "by_provider_pass_scope_length": {
                        "short": {"attempted": 90, "completed": 75},
                        "long": {"attempted": 10, "completed": 5},
                    },
                    "by_provider_pass_scope_distance": {
                        "0-10m": {"attempted": 101, "completed": 80},
                    },
                },
            },
            "match_clock": {
                "average_match_seconds": 5400.0,
                "average_active_play_seconds": 3100.0,
            },
            "shot_outcomes": {"last_line_blocks": {"total": 0}},
        },
    }

    audit = aggregate_reports([report])

    assert audit["integrity"]["status"] == "error"
    assert audit["mechanism_diagnostics"]["pass_distance_scope_integrity"][
        "status"
    ] == "error"


def test_alignment_audit_accepts_per_match_display_rounding() -> None:
    report = {
        "match_count": 30,
        "runtime_config": {"tick_duration": 1.0},
        "aggregate": {
            "premier_league_alignment": {
                "metrics": {"fouls": {"current": 20.0}},
                "engine_scope_diagnostics": {
                    "comparable_non_cross_passes_per_match": 724.733,
                    "comparable_non_cross_completed_passes_per_match": 599.733,
                    "corner_restarts_per_match": 10.0,
                    "penalty_restarts_per_match": 0.2,
                    "penalty_goals_per_match": 0.16,
                },
            },
            "metric_integrity": {
                "status": "ok",
                "core_totals": {"shots": 600, "shots_on_target": 240, "stat_goals": 80},
            },
            "pass_causality": {
                "breakdown": {
                    "by_provider_pass_scope_length": {
                        "short": {"attempted": 19491, "completed": 16552},
                        "long": {"attempted": 2251, "completed": 1440},
                    },
                    "by_provider_pass_scope_distance": {
                        "0-10m": {"attempted": 1283, "completed": 1061},
                        "10-20m": {"attempted": 8714, "completed": 7590},
                        "20-30m": {"attempted": 8488, "completed": 7122},
                        "30m+": {"attempted": 3257, "completed": 2219},
                    },
                },
            },
            "match_clock": {
                "average_match_seconds": 5400.0,
                "average_active_play_seconds": 3100.0,
            },
            "shot_outcomes": {"last_line_blocks": {"total": 0}},
        },
    }

    audit = aggregate_reports([report])

    scope = audit["mechanism_diagnostics"]["pass_distance_scope_integrity"]
    assert scope["status"] == "ok"
    assert scope["rounding_tolerance"] == 0.015
