from __future__ import annotations

from scripts.diagnose_engine_v2_match_pace import (
    _all_team_checks_ok,
    _aggregate_shot_outcomes,
    _body_challenge_summary,
    _carry_contact_summary,
    _direct_shot_creations,
    _distribution_values,
    _held_body_separation_summary,
    _metric_integrity_summary,
    _pass_causality_summary,
    _premier_league_alignment,
    _quantile,
    _sequence_summary,
    _shot_family_summary,
    _shot_outcome_summary,
    _shot_release_summary,
    _weighted_team_pass_success_rate,
    _weighted_team_take_on_success_rate,
)
from scripts.benchmark_engine_v2 import (
    blocked_shot_count,
    run_assertions,
    shot_accuracy_metrics,
)
from scripts.validate_engine_v2_real_squads import _weighted_pass_success_rate
from scripts.validate_engine_v2_real_squads import _long_shot_diagnostics
from scripts.validate_engine_v2_real_squads import _scan_match


def _event(
    event_type: str,
    outcome: str,
    team: str = "home",
    tags: list[str] | None = None,
) -> dict:
    return {
        "event_type": event_type,
        "outcome": outcome,
        "team_side": team,
        "tags": tags or ["short", "feet", "distance_0_10"],
        "origin": [20.0, 30.0],
        "target": [25.0, 30.0],
    }


def test_take_on_success_rate_is_sample_weighted() -> None:
    summaries = [
        {
            "home_stats": {"take_ons": 1, "successful_take_ons": 1},
            "away_stats": {"take_ons": 4, "successful_take_ons": 1},
        },
        {
            "home_stats": {"take_ons": 9, "successful_take_ons": 0},
            "away_stats": {"take_ons": 6, "successful_take_ons": 2},
        },
    ]

    assert _weighted_team_take_on_success_rate(summaries, "home") == 10.0
    assert _weighted_team_take_on_success_rate(summaries, "away") == 30.0


def test_body_challenge_continuation_is_not_a_completed_take_on() -> None:
    summary = _body_challenge_summary(
        [
            _event(
                "duel",
                "attempted",
                tags=["take_on_attempt", "body_challenge"],
            ),
            _event("duel", "retained", tags=["take_on", "body_challenge"]),
            _event(
                "duel",
                "won",
                team="away",
                tags=["possession_won", "pressure_turnover", "body_challenge"],
            ),
            _event("duel", "loose", tags=["second_ball", "body_challenge"]),
            _event(
                "duel",
                "won",
                tags=["take_on", "take_on_completed", "spatially_separated"],
            ),
        ]
    )

    assert summary["terminal"] == 3
    assert summary["attacker_continues"] == 1
    assert summary["defender_wins"] == 1
    assert summary["loose"] == 1
    assert summary["attacker_continuation_rate"] == 0.3333
    assert summary["by_context"]["take_on"] == {
        "terminal": 1,
        "attacker_continues": 1,
        "defender_wins": 0,
        "loose": 0,
        "attacker_continuation_rate": 1.0,
        "outcomes": {"attempted": 1, "retained": 1},
    }
    assert summary["by_context"]["unknown"]["terminal"] == 2


def test_carry_contact_summary_includes_tackles_and_body_challenges() -> None:
    summary = _carry_contact_summary(
        [
            _event("duel", "attempted", tags=["take_on_attempt", "body_challenge"]),
            _event("duel", "retained", tags=["take_on", "body_challenge"]),
            _event(
                "tackle",
                "won",
                team="away",
                tags=["possession_won", "take_on", "blocked"],
            ),
            _event(
                "duel",
                "loose",
                tags=["second_ball", "ball_protection", "body_challenge"],
            ),
            _event(
                "tackle",
                "won",
                team="away",
                tags=["possession_won", "pass_release", "blocked"],
            ),
        ]
    )

    assert summary["contacts"] == 3
    assert summary["attacker_continues"] == 1
    assert summary["defender_wins"] == 1
    assert summary["loose"] == 1
    assert summary["attacker_continuation_rate"] == 0.3333
    assert summary["by_context"]["take_on"]["contacts"] == 2
    assert summary["by_context"]["ball_protection"]["contacts"] == 1
    assert summary["by_defender_action"]["body_challenge"]["contacts"] == 2
    assert summary["by_defender_action"]["tackle"]["contacts"] == 1


def test_held_body_separation_allows_quantized_nominal_boundary() -> None:
    summary = _held_body_separation_summary(
        [
            {
                "type": "frame",
                "t": 10.0,
                "half": 1,
                "ball_team": "home",
                "ball_holder": 0,
                "home": [[10.0, 20.0]],
                "away": [[10.8, 20.1], [30.0, 40.0]],
            }
        ]
    )

    assert summary["held_frames"] == 1
    assert summary["minimum_separation_m"] == 0.8062
    assert summary["below_body_separation_frames"] == 1
    assert summary["deep_overlap_frames"] == 0
    assert summary["deep_overlap_samples"] == []


def test_held_body_separation_reports_deep_overlap_with_actual_defender_index() -> None:
    summary = _held_body_separation_summary(
        [
            {
                "type": "frame",
                "t": 12.0,
                "half": 1,
                "ball_team": "away",
                "ball_holder": 0,
                "home": [[30.0, 40.0], [50.3, 20.2]],
                "away": [[50.0, 20.0]],
            }
        ]
    )

    assert summary["held_frames"] == 1
    assert summary["deep_overlap_frames"] == 1
    assert summary["deep_overlap_samples"] == [
        {
            "t": 12.0,
            "half": 1,
            "team": "away",
            "holder": 0,
            "defender": 1,
            "distance_m": 0.3606,
        }
    ]


def test_held_body_separation_excludes_terminal_flight_attributed_to_shooter() -> None:
    summary = _held_body_separation_summary(
        [
            {
                "type": "frame",
                "t": 12.5,
                "half": 1,
                "ball_team": "home",
                "ball_holder": 0,
                "ball_flight": {
                    "type": "shot",
                    "complete": True,
                    "end_reason": "goal",
                },
                "home": [[50.0, 20.0]],
                "away": [[50.1, 20.1]],
            }
        ]
    )

    assert summary["held_frames"] == 0
    assert summary["minimum_separation_m"] is None
    assert summary["deep_overlap_frames"] == 0


def test_held_body_separation_reports_crossing_between_safe_endpoints() -> None:
    summary = _held_body_separation_summary(
        [
            {
                "type": "frame",
                "t": 10.0,
                "half": 1,
                "ball_team": "home",
                "ball_holder": 0,
                "home": [[10.0, 20.0]],
                "away": [[12.0, 20.0]],
            },
            {
                "type": "frame",
                "t": 12.0,
                "half": 1,
                "ball_team": "home",
                "ball_holder": 0,
                "home": [[12.0, 20.0]],
                "away": [[10.0, 20.0]],
            },
        ]
    )

    assert summary["deep_overlap_frames"] == 0
    assert summary["continuous_held_intervals"] == 1
    assert summary["minimum_path_separation_m"] == 0.0
    assert summary["path_below_body_separation_intervals"] == 1
    assert summary["path_deep_overlap_intervals"] == 1
    assert summary["path_deep_overlap_samples"] == [
        {
            "start_t": 10.0,
            "end_t": 12.0,
            "half": 1,
            "team": "home",
            "holder": 0,
            "defender": 0,
            "minimum_distance_m": 0.0,
        }
    ]


def test_pass_accounting_includes_every_released_failure_terminal() -> None:
    events = [
        _event("pass", "completed"),
        _event("pass", "first_touch_error"),
        _event("pass", "loose"),
        _event("pass", "out_of_play"),
        _event("pass", "period_end"),
        _event(
            "interception",
            "won",
            team="away",
            tags=["short", "feet", "distance_0_10", "pass_cut_out"],
        ),
        _event("offside", "offside", tags=["short", "feet", "pass_release"]),
        _event("carry", "loose", tags=["technical_error", "second_ball"]),
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 7, "passes_completed": 1},
        {"passes": 0, "passes_completed": 0},
    )

    assert summary["attempted"]["total"] == 7
    assert summary["completed"] == 1
    assert summary["attributed_outcomes"] == {
        "completed": 1,
        "first_touch_error": 1,
        "intercepted": 1,
        "loose": 1,
        "offside": 1,
        "out_of_play": 1,
        "period_end": 1,
    }
    assert summary["outcome_classes"]["total"] == {
        "completed": 1,
        "offside": 1,
        "opposing_control": 1,
        "out_of_play": 1,
        "period_end_censored": 1,
        "technical_failure": 1,
        "unresolved_control": 1,
    }
    assert summary["outcome_classes"]["by_team"] == {
        "home": {
            "completed": 1,
            "offside": 1,
            "opposing_control": 1,
            "out_of_play": 1,
            "period_end_censored": 1,
            "technical_failure": 1,
            "unresolved_control": 1,
        },
        "away": {},
    }
    assert summary["outcome_classes"]["closure"] == {
        "classified": 7,
        "attempted": 7,
        "delta": 0,
    }
    assert summary["terminal_control_classes"]["total"] == {
        "completed": 1,
        "offside": 1,
        "opposing_control": 1,
        "out_of_play": 1,
        "period_end_censored": 1,
        "unresolved_control": 2,
    }
    assert "unattributed_terminal" not in summary["failure_causes"]
    for buckets in summary["breakdown"].values():
        assert sum(bucket["attempted"] for bucket in buckets.values()) == 7
        assert sum(bucket["completed"] for bucket in buckets.values()) == 1


def test_pass_failure_classes_separate_delivery_errors_from_control_outcomes() -> None:
    events = [
        _event("pass", "completed", tags=["short", "feet", "delivery_error"]),
        _event("pass", "loose", tags=["short", "feet", "delivery_error"]),
        _event("pass", "loose", tags=["short", "feet", "delivery_clean"]),
        _event(
            "interception",
            "won",
            team="away",
            tags=["short", "feet", "delivery_error", "pass_cut_out"],
        ),
        _event(
            "interception",
            "won",
            team="away",
            tags=["short", "feet", "delivery_clean", "pass_cut_out"],
        ),
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 5, "passes_completed": 1},
        {"passes": 0, "passes_completed": 0},
    )

    assert summary["outcome_classes"]["total"] == {
        "completed": 1,
        "opposing_control": 1,
        "technical_failure": 2,
        "unresolved_control": 1,
    }
    assert summary["terminal_control_classes"]["total"] == {
        "completed": 1,
        "opposing_control": 2,
        "unresolved_control": 2,
    }
    assert summary["outcome_classes"]["closure"]["delta"] == 0
    assert summary["failure_causes"]["delivery_error_loose"]["count"] == 1
    assert summary["failure_causes"]["delivery_error_interception"]["count"] == 1
    assert summary["failure_causes"]["arrival_loose"]["count"] == 1
    assert summary["failure_causes"]["arrival_interception"]["count"] == 1


def test_pass_out_of_play_separates_direct_flight_from_residual_free_ball() -> None:
    events = [
        _event(
            "pass",
            "out_of_play",
            tags=["short", "feet", "distance_0_10", "throw_in"],
        ),
        _event(
            "pass",
            "out_of_play",
            tags=[
                "short",
                "feet",
                "distance_0_10",
                "second_ball",
                "goal_kick",
            ],
        ),
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 2, "passes_completed": 0},
        {"passes": 0, "passes_completed": 0},
    )

    assert summary["out_of_play"] == {
        "by_stage": {"direct_flight": 1, "residual_free_ball": 1},
        "by_restart": {"goal_kick": 1, "throw_in": 1},
        "by_distance_and_stage": {
            "0-10m": {"direct_flight": 1, "residual_free_ball": 1}
        },
    }


def test_pass_out_of_play_preserves_corner_restart_classification() -> None:
    summary = _pass_causality_summary(
        [
            _event(
                "pass",
                "out_of_play",
                tags=["short", "space", "distance_20_30", "corner"],
            )
        ],
        {"passes": 1, "passes_completed": 0},
        {"passes": 0, "passes_completed": 0},
    )

    assert summary["out_of_play"]["by_restart"] == {"corner": 1}


def test_distribution_quantiles_are_weighted_by_all_sequences() -> None:
    values = _distribution_values({0: 90, 10: 10})

    assert len(values) == 100
    assert _quantile(values, 0.90) == 0
    assert _quantile(values, 0.91) == 10


def test_real_squad_pass_rate_is_weighted_by_attempts() -> None:
    matches = [
        {
            "home_passes": 10,
            "home_passes_completed": 10,
            "away_passes": 1,
            "away_passes_completed": 0,
        },
        {
            "home_passes": 90,
            "home_passes_completed": 45,
            "away_passes": 99,
            "away_passes_completed": 99,
        },
    ]

    assert _weighted_pass_success_rate(matches, "home") == 55.0
    assert _weighted_pass_success_rate(matches, "away") == 99.0


def test_real_squad_validator_reports_long_shots_without_forbidding_them() -> None:
    events = [
        {
            **_event("shot", "off_target"),
            "origin": [5.0, 34.0],
            "target": [105.0, 34.0],
            "xg": 0.0,
            "xg_exact": 0.0012,
        },
        {
            **_event("shot", "saved"),
            "origin": [90.0, 34.0],
            "target": [105.0, 34.0],
            "xg": 0.2,
        },
    ]

    assert _long_shot_diagnostics(events) == {
        "count": 1,
        "share_of_shots": 0.5,
        "xg": 0.0012,
    }


def test_diagnostic_aggregate_uses_weighted_team_pass_rate() -> None:
    summaries = [
        {
            "home_stats": {
                "passes": 10,
                "passes_completed": 10,
                "pass_success_rate": 100.0,
            }
        },
        {
            "home_stats": {
                "passes": 90,
                "passes_completed": 45,
                "pass_success_rate": 50.0,
            }
        },
    ]

    assert _weighted_team_pass_success_rate(summaries, "home") == 55.0


def test_real_squad_validator_uses_canonical_duel_events_and_team_carries() -> None:
    response = {
        "trace": {"entries": []},
        "events": [
            {
                "event_type": "duel",
                "outcome": "won",
                "origin": [20.0, 30.0],
                "target": [20.0, 30.0],
            },
            {
                "event_type": "duel",
                "outcome": "released",
                "origin": [30.0, 30.0],
                "target": [30.0, 30.0],
            },
            {
                "event_type": "duel",
                "outcome": "lost",
                "origin": [40.0, 30.0],
                "target": [40.0, 30.0],
            },
            {
                **_event("shot", "off_target"),
                "xg": 0.0,
                "xg_exact": 0.004,
            },
        ],
        "replay": [],
        "home_score": 0,
        "away_score": 0,
        "home_stats": {
            "possession": 50.0,
            "shots": 0,
            "shots_on_target": 0,
            "xg": 0.0,
            "passes": 0,
            "passes_completed": 0,
            "tackles": 0,
            "carries": 4,
        },
        "away_stats": {
            "possession": 50.0,
            "shots": 0,
            "shots_on_target": 0,
            "xg": 0.0,
            "passes": 0,
            "passes_completed": 0,
            "tackles": 0,
            "carries": 3,
        },
    }

    summary = _scan_match(response)

    assert summary["attacker_won_duels"] == 2
    assert summary["carries"] == 7
    assert summary["home_xg"] == 0.004


def test_opta_pass_mapping_excludes_crosses_without_claiming_complete_bound() -> None:
    summary = {
        "home_stats": {
            "passes": 10,
            "passes_completed": 6,
            "crosses": 4,
            "crosses_completed": 1,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "away_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [0, 0],
        "shot_outcomes": {"total": {"blocked": 0}},
    }

    alignment = _premier_league_alignment([summary])

    assert alignment["metrics"]["passes"]["current"] == 6.0
    assert alignment["metrics"]["passes"]["comparison_interval"] is None
    assert alignment["metrics"]["pass_success_rate"]["current"] == 83.333
    assert alignment["metrics"]["pass_success_rate"]["comparison_interval"] is None
    assert (
        alignment["metrics"]["pass_success_rate"]["comparison_status"]
        == "known_scope_sensitivity_only"
    )
    assert (
        alignment["engine_scope_diagnostics"][
            "crosses_excluded_from_opta_pass_comparison_per_match"
        ]
        == 4.0
    )
    assert (
        alignment["engine_scope_diagnostics"][
            "completed_crosses_excluded_from_opta_pass_comparison_per_match"
        ]
        == 1.0
    )
    assert alignment["metrics"]["passes"]["calibration_eligible"] is False
    assert alignment["metrics"]["passes"]["absolute_gap"] is None
    assert alignment["metrics"]["pass_success_rate"]["calibration_eligible"] is False
    assert alignment["metrics"]["pass_success_rate"]["absolute_gap"] is None


def test_opta_pass_success_exposes_known_restart_sensitivity_only() -> None:
    summary = {
        "home_stats": {
            "passes": 10,
            "passes_completed": 6,
            "crosses": 2,
            "crosses_completed": 1,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 2,
            "corners": 1,
            "offside_free_kicks": 1,
        },
        "away_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [0, 0],
        "shot_outcomes": {"total": {"blocked": 0}},
    }

    alignment = _premier_league_alignment([summary])

    assert alignment["metrics"]["passes"]["current"] == 8.0
    assert alignment["metrics"]["passes"]["comparison_interval"] is None
    assert alignment["metrics"]["pass_success_rate"]["current"] == 62.5
    assert alignment["metrics"]["pass_success_rate"]["comparison_interval"] is None
    assert alignment["engine_scope_diagnostics"][
        "known_restart_pass_attempt_sensitivity_range_per_match"
    ] == [8.0, 12.0]
    assert alignment["engine_scope_diagnostics"][
        "known_restart_pass_success_rate_sensitivity_range"
    ] == [
        41.667,
        75.0,
    ]
    assert (
        alignment["engine_scope_diagnostics"][
            "goal_kick_pass_candidates_missing_from_engine_pass_actions_per_match"
        ]
        == 2.0
    )


def test_bounded_provider_metric_uses_interval_instead_of_point_gap() -> None:
    summary = {
        "home_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 6,
            "shots_on_target": 2,
            "goals": 1,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "away_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 6,
            "shots_on_target": 2,
            "goals": 1,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [1, 1],
        "shot_outcomes": {"total": {"blocked": 6}},
    }

    alignment = _premier_league_alignment([summary])
    shots_on_target = alignment["metrics"]["shots_on_target"]

    assert shots_on_target["current"] == 4.0
    assert shots_on_target["comparison_interval"] == [4.0, 10.0]
    assert shots_on_target["target_relation"] == "within_interval"
    assert shots_on_target["calibration_eligible"] is False
    assert shots_on_target["absolute_gap"] is None
    shots_on_target_share = alignment["metrics"]["shots_on_target_share"]
    assert shots_on_target_share["current"] == round(4 / 12 * 100, 3)
    assert shots_on_target_share["comparison_interval"] == [
        round(4 / 12 * 100, 3),
        round(10 / 12 * 100, 3),
    ]
    provider_accuracy = alignment["metrics"]["provider_shooting_accuracy"]
    assert provider_accuracy["current"] == round(4 / 6 * 100, 3)
    assert provider_accuracy["comparison_interval"] == [
        round(4 / 6 * 100, 3),
        round(10 / 12 * 100, 3),
    ]


def test_direct_macro_gap_is_not_exposed_as_safe_open_play_tuning_target() -> None:
    summary = {
        "home_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 1,
            "shots_on_target": 1,
            "goals": 1,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "away_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [1, 0],
        "shot_outcomes": {
            "total": {"goal": 1, "saved": 0, "blocked": 0, "off_target": 0, "period_end": 0},
            "censored_on_target": {"home": 0, "away": 0, "total": 0},
        },
    }

    alignment = _premier_league_alignment([summary])

    for metric in ("shots", "goals", "goal_conversion_rate"):
        assert alignment["metrics"][metric]["direct_observation_eligible"] is True
        assert alignment["metrics"][metric]["calibration_eligible"] is False
        assert alignment["metrics"][metric]["absolute_gap"] is None
        assert alignment["metrics"][metric]["relative_gap"] is None
        assert alignment["metrics"][metric]["optimization_safe"] is False
        assert alignment["metrics"][metric]["optimization_caveat"]

    assert alignment["metrics"]["goal_conversion_rate"]["current"] == 100.0
    assert alignment["metrics"]["goal_conversion_rate"]["target"] == round(
        1115 / 9850 * 100,
        3,
    )
    assert (
        alignment["metrics"]["goal_conversion_rate"]["comparison_status"]
        == "derived_direct"
    )
    assert alignment["metrics"]["shots"]["current_relation_to_target"] == "below_target"
    assert alignment["metrics"]["goals"]["current_relation_to_target"] == "below_target"
    assert (
        alignment["metrics"]["goal_conversion_rate"]["current_relation_to_target"]
        == "above_target"
    )


def test_provider_shots_on_target_excludes_period_end_censored_attempts() -> None:
    summary = {
        "home_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 4,
            "shots_on_target": 3,
            "goals": 1,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "away_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [1, 0],
        "shot_outcomes": {
            "total": {
                "goal": 1,
                "saved": 1,
                "blocked": 1,
                "off_target": 0,
                "period_end": 1,
            },
            "censored_on_target": {"home": 1, "away": 0, "total": 1},
        },
    }

    alignment = _premier_league_alignment([summary])
    shots_on_target = alignment["metrics"]["shots_on_target"]

    assert shots_on_target["current"] == 2.0
    assert shots_on_target["comparison_interval"] == [2.0, 4.0]
    assert (
        alignment["engine_scope_diagnostics"][
            "raw_engine_shots_on_target_per_match"
        ]
        == 3.0
    )
    assert (
        alignment["engine_scope_diagnostics"][
            "period_end_on_target_censored_per_match"
        ]
        == 1.0
    )


def test_provider_pass_success_exposes_period_end_outcome_uncertainty() -> None:
    summary = {
        "home_stats": {
            "passes": 10,
            "passes_completed": 6,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "away_stats": {
            "passes": 0,
            "passes_completed": 0,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "goal_kicks": 0,
            "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [0, 0],
        "pass_causality": {
            "attributed_outcomes": {"completed": 6, "loose": 3, "period_end": 1},
        },
        "shot_outcomes": {
            "total": {
                "goal": 0,
                "saved": 0,
                "blocked": 0,
                "off_target": 0,
                "period_end": 0,
            },
            "censored_on_target": {"home": 0, "away": 0, "total": 0},
        },
    }

    alignment = _premier_league_alignment([summary])
    pass_success = alignment["metrics"]["pass_success_rate"]

    assert pass_success["current"] == 60.0
    assert pass_success["comparison_interval"] is None
    assert pass_success["known_scope_sensitivity_interval"] == [60.0, 70.0]
    assert (
        alignment["engine_scope_diagnostics"][
            "period_end_pass_outcomes_censored_per_match"
        ]
        == 1.0
    )


def test_shot_accuracy_reports_internal_block_classification_sensitivity() -> None:
    metrics = shot_accuracy_metrics(
        shots=20,
        shots_on_target=6,
        blocked_shots=5,
    )

    assert metrics["shots_on_target_share_pct"] == 30.0
    assert metrics["provider_accuracy_if_all_blocks_ordinary_pct"] == 40.0
    assert round(
        metrics["provider_accuracy_if_all_blocks_last_line_pct"], 6
    ) == 55.0


def test_sequence_summary_marks_event_observation_scope_and_id_gaps() -> None:
    events = [
        {
            **_event("pass", "completed"),
            "seq": 1,
            "tick": 10,
            "match_second": 20,
            "possession_id": 3,
            "half": 1,
        },
        {
            **_event("shot", "off_target"),
            "seq": 2,
            "tick": 20,
            "match_second": 40,
            "possession_id": 5,
            "half": 1,
        },
    ]

    summary = _sequence_summary(events, home_attacking_right=True)

    assert summary["sequence_count"] == 2
    assert summary["observability"] == {
        "first_possession_id": 3,
        "last_possession_id": 5,
        "possession_id_span": 3,
        "observed_possession_ids": 2,
        "missing_possession_ids_in_span": 1,
        "all_possession_ids_observed": False,
    }
    assert summary["scope"].startswith("event_observed possession segments only")


def test_benchmark_counts_blocked_shot_terminals_not_defender_stat_aliases() -> None:
    events = [
        _event("shot", "blocked"),
        _event("shot", "saved"),
        _event("duel", "won", tags=["block"]),
    ]

    assert blocked_shot_count(events) == 1


def test_benchmark_does_not_treat_one_match_as_side_balance_sample() -> None:
    stats = {
        "matches": 1,
        "home_star": 5,
        "away_star": 5,
        "avg_goals_per_match": 1.0,
        "avg_shots_per_match": 13.0,
        "shots_on_target_share_pct": 23.1,
        "raw_engine_pass_success_rate_pct": 86.8,
        "avg_home_possession": 59.0,
        "avg_away_possession": 41.0,
        "home_win_pct": 0.0,
        "away_win_pct": 100.0,
    }

    assert run_assertions(stats)


def test_aggregate_shot_outcomes_preserve_mutually_exclusive_terminals() -> None:
    summaries = [
        {
            "shot_outcomes": {
                "by_team": {
                    "home": {
                        "goal": 1,
                        "saved": 1,
                        "blocked": 2,
                        "off_target": 3,
                        "period_end": 0,
                    },
                    "away": {
                        "goal": 0,
                        "saved": 1,
                        "blocked": 0,
                        "off_target": 2,
                        "period_end": 1,
                    },
                }
            }
        },
        {
            "shot_outcomes": {
                "by_team": {
                    "home": {
                        "goal": 0,
                        "saved": 0,
                        "blocked": 1,
                        "off_target": 1,
                        "period_end": 0,
                    },
                    "away": {
                        "goal": 1,
                        "saved": 0,
                        "blocked": 1,
                        "off_target": 0,
                        "period_end": 0,
                    },
                }
            }
        },
    ]

    outcomes = _aggregate_shot_outcomes(summaries)

    assert outcomes["total"] == {
        "goal": 2,
        "saved": 2,
        "blocked": 4,
        "off_target": 6,
        "period_end": 1,
    }
    assert outcomes["terminal_count"] == 15
    assert outcomes["per_match"]["blocked"] == 2.0
    assert outcomes["share"]["period_end"] == round(1 / 15, 4)


def test_sample_integrity_gate_rejects_any_non_ok_team_check() -> None:
    summaries = [
        {
            "metric_integrity": {
                "teams": {
                    "home": {"checks": {"xg.team_vs_events": {"status": "ok"}}},
                    "away": {"checks": {"xg.team_vs_events": {"status": "ok"}}},
                }
            }
        },
        {
            "metric_integrity": {
                "teams": {
                    "home": {"checks": {"xg.team_vs_events": {"status": "warning"}}},
                    "away": {"checks": {"xg.team_vs_events": {"status": "ok"}}},
                }
            }
        },
    ]

    assert not _all_team_checks_ok(summaries, ("xg.team_vs_events",))


def test_failed_pass_and_second_ball_do_not_create_key_pass() -> None:
    events = [
        {
            **_event("pass", "loose"),
            "seq": 1,
            "possession_id": 7,
            "player": {"player_id": "passer"},
            "target_player": {"player_id": "shooter"},
        },
        {
            **_event("recovery", "won"),
            "seq": 2,
            "possession_id": 7,
            "player": {"player_id": "shooter"},
        },
        {
            **_event("shot", "saved"),
            "seq": 3,
            "possession_id": 7,
            "player": {"player_id": "shooter"},
            "xg": 0.25,
        },
    ]

    key_passes, assists, expected_assists = _direct_shot_creations(events, "home")

    assert key_passes == {}
    assert assists == {}
    assert expected_assists == 0.0


def test_direct_shot_creation_xa_uses_exact_xg() -> None:
    events = [
        {
            **_event("pass", "completed"),
            "seq": 1,
            "possession_id": 7,
            "player": {"player_id": "passer"},
            "target_player": {"player_id": "shooter"},
        },
        {
            **_event("shot", "saved"),
            "seq": 2,
            "possession_id": 7,
            "player": {"player_id": "shooter"},
            "assist_player": None,
            "xg": 0.01,
            "xg_exact": 0.0149,
        },
    ]

    key_passes, assists, expected_assists = _direct_shot_creations(events, "home")

    assert key_passes == {"passer": 1}
    assert assists == {}
    assert expected_assists == 0.0149


def test_same_team_recovery_after_technical_error_breaks_shot_creation() -> None:
    events = [
        {
            **_event("pass", "completed"),
            "seq": 1,
            "possession_id": 7,
            "player": {"player_id": "passer"},
            "target_player": {"player_id": "shooter"},
        },
        {
            **_event(
                "carry",
                "loose",
                tags=["technical_error", "second_ball"],
            ),
            "seq": 2,
            "possession_id": 7,
            "player": {"player_id": "shooter"},
        },
        {
            **_event("shot", "goal"),
            "seq": 3,
            "possession_id": 7,
            "player": {"player_id": "shooter"},
            "assist_player": {"player_id": "passer"},
            "xg": 0.25,
        },
    ]

    key_passes, assists, expected_assists = _direct_shot_creations(events, "home")

    assert key_passes == {}
    assert assists == {}
    assert expected_assists == 0.0


def test_big_chance_integrity_uses_unrounded_event_tag() -> None:
    player_stats = [
        {
            "shots": 1,
            "shots_on_target": 0,
            "goals": 0,
            "passes": 0,
            "completed_passes": 0,
            "tackles_attempted": 0,
            "tackles_won": 0,
            "take_ons": 0,
            "successful_take_ons": 0,
            "saves": 0,
            "blocks": 0,
            "interceptions": 0,
            "pressures": 0,
            "successful_pressures": 0,
            "turnovers": 0,
            "clearances": 0,
            "carries": 0,
            "carries_completed": 0,
            "crosses": 0,
            "successful_crosses": 0,
            "long_passes": 0,
            "completed_long_passes": 0,
            "key_passes": 0,
            "offsides": 0,
            "progressive_passes": 0,
            "passes_into_final_third": 0,
            "passes_into_box": 0,
            "carries_into_final_third": 0,
            "carries_into_box": 0,
            "progressive_carries": 0,
            "xg": 0.29,
            "post_shot_xg": 0.0,
            "xa": 0.0,
            "assists": 0,
            "psxg_faced": 0.0,
            "goals_conceded": 0,
        }
    ]
    empty_stats = {
        "shots": 0,
        "shots_on_target": 0,
        "goals": 0,
        "passes": 0,
        "passes_completed": 0,
        "pass_success_rate": 0.0,
        "tackle_attempts": 0,
        "tackles_won": 0,
        "take_ons": 0,
        "successful_take_ons": 0,
        "saves": 0,
        "blocks": 0,
        "interceptions": 0,
        "pressures": 0,
        "successful_pressures": 0,
        "turnovers": 0,
        "clearances": 0,
        "carries": 0,
        "carries_completed": 0,
        "crosses": 0,
        "crosses_completed": 0,
        "long_passes": 0,
        "completed_long_passes": 0,
        "key_passes": 0,
        "offsides": 0,
        "progressive_passes": 0,
        "passes_into_final_third": 0,
        "passes_into_box": 0,
        "carries_into_final_third": 0,
        "carries_into_box": 0,
        "progressive_carries": 0,
        "shots_in_box": 0,
        "shots_outside_box": 0,
        "xg": 0.0,
        "post_shot_xg": 0.0,
        "big_chances": 0,
        "corners": 0,
        "goal_kicks": 0,
        "throw_ins": 0,
        "offside_free_kicks": 0,
        "tackles": 0,
        "dribbles": 0,
        "free_kicks": 0,
        "possession": 50.0,
    }
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [
            {
                **_event("shot", "off_target", tags=["big_chance"]),
                "seq": 1,
                "possession_id": 1,
                "player": {"player_id": "shooter"},
                "target_player": None,
                "assist_player": None,
                "xg": 0.29,
            }
        ],
        "home_stats": {
            **empty_stats,
            "shots": 1,
            "shots_outside_box": 1,
            "xg": 0.29,
            "big_chances": 1,
        },
        "away_stats": empty_stats,
        "home_player_stats": player_stats,
        "away_player_stats": [],
    }

    integrity = _metric_integrity_summary(response)

    assert (
        integrity["teams"]["home"]["checks"]["big_chances.team_vs_events"]["status"]
        == "ok"
    )


def test_possession_integrity_rejects_ball_state_partition_mismatch() -> None:
    empty_stats = {
        "shots": 0,
        "shots_on_target": 0,
        "goals": 0,
        "passes": 0,
        "passes_completed": 0,
        "pass_success_rate": 0.0,
        "tackle_attempts": 0,
        "tackles_won": 0,
        "take_ons": 0,
        "successful_take_ons": 0,
        "saves": 0,
        "blocks": 0,
        "interceptions": 0,
        "pressures": 0,
        "successful_pressures": 0,
        "turnovers": 0,
        "clearances": 0,
        "carries": 0,
        "carries_completed": 0,
        "crosses": 0,
        "crosses_completed": 0,
        "long_passes": 0,
        "completed_long_passes": 0,
        "key_passes": 0,
        "offsides": 0,
        "progressive_passes": 0,
        "passes_into_final_third": 0,
        "passes_into_box": 0,
        "carries_into_final_third": 0,
        "carries_into_box": 0,
        "progressive_carries": 0,
        "shots_in_box": 0,
        "shots_outside_box": 0,
        "xg": 0.0,
        "post_shot_xg": 0.0,
        "big_chances": 0,
        "corners": 0,
        "goal_kicks": 0,
        "throw_ins": 0,
        "offside_free_kicks": 0,
        "tackles": 0,
        "dribbles": 0,
        "free_kicks": 0,
        "possession": 50.0,
    }
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [],
        "home_stats": empty_stats,
        "away_stats": empty_stats,
        "home_player_stats": [],
        "away_player_stats": [],
        "match_clock": {
            "match_ticks": 180,
            "active_play_ticks": 170,
            "dead_ball_ticks": 10,
            "ball_state_ticks": {
                "held": 100,
                "in_flight": 40,
                "free_ball": 20,
                "dead": 10,
            }
        },
    }

    integrity = _metric_integrity_summary(response)

    check = integrity["cross_team_checks"]["ball_state_ticks_match_match_clock"]
    assert check["status"] == "error"
    assert check["actual"] == 170.0
    assert check["expected"] == 180.0


def test_possession_integrity_reports_controlled_and_neutral_time() -> None:
    empty_stats = {
        "possession": 50.0,
    }
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [],
        "home_stats": empty_stats,
        "away_stats": empty_stats,
        "home_player_stats": [],
        "away_player_stats": [],
        "match_clock": {
            "match_ticks": 200,
            "active_play_ticks": 180,
            "dead_ball_ticks": 20,
            "ball_state_ticks": {
                "held": 100,
                "in_flight": 50,
                "free_ball": 30,
                "dead": 20,
            },
        },
    }

    integrity = _metric_integrity_summary(response)

    assert integrity["possession_scope"] == {
        "controlled_ticks": 100,
        "neutral_active_ticks": 80,
        "dead_ticks": 20,
        "controlled_share_of_match": 0.5,
        "controlled_share_of_active_play": round(100 / 180, 4),
        "neutral_share_of_active_play": round(80 / 180, 4),
    }


def test_metric_integrity_exposes_calibration_policy_and_placeholders() -> None:
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [],
        "home_stats": {"possession": 50.0},
        "away_stats": {"possession": 50.0},
        "home_player_stats": [],
        "away_player_stats": [],
        "match_clock": {
            "match_ticks": 100,
            "active_play_ticks": 90,
            "dead_ball_ticks": 10,
            "ball_state_ticks": {
                "held": 60,
                "in_flight": 20,
                "free_ball": 10,
                "dead": 10,
            },
        },
    }

    integrity = _metric_integrity_summary(response)

    assert integrity["external_comparability"]["pass_success_rate"].startswith(
        "scope_mismatch"
    )
    assert integrity["external_comparability"]["interceptions"].startswith(
        "internal_opposing_control_wins"
    )
    assert integrity["external_comparability"]["headers"] == (
        "unsupported_zero_placeholder"
    )
    assert integrity["external_comparability"]["post_shot_xg"] == (
        "internal_proxy_not_provider_comparable"
    )
    assert integrity["definitions"]["post_shot_xg"].startswith("internal proxy")
    assert "pass_success_rate" in integrity["calibration_policy"][
        "scope_mismatched_do_not_point_calibrate"
    ]["metrics"]
    assert integrity["calibration_policy"]["unsupported_placeholders"]["metrics"] == [
        "headers",
        "headers_won",
    ]


def test_metric_integrity_separates_validation_results_from_compatibility_notices() -> None:
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [],
        "home_stats": {"possession": 50.0},
        "away_stats": {"possession": 50.0},
        "home_player_stats": [],
        "away_player_stats": [],
    }

    integrity = _metric_integrity_summary(response)

    assert integrity["issue_breakdown"]["validation_checks"].get("warning", 0) == 0
    assert integrity["issue_breakdown"]["validation_checks"]["ok"] > 0
    assert integrity["issue_breakdown"]["compatibility_notices"] == {
        "total": 6,
        "by_field": {
            "dribbles": 2,
            "free_kicks": 2,
            "tackles": 2,
        },
    }
    assert integrity["issue_counts"]["warning"] == 6


def test_successful_take_on_requires_won_completed_take_on_event() -> None:
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [
            _event("duel", "attempted", tags=["take_on_attempt"]),
            _event("duel", "attempted", tags=["take_on_attempt"]),
            _event("duel", "retained", tags=["take_on"]),
            _event(
                "duel",
                "won",
                tags=["take_on", "take_on_completed", "spatially_separated"],
            ),
        ],
        "home_stats": {
            "take_ons": 2,
            "successful_take_ons": 1,
            "possession": 50.0,
        },
        "away_stats": {"possession": 50.0},
        "home_player_stats": [
            {
                "take_ons": 2,
                "successful_take_ons": 1,
            }
        ],
        "away_player_stats": [],
    }

    integrity = _metric_integrity_summary(response)

    assert integrity["teams"]["home"]["checks"][
        "successful_take_ons.team_vs_events"
    ]["status"] == "ok"
    assert integrity["teams"]["home"]["checks"]["take_ons.team_vs_events"]["status"] == "ok"


def test_successful_take_on_rejects_retained_contact_without_spatial_separation() -> None:
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [
            _event("duel", "attempted", tags=["take_on_attempt"]),
            _event("duel", "retained", tags=["take_on"]),
            _event("duel", "won", tags=["take_on", "take_on_completed"]),
        ],
        "home_stats": {
            "take_ons": 1,
            "successful_take_ons": 1,
            "possession": 50.0,
        },
        "away_stats": {"possession": 50.0},
        "home_player_stats": [
            {
                "take_ons": 1,
                "successful_take_ons": 1,
            }
        ],
        "away_player_stats": [],
    }

    integrity = _metric_integrity_summary(response)

    check = integrity["teams"]["home"]["checks"][
        "successful_take_ons.team_vs_events"
    ]
    assert check["status"] == "error"
    assert check["expected"] == 0.0


def test_shot_release_summary_separates_selected_unreleased_and_released_attempts() -> None:
    response = {
        "events": [
            _event("shot", "saved", team="home"),
            _event("shot", "off_target", team="away"),
        ],
        "trace": {
            "entries": [
                {
                    "tick": 5,
                    "type": "event",
                    "event": "shot_prepared",
                    "team": "home",
                    "body_release_probability": 0.15,
                },
                {
                    "tick": 10,
                    "type": "event",
                    "event": "shot_unreleased",
                    "team": "home",
                    "body_release_probability": 0.25,
                    "body_release_roll": 0.80,
                    "release_readiness_before": 0.20,
                    "release_readiness_after": 0.45,
                },
                {
                    "tick": 20,
                    "type": "event",
                    "event": "shot_unreleased",
                    "team": "away",
                    "body_release_probability": 0.60,
                    "body_release_roll": 0.75,
                    "release_readiness_before": 0.50,
                    "release_readiness_after": 0.70,
                },
            ]
        },
    }

    summary = _shot_release_summary(response)

    assert summary["selected"] == 4
    assert summary["prepared_contacts"] == 1
    assert summary["unreleased"] == 2
    assert summary["abandoned"] == 0
    assert summary["released"] == 2
    assert summary["release_rate"] == 0.5
    assert summary["by_team"]["home"] == {
        "selected": 2,
        "prepared_contacts": 1,
        "unreleased": 1,
        "abandoned": 0,
        "pre_release_duel_losses": 0,
        "released": 1,
        "unresolved": 0,
        "release_rate": 0.5,
    }
    assert summary["unreleased_body_probability"]["mean"] == 0.425
    assert summary["unreleased_readiness"]["mean_before"] == 0.35
    assert summary["unreleased_readiness"]["mean_after"] == 0.575


def test_shot_family_summary_separates_carry_finishes_from_shoot_actions() -> None:
    summary = _shot_family_summary(
        [
            {**_event("shot", "saved"), "xg": 0.2},
            {**_event("shot", "goal"), "xg": 0.3},
            {
                **_event("shot", "goal", tags=["carry_finish"]),
                "xg": 0.8,
            },
        ]
    )

    assert summary["shoot_action"] == {
        "shots": 2,
        "goals": 1,
        "event_xg": 0.5,
        "xg_per_shot": 0.25,
        "goal_conversion_rate": 0.5,
    }
    assert summary["carry_finish"] == {
        "shots": 1,
        "goals": 1,
        "event_xg": 0.8,
        "xg_per_shot": 0.8,
        "goal_conversion_rate": 1.0,
    }
    assert summary["closure"] == {
        "classified": 3,
        "shot_events": 3,
        "delta": 0,
    }


def test_shot_xg_aggregation_prefers_exact_event_value_over_display_rounding() -> None:
    events = [
        {
            **_event("shot", "saved"),
            "xg": 0.01,
            "xg_exact": 0.0149,
        },
        {
            **_event("shot", "goal", tags=["carry_finish"]),
            "xg": 0.01,
            "xg_exact": 0.0149,
        },
    ]

    outcomes = _shot_outcome_summary(events)
    families = _shot_family_summary(events)

    assert outcomes["event_xg"]["total"] == 0.0298
    assert families["shoot_action"]["event_xg"] == 0.0149
    assert families["carry_finish"]["event_xg"] == 0.0149
    assert families["shoot_action"]["xg_per_shot"] == 0.0149


def test_shot_release_summary_excludes_carry_finish_from_shoot_releases() -> None:
    response = {
        "events": [
            _event("shot", "saved", team="home"),
            _event("shot", "goal", team="away", tags=["carry_finish"]),
        ],
        "trace": {"entries": [], "decisions": []},
    }

    summary = _shot_release_summary(response)

    assert summary["selected"] == 1
    assert summary["released"] == 1
    assert summary["by_team"]["home"]["released"] == 1
    assert summary["by_team"]["away"]["released"] == 0


def test_shot_release_summary_uses_decisions_and_accounts_for_pre_release_duels() -> None:
    response = {
        "events": [
            _event("shot", "saved", team="home"),
            _event(
                "tackle",
                "won",
                team="away",
                tags=["possession_won", "shot_release", "blocked"],
            ),
        ],
        "trace": {
            "decisions": [
                {
                    "tick": tick,
                    "team": "home",
                    "chosen": {"action_type": "shoot"},
                }
                for tick in (10, 20, 30)
            ],
            "entries": [
                {
                    "tick": 9,
                    "type": "event",
                    "event": "shot_prepared",
                    "team": "home",
                },
                {
                    "tick": 10,
                    "type": "event",
                    "event": "shot_unreleased",
                    "team": "home",
                    "body_release_probability": 0.25,
                    "release_readiness_before": 0.20,
                    "release_readiness_after": 0.45,
                }
            ],
        },
    }

    summary = _shot_release_summary(response)

    assert summary["selected"] == 3
    assert summary["prepared_contacts"] == 1
    assert summary["unreleased"] == 1
    assert summary["abandoned"] == 0
    assert summary["pre_release_duel_losses"] == 1
    assert summary["released"] == 1
    assert summary["unresolved"] == 0
    assert summary["selection_accounting_status"] == "ok"


def test_shot_release_summary_does_not_count_attacker_retention_as_duel_loss() -> None:
    response = {
        "events": [
            _event(
                "duel",
                "retained",
                team="home",
                tags=["shot_release", "body_challenge"],
            ),
            _event("shot", "saved", team="home"),
        ],
        "trace": {
            "decisions": [
                {
                    "tick": 10,
                    "team": "home",
                    "chosen": {"action_type": "shoot"},
                }
            ],
            "entries": [],
        },
    }

    summary = _shot_release_summary(response)

    assert summary["selected"] == 1
    assert summary["pre_release_duel_losses"] == 0
    assert summary["released"] == 1
    assert summary["unresolved"] == 0


def test_shot_release_summary_closes_prepared_shot_abandonment() -> None:
    response = {
        "events": [],
        "trace": {
            "decisions": [
                {
                    "tick": 10,
                    "team": "home",
                    "chosen": {"action_type": "shoot"},
                }
            ],
            "entries": [
                {
                    "tick": 10,
                    "type": "event",
                    "event": "shot_prepared",
                    "team": "home",
                },
                {
                    "tick": 11,
                    "type": "event",
                    "event": "shot_abandoned",
                    "team": "home",
                    "reason": "better_visible_release",
                },
            ],
        },
    }

    summary = _shot_release_summary(response)

    assert summary["selected"] == 1
    assert summary["prepared_contacts"] == 1
    assert summary["abandoned"] == 1
    assert summary["unreleased"] == 0
    assert summary["released"] == 0
    assert summary["unresolved"] == 0
    assert summary["selection_accounting_status"] == "ok"
