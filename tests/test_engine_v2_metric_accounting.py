from __future__ import annotations

from collections import Counter, defaultdict

import pytest

from scripts.diagnose_engine_v2_match_pace import (
    _action_pace_summary,
    _aggregate_pass_terminal_control,
    _aggregate_reorient_follow_up,
    _aggregate_team_control_chains,
    _additional_settlement_mass,
    _aerial_distribution_intent_counterfactual_summary,
    _reorient_live_same_tick_summary,
    _all_team_checks_ok,
    _aggregate_shot_outcomes,
    _body_challenge_summary,
    _binary_ranking_auc,
    _balanced_formation_graph_elasticity,
    _continuous_connection_redundancy,
    _continuous_coordination_optima,
    _continuous_triangle_closure,
    _controller_handoff_receipt_upper_bound,
    _carry_contact_summary,
    _communication_pass_counterfactual_summary,
    _communication_receipt_follow_up_counterfactual_summary,
    _direct_shot_creations,
    _engine_possession_interruption_hazard,
    _extend_candidate_motion_to_horizon,
    _distribution_values,
    _free_ball_control_summary,
    _formal_tackle_trace_summary,
    _held_body_separation_summary,
    _held_action_execution_by_possession_summary,
    _high_pressure_support_gap_episode_summary,
    _metric_integrity_summary,
    _nonpass_pass_opportunity_by_possession_summary,
    _normalized_trace_spatial_claim,
    _optimistic_outlet_resource_candidate,
    _optional_trace_rows,
    _outcome_distinguishability_selection_counterfactual,
    _pass_breakdown_scope_integrity_checks,
    _pass_causality_summary,
    _possession_chain_budget_summary,
    _pass_successor_support_alternative_ledger,
    _pass_terminal_control_summary,
    _physical_short_pass_availability_funnel,
    _premier_league_alignment,
    _pressure_projection_scope_summary,
    _prospective_carrier_engagement_coverage,
    _quantile,
    _relative_motion_projection,
    _receiver_hierarchical_pass_distribution,
    _rigid_translation_geometry,
    _targeted_formation_graph_elasticity,
    _retarget_displacement_preserving_motion_components,
    _restart_release_lifecycle,
    _sequence_summary,
    _shot_family_summary,
    _shot_outcome_summary,
    _shot_release_summary,
    _selected_pass_release_funnel,
    _support_task_pass_funnel,
    _support_arrival_stability_summary,
    _support_responsibility_identity_continuity_summary,
    _successor_transition_support_upper_bound,
    _successor_transition_support_episode_intersection,
    _team_plan_pass_policy_decomposition,
    _team_plan_policy_pair_decomposition,
    _team_control_chain_summary,
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


def test_team_control_chains_merge_adjacent_same_team_possessions() -> None:
    events = [
        {
            **_event("pass", "completed", "home"),
            "possession_id": 1, "half": 1, "tick": 1, "seq": 1,
            "match_second": 1.0,
        },
        {
            **_event("pass", "out_of_play", "home"),
            "possession_id": 2, "half": 1, "tick": 4, "seq": 2,
            "match_second": 4.0,
        },
        {
            **_event("pass", "completed", "away", ["cross"]),
            "possession_id": 3, "half": 1, "tick": 7, "seq": 3,
            "match_second": 7.0,
        },
        {
            **_event("pass", "completed", "away"),
            "possession_id": 3, "half": 1, "tick": 9, "seq": 4,
            "match_second": 9.0,
        },
    ]

    summary = _team_control_chain_summary(events)

    assert summary["possession_segments"] == 3
    assert summary["team_control_chains"] == 2
    assert summary["merged_same_team_boundaries"] == 1
    assert summary["provider_pass_attempts"] == 3
    assert summary["provider_pass_completions"] == 2
    assert summary["provider_pass_attempts_per_chain"] == 1.5
    assert summary["provider_completed_passes_per_chain"] == 1.0
    assert summary["completed_pass_count_bands"]["1"] == {
        "count": 2,
        "share": 1.0,
    }

    aggregate = _aggregate_team_control_chains([
        {"sequence": {"team_control_chains": summary}},
        {"sequence": {"team_control_chains": summary}},
    ])
    assert aggregate["team_control_chains_per_match"] == 2.0
    assert aggregate["provider_pass_attempts_per_chain"] == 1.5
    assert aggregate["provider_completed_passes_per_chain"] == 1.0
    assert aggregate["completed_pass_count_bands"]["1"] == {
        "count": 4,
        "share": 1.0,
    }


def test_relative_motion_projection_uses_velocity_not_target_intent() -> None:
    projection = _relative_motion_projection(
        [0.0, 0.0],
        [1.0, 0.0],
        [10.0, 0.0],
        [-3.0, 0.0],
        3.0,
    )

    assert projection["current_distance_m"] == 10.0
    assert projection["terminal_distance_m"] == 2.0
    assert projection["closest_distance_m"] == 0.0
    assert projection["closest_tick"] == 2.5
    assert projection["terminal_closing_m"] == 8.0


def test_binary_ranking_auc_is_threshold_free_and_counts_ties_half() -> None:
    assert _binary_ranking_auc([0.8, 0.4], [0.4, 0.2]) == 0.875
    assert _binary_ranking_auc([], [0.2]) is None


def test_normalized_spatial_claim_accepts_raw_and_intermediate_field_names() -> None:
    raw = {
        "claim_active": True,
        "claim_origin": [10.0, 20.0],
        "target": [18.0, 24.0],
        "occupancy_radius": 4.0,
        "corridor_half_width": 2.0,
        "depth_band": 1,
        "width_band": 0,
    }
    intermediate = {
        "active": True,
        "origin": (10.0, 20.0),
        "target": (18.0, 24.0),
        "occupancy_radius": 4.0,
        "corridor_half_width": 2.0,
        "depth_band": 1,
        "width_band": 0,
    }

    assert _normalized_trace_spatial_claim(raw) == (
        _normalized_trace_spatial_claim(intermediate)
    )


def test_successor_transition_upper_bound_adopts_only_higher_scoring_support() -> None:
    first = {
        "successor_support_counterfactual": [
            {
                "idx": 2, "is_passer": False, "current_score": 0.10,
                "successor_support_score": 0.20,
                "projected_receipt_distance_to_destination_m": 8.0,
            },
            {
                "idx": 3, "is_passer": True, "current_score": 0.20,
                "successor_support_score": 0.10,
                "projected_receipt_distance_to_destination_m": 6.0,
            },
            {
                "idx": 4, "is_passer": False, "current_score": 0.30,
                "successor_support_score": 0.40,
                "projected_receipt_distance_to_destination_m": 12.0,
            },
        ]
    }
    final = {
        "attacking_players": [
            {"idx": 2, "distance_to_observed_destination_m": 14.0},
            {"idx": 3, "distance_to_observed_destination_m": 7.0},
            {"idx": 4, "distance_to_observed_destination_m": 11.0},
        ]
    }

    all_players = _successor_transition_support_upper_bound(
        first, final, include_passer=True
    )
    other_only = _successor_transition_support_upper_bound(
        first, final, include_passer=False
    )

    assert all_players == {
        "eligible_players": 3,
        "adopted_players": 2,
        "baseline_nearest_m": 7.0,
        "projected_nearest_m": 7.0,
        "nearest_is_passer": True,
        "nearest_adopted": False,
        "nearest_player_idx": 3,
        "nearest_production_flight_attack_active": False,
        "nearest_production_target_to_successor_m": None,
        "nearest_production_effective_target_to_successor_m": None,
    }
    assert other_only == {
        "eligible_players": 2,
        "adopted_players": 2,
        "baseline_nearest_m": 11.0,
        "projected_nearest_m": 8.0,
        "nearest_is_passer": False,
        "nearest_adopted": True,
        "nearest_player_idx": 2,
        "nearest_production_flight_attack_active": False,
        "nearest_production_target_to_successor_m": None,
        "nearest_production_effective_target_to_successor_m": None,
    }


def test_successor_transition_upper_bound_uses_physical_receipt_geometry() -> None:
    first = {
        "successor_support_counterfactual": [
            {
                "idx": 2,
                "is_passer": False,
                "current_score": 0.10,
                "successor_support_score": 0.20,
                "projected_receipt_pos": [8.0, 0.0],
                "projected_receipt_distance_to_destination_m": 2.0,
            },
            {
                "idx": 3,
                "is_passer": True,
                "current_score": 0.20,
                "successor_support_score": 0.10,
                "projected_receipt_pos": [4.0, 0.0],
                "projected_receipt_distance_to_destination_m": 6.0,
            },
        ]
    }
    final = {
        "attacking_players": [
            {"idx": 2, "distance_to_observed_destination_m": 1.0},
            {"idx": 3, "distance_to_observed_destination_m": 2.0},
        ]
    }
    terminal = {
        "winner_pos": [20.0, 0.0],
        "actual_receipt_outfield_teammates": [
            {"idx": 2, "distance_to_receiver_m": 14.0},
            {"idx": 3, "distance_to_receiver_m": 11.0},
        ],
    }

    result = _successor_transition_support_upper_bound(
        first,
        final,
        include_passer=True,
        receipt_terminal=terminal,
    )

    assert result == {
        "eligible_players": 2,
        "adopted_players": 1,
        "baseline_nearest_m": 11.0,
        "projected_nearest_m": 11.0,
        "nearest_is_passer": True,
        "nearest_adopted": False,
        "nearest_player_idx": 3,
        "nearest_production_flight_attack_active": False,
        "nearest_production_target_to_successor_m": None,
        "nearest_production_effective_target_to_successor_m": None,
    }


def test_successor_transition_episode_intersection_joins_intended_receipt_replays() -> None:
    gaps = [
        {
            "tick": 13,
            "possession_id": 2,
            "team": "home",
            "holder_idx": 4,
            "cause": "controller_handoff",
            "acquisition_source": "intended_pass_receipt",
            "acquisition_replay_id": "pass-1",
            "nearest_support_distance_m": 12.0,
        },
        {
            "tick": 20,
            "possession_id": 3,
            "team": "away",
            "holder_idx": 7,
            "cause": "new_possession",
            "acquisition_source": "intended_pass_receipt",
            "acquisition_replay_id": "pass-2",
            "nearest_support_distance_m": 13.0,
        },
        {
            "tick": 30,
            "acquisition_source": "pass_interception",
            "acquisition_replay_id": "pass-3",
        },
    ]
    transitions = [
        {
            "profile": "all_nonreceiver",
            "replay_id": "pass-1",
            "receipt_tick": 12,
            "baseline_nearest_m": 12.5,
            "projected_nearest_m": 8.0,
            "nearest_is_passer": True,
            "nearest_adopted": True,
        },
        {
            "profile": "all_nonreceiver",
            "replay_id": "pass-2",
            "receipt_tick": 19,
            "baseline_nearest_m": 13.5,
            "projected_nearest_m": 11.0,
            "nearest_is_passer": False,
            "nearest_adopted": True,
        },
        {
            "profile": "other_only",
            "replay_id": "pass-1",
            "receipt_tick": 12,
            "baseline_nearest_m": 14.0,
            "projected_nearest_m": 9.0,
            "nearest_is_passer": False,
            "nearest_adopted": True,
        },
        {
            "profile": "other_only",
            "replay_id": "pass-2",
            "receipt_tick": 19,
            "missing_reason": "missing_flight_frame",
        },
    ]

    report = _successor_transition_support_episode_intersection(gaps, transitions)

    assert report["gap_episode_count"] == 3
    assert report["intended_receipt_episode_count"] == 2
    assert report["profiles"]["all_nonreceiver"]["counts"] == {
        "baseline_outside_10m": 2,
        "creates_within_10m": 1,
        "duplicate_transition_cases": 0,
        "matched_transition_projection": 2,
        "nearest_adopted": 2,
        "nearest_is_other": 1,
        "nearest_is_passer": 1,
        "remains_outside_10m": 1,
        "target_episodes": 2,
        "target_unique_replays": 2,
        "upper_bound_outside_10m": 1,
        "upper_bound_within_10m": 1,
    }
    assert report["profiles"]["other_only"]["counts"][
        "missing_transition_projection"
    ] == 1
    assert report["profiles"]["other_only"]["counts"][
        "missing_reason=missing_flight_frame"
    ] == 1
    assert report["profiles"]["other_only"]["cases"][0][
        "creates_within_10m"
    ] is True
    assert report["profiles"]["other_only"]["cases"][1][
        "missing_reason"
    ] == "missing_flight_frame"


def test_receiver_hierarchy_removes_target_count_mass_without_changing_target_ratios() -> None:
    distribution = _receiver_hierarchical_pass_distribution([
        {
            "near_optimal": True, "receiver_idx": 1, "softmax_weight": 1.0,
            "distance_m": 8.0, "target_kind": "feet", "is_long": False,
            "target": [-8.0, 0.0],
            "receiver_offset_m": 0.0, "retention_probability": 0.9,
            "option_duration_seconds": 1.0, "retained_control_probability": 0.9,
            "opposing_control_probability": 0.05, "unresolved_probability": 0.05,
        },
        {
            "near_optimal": True, "receiver_idx": 1, "softmax_weight": 0.5,
            "distance_m": 12.0, "target_kind": "space", "is_long": True,
            "target": [-12.0, 0.0],
            "receiver_offset_m": 5.0, "retention_probability": 0.7,
            "option_duration_seconds": 2.0, "retained_control_probability": 0.7,
            "opposing_control_probability": 0.1, "unresolved_probability": 0.2,
        },
        {
            "near_optimal": True, "receiver_idx": 2, "softmax_weight": 1.0,
            "distance_m": 18.0, "target_kind": "feet", "is_long": False,
            "target": [18.0, 0.0],
            "receiver_offset_m": 1.0, "retention_probability": 0.8,
            "option_duration_seconds": 2.0, "retained_control_probability": 0.8,
            "opposing_control_probability": 0.1, "unresolved_probability": 0.1,
        },
    ], origin=[0.0, 0.0], attacking_right=True, goalkeeper_idx=1)

    assert distribution is not None
    assert distribution["near_optimal_targets"] == 3.0
    assert distribution["near_optimal_receivers"] == 2.0
    assert abs(distribution["flat_expected_within_10m_feet"] - 0.4) < 1e-12
    assert distribution["hierarchical_expected_goalkeeper"] < distribution[
        "flat_expected_goalkeeper"
    ]
    assert distribution["hierarchical_expected_long_backward_goalkeeper"] < distribution[
        "flat_expected_long_backward_goalkeeper"
    ]
    assert abs(distribution["hierarchical_expected_within_10m_feet"] - 1.0 / 3.0) < 1e-12
    assert distribution["candidate_probability_total_variation"] > 0.0


def test_controller_handoff_requires_all_existing_semantic_gates() -> None:
    task = {
        "intent": "support",
        "phase": "active",
        "accepted_tick": 8,
        "expires_tick": 20,
        "spatial_claim": {
            "active": True,
            "origin": [20.0, 30.0],
            "target": [36.0, 30.0],
            "occupancy_radius": 4.5,
            "corridor_half_width": 2.2,
            "depth_band": 1,
            "width_band": 0,
        },
    }
    candidate_claim = {
        **task["spatial_claim"],
        "origin": [18.0, 30.0],
    }
    release = {
        "replay_id": 7,
        "passer_player": 2,
        "target_player": 5,
    }
    receipt = {
        "replay_id": 7,
        "tick": 12,
        "player_idx": 5,
        "winner_is_intended_receiver": True,
        "winner_pos": [40.0, 30.0],
        "actual_receipt_outfield_teammates": [
            {"idx": 2, "distance_to_receiver_m": 14.0},
            {"idx": 3, "distance_to_receiver_m": 12.0},
        ],
    }
    first_flight = {
        "controller_handoff_counterfactual": {
            "eligible": True,
            "passer_idx": 2,
            "receiver_idx": 5,
            "receiver_task_identity_stable_since_release": True,
            "responsibility_task": task,
            "responsibility_effective_target": [36.0, 30.0],
            "projected_receipt_pos": [33.0, 30.0],
            "projected_distance_covered_m": 4.0,
        }
    }
    passer_decision = {
        "controller_handoff_candidate": {
            "replay_id": 7,
            "passer_idx": 2,
            "receiver_idx": 5,
            "identity_stable": True,
            "responsibility_active_at_release": True,
            "responsibility_intent_eligible": True,
            "responsibility_task": task,
            "candidate_base_score": 0.20,
            "local_best_base_score": 0.30,
            "candidate_claim": candidate_claim,
            "task_acceptance": {
                "accepted": True,
                "candidate_value": 0.18,
                "retained_value": 0.12,
            },
        }
    }
    receipt_state = {
        "supporters": [
            {
                "idx": 3,
                "is_goalkeeper": False,
                "task_active": True,
                "task_spatial_claim": {
                    "active": True,
                    "origin": [20.0, 50.0],
                    "target": [55.0, 50.0],
                    "occupancy_radius": 4.5,
                    "corridor_half_width": 2.2,
                    "depth_band": 1,
                    "width_band": 0,
                },
            }
        ]
    }

    result = _controller_handoff_receipt_upper_bound(
        release=release,
        receipt=receipt,
        first_flight=first_flight,
        receipt_state=receipt_state,
        passer_decision=passer_decision,
    )

    assert result["all_gates"] is True
    assert result["clears_local_floor"] is True
    assert result["conflict_free"] is True
    assert result["baseline_nearest_m"] == 12.0
    assert result["projected_nearest_m"] == 7.0
    assert result["creates_within_10m"] is True


def test_controller_handoff_rejects_conflicting_final_assignment() -> None:
    task = {
        "intent": "receive",
        "phase": "active",
        "expires_tick": 15,
        "spatial_claim": {
            "active": True,
            "origin": [20.0, 30.0],
            "target": [36.0, 30.0],
            "occupancy_radius": 4.5,
            "corridor_half_width": 2.2,
            "depth_band": 1,
            "width_band": 0,
        },
    }
    claim = {**task["spatial_claim"], "origin": [18.0, 30.0]}
    result = _controller_handoff_receipt_upper_bound(
        release={"passer_player": 2, "target_player": 5},
        receipt={
            "replay_id": 9,
            "tick": 12,
            "player_idx": 5,
            "winner_is_intended_receiver": True,
            "winner_pos": [40.0, 30.0],
            "actual_receipt_outfield_teammates": [
                {"idx": 2, "distance_to_receiver_m": 14.0}
            ],
        },
        first_flight={
            "controller_handoff_counterfactual": {
                "eligible": True, "passer_idx": 2, "receiver_idx": 5,
                "receiver_task_identity_stable_since_release": True,
                "responsibility_task": task,
                "responsibility_effective_target": [36.0, 30.0],
                "projected_receipt_pos": [33.0, 30.0],
            }
        },
        receipt_state={
            "supporters": [{
                "idx": 3, "is_goalkeeper": False, "task_active": True,
                "task_spatial_claim": claim,
            }]
        },
        passer_decision={
            "controller_handoff_candidate": {
                "replay_id": 9, "passer_idx": 2, "receiver_idx": 5,
                "identity_stable": True,
                "responsibility_active_at_release": True,
                "responsibility_intent_eligible": True,
                "responsibility_task": task,
                "candidate_base_score": 0.20,
                "local_best_base_score": 0.30,
                "candidate_claim": claim,
                "task_acceptance": {"accepted": True},
            }
        },
    )

    assert result["conflict_free"] is False
    assert result["conflicting_teammates"] == [3]
    assert result["all_gates"] is False


def test_pass_successor_support_alternative_ledger_compares_same_value_fields() -> None:
    def candidate(score: float, nearest: float, distance: float) -> dict:
        return {
            "action_type": "pass",
            "target": [distance, 0.0],
            "value": {
                "score": score,
                "components": {
                    "after_value": score + 0.01,
                    "option_return": score - 0.01,
                    "local_shaping": 0.01,
                    "temporal_discount": 0.90,
                    "turnover_cost": 0.02,
                    "outcome_transition": {
                        "retained_control_probability": 0.8,
                        "retained_control_value": score + 0.01,
                        "opposing_control_probability": 0.1,
                        "opposing_control_value": 0.03,
                        "goal_probability": 0.0,
                    },
                    "projected_retained_state": {
                        "nearest_outfield_teammate_distance": nearest,
                        "control_residual": 0.02,
                        "outlet_access": 0.4,
                        "structure": 0.6,
                    },
                },
            },
        }

    report = _pass_successor_support_alternative_ledger({
        "phase": "on_ball",
        "pos": [0.0, 0.0],
        "chosen": candidate(0.50, 14.0, 18.0),
        "alternatives": [
            candidate(0.48, 8.0, 9.0),
            candidate(0.44, 11.0, 15.0),
            {"action_type": "carry", "value": {"score": 0.60}},
        ],
    })

    assert report["pass_candidate_count"] == 3
    assert report["closer_successor_candidate_count"] == 2
    assert report["under_10m_successor_candidate_count"] == 1
    assert report["best_closer_successor"]["score_minus_chosen"] == pytest.approx(-0.02)
    assert report["best_under_10m_successor"]["nearest_support_delta_m"] == -6.0
    assert report["best_under_10m_successor"]["bellman_decomposition"][
        "continuation_probability_effect"
    ] == 0.0
    assert report["best_under_10m_successor"]["bellman_decomposition"][
        "score_option_return_effect"
    ] == pytest.approx(-0.02)
    assert report["best_under_10m_successor"]["bellman_decomposition"][
        "score_local_shaping_effect"
    ] == 0.0


def test_high_pressure_support_gap_episode_summary_classifies_physical_crossings() -> None:
    def state(
        tick: int,
        holder: int,
        opponent_distance: float,
        support_distance: float,
    ) -> dict:
        return {
            "event": "held_support_state",
            "tick": tick,
            "possession_id": 7,
            "team": "home",
            "holder_idx": holder,
            "holder_pos": [0.0, 0.0],
            "nearest_opponent_distance_m": opponent_distance,
            "supporters": [{
                "idx": 3,
                "is_goalkeeper": False,
                "pos": [support_distance, 0.0],
            }],
        }

    report = _high_pressure_support_gap_episode_summary([
        state(1, 2, 3.0, 11.0),
        state(2, 2, 1.5, 11.2),
        {
            "event": "pass_control_terminal",
            "tick": 3,
            "winner_team": "home",
            "winner_player": 4,
            "possession_retained": True,
            "winner_is_intended_receiver": True,
        },
        state(3, 4, 1.2, 12.0),
        state(4, 4, 3.0, 9.0),
        state(5, 4, 1.0, 10.5),
    ])

    assert report["counts"] == {
        "cause=controller_handoff": 1,
        "cause=joint_crossing": 1,
        "cause=pressure_crossing": 1,
        "acquisition_source=intended_pass_receipt": 2,
        "acquisition_source=unknown": 1,
        "gap_episode_entries": 3,
    }
    assert [case["cause"] for case in report["cases"]] == [
        "pressure_crossing",
        "controller_handoff",
        "joint_crossing",
    ]


def test_support_responsibility_identity_continuity_separates_owner_from_nearest() -> None:
    def state(
        tick: int,
        pressure_distance: float,
        first_pos: float,
        first_target: float,
        second_pos: float,
        second_target: float,
    ) -> dict:
        def supporter(idx: int, pos: float, target: float) -> dict:
            return {
                "idx": idx,
                "is_goalkeeper": False,
                "pos": [pos, 0.0],
                "effective_target": [target, 0.0],
                "task_active": True,
                "task_intent": "Support",
                "task_accepted_tick": tick,
            }

        return {
            "event": "held_support_state",
            "tick": tick,
            "possession_id": 9,
            "team": "home",
            "holder_idx": 4,
            "holder_pos": [0.0, 0.0],
            "nearest_opponent_distance_m": pressure_distance,
            "supporters": [
                supporter(1, first_pos, first_target),
                supporter(2, second_pos, second_target),
            ],
        }

    report = _support_responsibility_identity_continuity_summary([
        state(1, 3.0, 7.0, 5.0, 9.0, 8.0),
        state(2, 1.0, 6.0, 7.0, 8.0, 4.0),
        state(3, 1.0, 5.0, 8.0, 9.0, 3.0),
    ])

    high_pressure = report["by_pressure"]["0_2m"]
    assert high_pressure["counts"] == {
        "changed_previous_owner_physically_closer": 1,
        "changed_previous_owner_less_remaining_move": 1,
        "changed_previous_owner_still_active": 1,
        "consecutive_physical_ticks": 2,
        "physical_nearest_identity_stable": 2,
        "responsibility_differs_from_physical_nearest": 2,
        "responsibility_identity_changed": 1,
        "responsibility_identity_stable": 1,
        "responsibility_target_within_10m": 2,
    }
    assert (
        high_pressure["metrics"][
            "changed_new_minus_previous_target_distance_m"
        ]["median"]
        == -3.0
    )
    assert (
        high_pressure["metrics"][
            "changed_new_minus_previous_player_distance_m"
        ]["median"]
        == 2.0
    )
    assert (
        high_pressure["metrics"][
            "changed_new_minus_previous_remaining_move_m"
        ]["median"]
        == 3.0
    )
    assert high_pressure["metrics"]["physical_nearest_distance_m"]["median"] == 5.5


def test_optimistic_outlet_resource_candidate_prices_team_capacity_against_local_cost() -> None:
    result = _optimistic_outlet_resource_candidate(
        {
            "target": [6.0, 8.0],
            "base_score": 0.30,
            "local_best_base_score": 0.50,
            "to_local_best_ratio": 0.60,
            "components": {
                "support_angle_value": 0.80,
                "immediate_reach": 0.50,
                "pass_feasibility": 0.75,
            },
        },
        [0.0, 0.0],
        {"zero_outlet": 0.10, "full_outlet": 0.90},
        turnover_avoidance_value=0.05,
    )

    assert result == pytest.approx({
        "target_distance_m": 10.0,
        "base_score": 0.30,
        "local_best_base_score": 0.50,
        "to_local_best_ratio": 0.60,
        "outlet_coverage": 0.30,
        "endpoint_capacity": 0.80,
        "local_value_cost": 0.20,
        "optimistic_team_value": 0.24,
        "optimistic_net_team_value": 0.04,
        "turnover_avoidance_value": 0.05,
        "turnover_avoidance_net_team_value": 0.09,
    })


def test_optimistic_outlet_resource_candidate_requires_a_complete_value_ledger() -> None:
    assert _optimistic_outlet_resource_candidate(
        {"target": [5.0, 0.0], "base_score": 0.2},
        [0.0, 0.0],
        {"zero_outlet": 0.1, "full_outlet": 0.2},
    ) is None


def test_continuous_connection_redundancy_rewards_independent_outlets() -> None:
    holder = (0.0, 0.0)
    collinear = _continuous_connection_redundancy(holder, [
        {"target": (10.0, 0.0), "value": 1.0, "projected_outlet_access": 1.0},
        {"target": (-10.0, 0.0), "value": 1.0, "projected_outlet_access": 1.0},
    ])
    orthogonal = _continuous_connection_redundancy(holder, [
        {"target": (10.0, 0.0), "value": 1.0, "projected_outlet_access": 1.0},
        {"target": (0.0, 10.0), "value": 1.0, "projected_outlet_access": 1.0},
    ])

    assert abs(collinear["connection_redundancy"]) < 1e-12
    assert abs(orthogonal["connection_redundancy"] - 1.0) < 1e-12
    assert abs(orthogonal["connection_isotropy"] - 1.0) < 1e-12


def test_continuous_triangle_closure_requires_three_connected_edges() -> None:
    holder = (0.0, 0.0)
    candidates = [
        {"target": (10.0, 0.0), "value": 1.0, "projected_outlet_access": 1.0},
        {"target": (0.0, 10.0), "value": 1.0, "projected_outlet_access": 1.0},
    ]
    disconnected = [
        candidates[0],
        {"target": (0.0, 60.0), "value": 1.0, "projected_outlet_access": 1.0},
    ]

    assert _continuous_triangle_closure(holder, candidates) > 0.0
    assert _continuous_triangle_closure(holder, disconnected) == 0.0


def test_rigid_translation_preserves_shape_and_exposes_slot_spacing() -> None:
    geometry = _rigid_translation_geometry(
        (14.0, 8.0),
        (10.0, 10.0),
        [(20.0, 10.0), (10.0, 20.0), (30.0, 20.0)],
    )

    assert abs(geometry["translation_m"] - 20 ** 0.5) < 1e-12
    assert geometry["formation_debt_m"] == geometry["translation_m"]
    assert geometry["translated_nearest_m"] == 10.0
    assert geometry["baseline_width_m"] == geometry["translated_width_m"]
    assert geometry["baseline_depth_m"] == geometry["translated_depth_m"]
    assert geometry["maximum_pairwise_distance_drift_m"] < 1e-12


def test_balanced_formation_graph_elasticity_preserves_global_frame() -> None:
    points = [(0.0, 0.0), (10.0, 0.0), (20.0, 8.0), (30.0, 20.0)]
    geometry = _balanced_formation_graph_elasticity(points, (8.0, 4.0), 0.7)

    assert geometry["centroid_drift_m"] < 1e-12
    assert abs(geometry["depth_drift_m"]) < 1e-12
    assert abs(geometry["width_drift_m"]) < 1e-12
    assert geometry["minimum_pair_separation_m"] > 0.0


def test_targeted_formation_graph_elasticity_selects_the_closest_continuous_state() -> None:
    geometry = _targeted_formation_graph_elasticity(
        [(0.0, 0.0), (12.0, 0.0), (24.0, 8.0), (32.0, 20.0)],
        (8.0, 4.0),
        6.0,
    )

    assert 0.0 <= geometry["demand"] <= 1.0
    assert abs(geometry["target_error_m"]) <= abs(
        geometry["root_baseline_distance_m"] - geometry["target_nearest_m"]
    )


def test_continuous_coordination_optimum_can_improve_redundancy_without_local_cost() -> None:
    def candidate(player: int, index: int, target: tuple[float, float]) -> dict:
        return {
            "player_idx": player,
            "candidate_index": index,
            "target": target,
            "value": 1.0,
            "projected_outlet_access": 1.0,
            "active": False,
        }

    pool = {
        1: {
            "assigned_index": 0,
            "candidates": [candidate(1, 0, (10.0, 0.0))],
        },
        2: {
            "assigned_index": 0,
            "candidates": [
                candidate(2, 0, (-10.0, 0.0)),
                candidate(2, 1, (0.0, 10.0)),
            ],
        },
    }
    optima = _continuous_coordination_optima(
        (0.0, 0.0), pool, lambda _left, _right: "clear"
    )

    assert optima["baseline"]["connection_redundancy"] == 0.0
    noninferior = optima["best_combined_local_noninferior"]
    assert noninferior["local_value"] == optima["baseline"]["local_value"]
    assert abs(noninferior["connection_redundancy"] - 1.0) < 1e-12
    assert noninferior["candidate_indices"] == [0, 1]
    redundancy_upper_bound = optima["best_redundancy_local_noninferior"]
    assert redundancy_upper_bound["local_value"] == optima["baseline"]["local_value"]
    assert abs(redundancy_upper_bound["connection_redundancy"] - 1.0) < 1e-12
    closure_upper_bound = optima["best_closure_local_noninferior"]
    assert closure_upper_bound["local_value"] == optima["baseline"]["local_value"]
    assert closure_upper_bound["triangle_closure"] > 0.0


def test_retarget_displacement_exactly_replays_the_selected_direction() -> None:
    displacement = _retarget_displacement_preserving_motion_components(
        (0.0, 0.0),
        (10.0, 0.0),
        (2.0, 1.0),
        (10.0, 0.0),
    )

    assert displacement == (2.0, 1.0)


def test_retarget_displacement_rotates_along_and_cross_components() -> None:
    displacement = _retarget_displacement_preserving_motion_components(
        (0.0, 0.0),
        (10.0, 0.0),
        (2.0, 1.0),
        (0.0, 10.0),
    )

    assert displacement == (-1.0, 2.0)


def test_trace_settled_probability_is_cumulative_over_direct_mass() -> None:
    direct_retained = 0.42
    direct_opposing = 0.18
    traced_settled_retained = 0.67
    traced_settled_opposing = 0.29

    assert abs(_additional_settlement_mass(
        traced_settled_retained, direct_retained
    ) - 0.25) < 1e-12
    assert abs(_additional_settlement_mass(
        traced_settled_opposing, direct_opposing
    ) - 0.11) < 1e-12


def test_pressure_projection_summary_closes_under_four_classification() -> None:
    counts = Counter(
        {
            "terminal:true_positive": 3,
            "terminal:false_positive": 1,
            "terminal:false_negative": 1,
            "terminal:true_negative": 5,
            "closest:true_positive": 4,
            "closest:false_positive": 2,
            "closest:false_negative": 0,
            "closest:true_negative": 4,
        }
    )
    metrics = defaultdict(
        list,
        {"terminal_absolute_error_m": [0.5, 1.5]},
    )

    summary = _pressure_projection_scope_summary(counts, metrics)

    terminal = summary["under_4m_classification"]["terminal"]
    assert terminal == {
        "true_positive": 3,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 5,
        "precision": 0.75,
        "recall": 0.75,
        "specificity": round(5 / 6, 6),
    }
    assert summary["metrics"]["terminal_absolute_error_m"]["median"] == 1.0


def test_prospective_carrier_engagement_rewards_visible_flight_convergence() -> None:
    near = _prospective_carrier_engagement_coverage(
        "approach", 4.0, 0.8, 0.3, 12.0, 6.0
    )
    far = _prospective_carrier_engagement_coverage(
        "approach", 14.0, 0.8, 0.3, 12.0, 6.0
    )

    assert near > far


def test_candidate_motion_extension_stops_at_the_existing_target() -> None:
    assert _extend_candidate_motion_to_horizon(
        (0.0, 0.0), (2.0, 0.0), (5.0, 0.0), 2.0
    ) == (4.0, 0.0)
    assert _extend_candidate_motion_to_horizon(
        (0.0, 0.0), (2.0, 0.0), (5.0, 0.0), 4.0
    ) == (5.0, 0.0)


def test_restart_lifecycle_accepts_out_of_play_as_the_restart_award() -> None:
    events = [
        {**_event("pass", "out_of_play", "away", ["corner"]), "seq": 1},
        {
            **_event(
                "pass",
                "intercepted",
                "home",
                ["long", "aerial", "corner_origin"],
            ),
            "seq": 2,
        },
    ]

    lifecycle = _restart_release_lifecycle(events)

    assert lifecycle["resolved"] == {"corner": 1}
    assert lifecycle["orphaned_count"] == 0
    assert lifecycle["stray_release_count"] == 0


def test_corner_aerial_cross_is_excluded_from_provider_long_balls() -> None:
    events = [
        _event(
            "pass",
            "completed",
            "home",
            ["long", "aerial", "cross", "corner_origin"],
        )
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 1, "passes_completed": 1},
        {"passes": 0, "passes_completed": 0},
    )

    assert summary["breakdown"]["by_length"]["long"]["attempted"] == 1
    assert "long" not in summary["breakdown"]["by_provider_pass_scope_length"]
    assert summary["breakdown"]["by_provider_pass_scope_distance"] == {}
    assert summary["breakdown"]["by_restart_origin"]["corner"]["attempted"] == 1
    assert summary["breakdown"]["by_provider_pass_scope_restart_origin"] == {}


def test_provider_distance_bands_close_to_the_non_cross_pass_scope() -> None:
    events = [
        _event("pass", "completed", "home", ["short", "feet", "distance_0_10"]),
        _event("pass", "completed", "home", ["short", "feet", "distance_10_20"]),
        _event(
            "pass",
            "completed",
            "home",
            ["long", "aerial", "cross", "distance_30_plus"],
        ),
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 3, "passes_completed": 3},
        {"passes": 0, "passes_completed": 0},
    )

    provider = summary["breakdown"]["by_provider_pass_scope_distance"]
    assert sum(bucket["attempted"] for bucket in provider.values()) == 2
    assert sum(bucket["completed"] for bucket in provider.values()) == 2
    assert provider["0-10m"]["attempted"] == 1
    assert provider["10-20m"]["attempted"] == 1
    assert "30m+" not in provider


def test_aggregate_pass_partitions_keep_provider_distance_in_non_cross_scope() -> None:
    pass_breakdowns = {
        "by_length": {
            "short": {"attempted": 8, "completed": 7},
            "long": {"attempted": 2, "completed": 1},
        },
        "by_provider_pass_scope_length": {
            "short": {"attempted": 8, "completed": 7},
            "long": {"attempted": 1, "completed": 0},
        },
        "by_provider_pass_scope_distance": {
            "0-10m": {"attempted": 2, "completed": 2},
            "10-20m": {"attempted": 7, "completed": 5},
        },
        "read_only_subset_diagnostic": {
            "observed": {"attempted": 3, "completed": 2},
        },
    }

    _, checks = _pass_breakdown_scope_integrity_checks(
        pass_breakdowns,
        total_pass_attempts=10,
        total_pass_completions=8,
        total_cross_attempts=1,
        total_completed_crosses=1,
    )

    assert all(checks.values())


def test_aggregate_pass_partitions_reject_bad_provider_distance_closure() -> None:
    pass_breakdowns = {
        "by_length": {
            "short": {"attempted": 8, "completed": 7},
            "long": {"attempted": 2, "completed": 1},
        },
        "by_provider_pass_scope_length": {
            "short": {"attempted": 8, "completed": 7},
            "long": {"attempted": 1, "completed": 0},
        },
        "by_provider_pass_scope_distance": {
            "0-10m": {"attempted": 10, "completed": 7},
        },
    }

    _, checks = _pass_breakdown_scope_integrity_checks(
        pass_breakdowns,
        total_pass_attempts=10,
        total_pass_completions=8,
        total_cross_attempts=1,
        total_completed_crosses=1,
    )

    assert checks["pass_breakdowns_partition_attempts"] is True
    assert checks["pass_breakdowns_partition_completions"] is True
    assert checks["provider_scope_length_excludes_cross_attempts"] is True
    assert checks["provider_scope_length_excludes_completed_crosses"] is True
    assert checks["provider_scope_distance_excludes_cross_attempts"] is False
    assert checks["provider_scope_distance_excludes_completed_crosses"] is True


def test_provider_passes_are_split_by_passer_ability_without_losing_interceptions() -> None:
    completed = {
        **_event("pass", "completed", "home", ["long", "feet"]),
        "player": {"player_id": 101, "position": "CM"},
        "target": [55.0, 30.0],
    }
    intercepted = {
        **_event("interception", "won", "away", ["long", "feet", "pass_cut_out"]),
        "player": {"player_id": 202, "position": "CB"},
        "target_player": {"player_id": 101, "position": "CM"},
        "target": [65.0, 30.0],
    }

    summary = _pass_causality_summary(
        [completed, intercepted],
        {"passes": 2, "passes_completed": 1},
        {"passes": 0, "passes_completed": 0},
        {("home", "101"): (88.0, 86.0)},
    )

    by_long_ability = summary["breakdown"][
        "by_provider_length_and_long_passing_band"
    ]["long:85_plus"]
    assert by_long_ability["attempted"] == 2
    assert by_long_ability["completed"] == 1
    assert by_long_ability["outcomes"] == {"completed": 1, "intercepted": 1}
    assert sum(
        bucket["attempted"]
        for bucket in summary["breakdown"][
            "provider_long_by_passer_ability_profile"
        ].values()
    ) == 2


def test_fine_long_pass_breakdowns_are_documented_subsets() -> None:
    events = [
        _event("pass", "completed", "home", ["short", "feet"]),
        {
            **_event("pass", "completed", "home", ["long", "feet"]),
            "target": [60.0, 30.0],
        },
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 2, "passes_completed": 2},
        {"passes": 0, "passes_completed": 0},
    )

    breakdown = summary["breakdown"]
    assert sum(bucket["attempted"] for bucket in breakdown["by_length"].values()) == 2
    assert (
        sum(bucket["attempted"] for bucket in breakdown["long_fine_breakdown"].values())
        == 1
    )
    assert (
        sum(
            bucket["attempted"]
            for bucket in breakdown["provider_long_fine_breakdown"].values()
        )
        == 1
    )


def test_restart_lifecycle_merges_matching_explicit_restart_after_out_of_play_award() -> None:
    events = [
        {
            **_event("loose_ball", "out_of_play", "home", ["goal_kick"]),
            "seq": 1,
        },
        {**_event("restart", "goal_kick", "away", ["set_piece"]), "seq": 2},
        {
            **_event("pass", "completed", "away", ["goal_kick_origin"]),
            "seq": 3,
        },
    ]

    lifecycle = _restart_release_lifecycle(events)

    assert lifecycle["resolved"] == {"goal_kick": 1}
    assert lifecycle["orphaned_count"] == 0
    assert lifecycle["stray_release_count"] == 0


def test_restart_lifecycle_lets_explicit_restart_correct_inferred_team() -> None:
    events = [
        {
            **_event("pass", "out_of_play", "home", ["corner"]),
            "seq": 1,
        },
        {**_event("restart", "corner", "home", ["set_piece"]), "seq": 2},
        {
            **_event("pass", "completed", "home", ["corner_origin"]),
            "seq": 3,
        },
    ]

    lifecycle = _restart_release_lifecycle(events)

    assert lifecycle["resolved"] == {"corner": 1}
    assert lifecycle["orphaned_count"] == 0
    assert lifecycle["stray_release_count"] == 0


def test_restart_lifecycle_resolves_old_release_before_awarding_new_restart() -> None:
    events = [
        {**_event("restart", "free_kick", "away", ["set_piece"]), "seq": 1},
        {
            **_event(
                "pass",
                "out_of_play",
                "away",
                ["free_kick_origin", "corner"],
            ),
            "seq": 2,
        },
        {
            **_event("pass", "completed", "home", ["corner_origin"]),
            "seq": 3,
        },
    ]

    lifecycle = _restart_release_lifecycle(events)

    assert lifecycle["resolved"] == {"corner": 1, "free_kick": 1}
    assert lifecycle["orphaned_count"] == 0
    assert lifecycle["stray_release_count"] == 0


def test_restart_lifecycle_infers_goal_kick_award_from_off_target_shot() -> None:
    events = [
        {**_event("shot", "off_target", "home", ["outside_box"]), "seq": 1},
        {
            **_event("pass", "completed", "away", ["goal_kick_origin"]),
            "seq": 2,
        },
    ]

    lifecycle = _restart_release_lifecycle(events)

    assert lifecycle["resolved"] == {"goal_kick": 1}
    assert lifecycle["orphaned_count"] == 0
    assert lifecycle["stray_release_count"] == 0


def test_restart_lifecycle_marks_unreleased_half_end_award_as_censored() -> None:
    events = [
        {
            **_event("shot", "off_target", "home", ["outside_box"]),
            "seq": 1,
            "half": 1,
        },
        {**_event("carry", "completed", "away"), "seq": 2, "half": 2},
    ]

    lifecycle = _restart_release_lifecycle(events)

    assert lifecycle["resolved"] == {}
    assert lifecycle["orphaned_count"] == 1
    assert lifecycle["orphaned"][0]["outcome"] == "goal_kick"
    assert lifecycle["orphaned"][0]["closed_by"] == "period_end"
    assert lifecycle["stray_release_count"] == 0


def test_action_pace_partitions_full_pass_candidate_pool_by_actual_distance() -> None:
    def candidate(
        target: list[float],
        score: float,
        retention: float,
        arrival: float = 0.8,
        lane_risk: float = 0.1,
        receiver_pressure: float = 0.2,
    ) -> dict:
        return {
            "action_type": "pass",
            "target": target,
            "source": "pass",
            "value": {
                "score": score,
                "success_prob": retention,
                "components": {
                    "base_accuracy": retention,
                    "receiver_arrival": arrival,
                    "lane_risk": lane_risk,
                    "receiver_pressure": receiver_pressure,
                    "after_value": score + 0.01,
                },
            },
        }

    summary = _action_pace_summary(
        {
            "trace": {
                "detail": "full",
                "decisions": [
                    {
                        "phase": "on_ball",
                        "player_idx": 0,
                        "pos": [0.0, 0.0],
                        "control": {"pressure_load": 0.75},
                        "chosen": candidate([10.0, 0.0], 0.6, 0.9),
                        "alternatives": [
                            candidate([32.0, 0.0], 0.5, 0.4, 0.35, 0.55, 0.65),
                            candidate([40.0, 0.0], 0.4, 0.3),
                        ],
                    }
                ],
                "entries": [],
            },
            "events": [],
        }
    )

    pool = summary["pass_candidate_selection"]
    assert pool["complete_candidate_pool"] is True
    assert pool["by_length"]["short"]["candidate_observations"] == 1
    assert pool["by_length"]["short"]["selected"] == 1
    assert pool["by_length"]["long"]["candidate_observations"] == 2
    assert pool["by_length"]["long"]["selected"] == 0
    assert pool["by_length"]["long"]["predicted_retention"]["mean"] == 0.35
    assert pool["best_long_minus_best_short_value"]["median"] == -0.1
    pass_choice = pool["best_pass_vs_chosen_action"]
    assert pass_choice["counts"]["pass_selected"] == 1
    goalkeeper = pool["goalkeeper"]
    assert goalkeeper["decisions_with_both_lengths"] == 1
    assert goalkeeper["best_candidate_means"]["long_base_accuracy"] == 0.4
    assert goalkeeper["best_candidate_means"]["long_receiver_arrival"] == 0.35
    assert goalkeeper["best_candidate_means"]["long_lane_risk"] == 0.55
    assert goalkeeper["best_candidate_means"]["long_receiver_pressure"] == 0.65
    pressured_long = pool["long_candidate_by_pressure_and_chosen_action"][
        "high:chosen=pass"
    ]
    assert pressured_long["minus_chosen"]["count"] == 1
    assert pressured_long["minus_chosen"]["mean"] == -0.1


def test_switch_pass_policy_decomposition_reconstructs_production_score_and_pair() -> None:
    signals = {
        "forward_bias": 0.32,
        "recycle_bias": 0.66,
        "switch_bias": 0.96,
        "risk_budget": 0.46,
    }

    def candidate(target: list[float], success: float, risk: float) -> dict:
        provisional = {
            "action_type": "pass",
            "target": target,
            "value": {
                "score": 0.0,
                "success_prob": success,
                "components": {
                    "option_return": 0.015,
                    "local_shaping": 0.0,
                    "current_value": 0.02,
                    "lane_risk": risk,
                },
            },
        }
        decomposition = _team_plan_pass_policy_decomposition(
            provisional,
            [50.0, 10.0],
            attacking_right=True,
            signals=signals,
        )
        assert decomposition is not None
        provisional["value"]["components"]["local_shaping"] = decomposition[
            "team_plan_policy_value"
        ]
        provisional["value"]["score"] = decomposition["team_plan_only_score"]
        return provisional

    backward = _team_plan_pass_policy_decomposition(
        candidate([15.0, 10.0], 0.90, 0.10),
        [50.0, 10.0],
        attacking_right=True,
        signals=signals,
    )
    lateral = _team_plan_pass_policy_decomposition(
        candidate([50.0, 58.0], 0.82, 0.16),
        [50.0, 10.0],
        attacking_right=True,
        signals=signals,
    )

    assert backward is not None and lateral is not None
    assert backward["retention"] == pytest.approx(0.81)
    assert backward["forward_alignment"] == 0.0
    assert backward["recycle_alignment"] == pytest.approx(0.30 * 0.66 * 0.81)
    assert backward["switch_alignment"] == 0.0
    assert backward["post_team_plan_goal_policy_residual"] == pytest.approx(0.0)
    assert backward["team_plan_only_score_residual"] == pytest.approx(0.0)
    assert lateral["switch_alignment"] > 0.0

    pair = _team_plan_policy_pair_decomposition(backward, lateral)
    assert pair["production_score_delta"] == pytest.approx(
        backward["production_score"] - lateral["production_score"]
    )
    assert pair["score_decomposition_error"] == pytest.approx(0.0, abs=1e-15)
    assert pair["policy_delta_reconstruction_error"] == pytest.approx(
        0.0, abs=1e-15
    )


def test_outcome_distinguishability_counterfactual_preserves_probability_mass() -> None:
    def candidate(
        action_type: str, score: float, retained: float, opposing: float, target_x: float
    ) -> dict:
        return {
            "action_type": action_type,
            "target": [target_x, 0.0],
            "value": {
                "score": score,
                "success_prob": retained,
                "components": {
                    "outcome_transition": {
                        "goal_probability": 0.0,
                        "retained_control_probability": retained,
                        "opposing_control_probability": opposing,
                    }
                },
            },
        }

    decision = {
        "pos": [0.0, 0.0],
        "attacking_right": True,
        "chosen": candidate("pass", 0.020, 0.70, 0.05, 35.0),
        "alternatives": [
            candidate("pass", 0.019, 0.86, 0.02, 12.0),
            candidate("carry", 0.018, 0.90, 0.02, 4.0),
        ],
        "bounded_rational_selection": {
            "iq": 75.0,
            "pressure": 0.4,
            "fatigue": 0.2,
        },
    }

    result = _outcome_distinguishability_selection_counterfactual(decision)

    assert result is not None
    for ledger in ("production", "raw"):
        assert sum(
            result[f"{ledger}_action_{action}_probability"]
            for action in ("carry", "pass", "shoot", "hold", "reorient", "clear")
        ) == pytest.approx(1.0)
        assert 0.0 <= result[f"{ledger}_provider_long_share_given_pass"] <= 1.0


def test_single_aerial_distribution_admission_summary_separates_both_selector_stages() -> None:
    response = {
        "trace": {
            "entries": [
                {
                    "event": "single_aerial_distribution_admission_counterfactual",
                    "tick": 42,
                    "team": "home",
                    "player_idx": 6,
                    "player_position": "CM",
                    "profile": "visual_velocity",
                    "option": {
                        "receiver_idx": 9,
                        "distance_m": 36.0,
                        "progress_m": 31.0,
                        "is_long": True,
                        "temporal_score_before_goal_policy": 0.018,
                        "policy_valued_score": 0.020,
                    },
                    "admission": {
                        "option": {
                            "raw_score": 0.020,
                            "raw_score_gap_to_actual_best": -0.004,
                            "adjusted_score": 0.017,
                            "near_optimal": True,
                            "conditional_pass_family_probability": 0.25,
                            "overall_selection_probability": 0.10,
                            "retained_control_probability": 0.54,
                            "opposing_control_probability": 0.31,
                            "unresolved_probability": 0.15,
                        },
                        "pass_candidate_stage": {
                            "current_candidate_count": 8,
                            "current_near_optimal_count": 3,
                            "counterfactual_near_optimal_count": 4,
                            "ground_probability_mass_after": 0.75,
                            "current_near_ground_probability_mass_after": 0.75,
                            "current_near_ground_probability_mass_displaced": 0.25,
                            "excluded_current_near_ground_count": 0,
                        },
                        "family_stage": {
                            "counterfactual_pass_near_optimal": True,
                            "current_pass_probability": 0.35,
                            "counterfactual_pass_probability": 0.40,
                            "current_ground_overall_probability": 0.35,
                            "counterfactual_ground_overall_probability": 0.30,
                            "ground_overall_probability_displaced": 0.05,
                        },
                    },
                }
            ]
        }
    }

    summary = _aerial_distribution_intent_counterfactual_summary(response)

    assert summary["counts"]["outfield_admitted_within_pass_family"] == 1
    assert summary["counts"]["outfield_pass_family_admitted_after_option"] == 1
    assert summary["counts"]["outfield_selectable_overall"] == 1
    assert summary["counts"]["outfield_raw_score_below_actual_best"] == 1
    assert summary["counts"]["outfield_admission_delivery=long_decisions"] == 1
    assert summary["counts"]["outfield_admission_direction=forward_selectable_overall"] == 1
    assert summary["counts"][
        "outfield_admission_profile=visual_velocity_selectable_overall"
    ] == 1
    assert summary["counts"][
        "outfield_admission_profile=visual_velocity:delivery=long_decisions"
    ] == 1
    assert summary["metrics"][
        "outfield_admission_option_overall_selection_probability"
    ]["mean"] == pytest.approx(0.10)
    assert summary["admission_cases"][0]["selectable_overall"] is True


def test_safe_near_feet_ledger_decomposes_chosen_winners_by_epl_distance() -> None:
    def action(
        action_type: str,
        target_x: float,
        retained_probability: float,
        retained_value: float,
        terminal_return: float,
        turnover_cost: float,
        temporal_discount: float,
        local_shaping: float,
        *,
        safe: bool = False,
    ) -> dict:
        continuation_return = retained_probability * retained_value
        option_return = temporal_discount * (
            continuation_return + terminal_return - turnover_cost
        )
        return {
            "action_type": action_type,
            "target": [target_x, 0.0],
            "value": {
                "score": option_return + local_shaping,
                "success_prob": 0.9 if safe else retained_probability,
                "components": {
                    "target_kind": "feet",
                    "option_return": option_return,
                    "local_shaping": local_shaping,
                    "temporal_discount": temporal_discount,
                    "turnover_cost": turnover_cost,
                    "outcome_transition": {
                        "retained_control_probability": retained_probability,
                        "retained_control_value": retained_value,
                        "goal_probability": terminal_return,
                    },
                    "projected_retained_state": {
                        "continuation_value": retained_value,
                        "network_time_budget_seconds": (
                            2.0 if target_x < 10.0 else 1.0
                        ),
                        "time_budget_continuation_value": (
                            retained_value - (0.02 if target_x < 10.0 else 0.10)
                        ),
                        "time_budget_continuation_value_delta": (
                            -0.02 if target_x < 10.0 else -0.10
                        ),
                        "control_readiness": retained_probability,
                    },
                },
            },
        }

    safe = action(
        "pass", 8.0, 0.9, 0.4, 0.01, 0.02, 0.95, 0.01, safe=True
    )
    chosen_25m = action(
        "pass", 25.0, 0.8, 0.5, 0.02, 0.01, 0.9, 0.02
    )
    chosen_31m = action(
        "pass", 31.0, 0.85, 0.5, 0.01, 0.01, 0.9, 0.01
    )
    chosen_carry = action(
        "carry", 2.0, 0.85, 0.48, 0.01, 0.01, 0.9, 0.01
    )
    lower_shot = action(
        "shoot", 20.0, 0.4, 0.2, 0.01, 0.05, 0.9, 0.0
    )

    summary = _action_pace_summary({
        "trace": {
            "detail": "full",
            "entries": [],
            "decisions": [
                {
                    "phase": "on_ball",
                    "pos": [0.0, 0.0],
                    "chosen": chosen,
                    "alternatives": [safe],
                }
                for chosen in (chosen_25m, chosen_31m, chosen_carry, lower_shot)
            ],
        },
        "events": [],
    })

    breakdown = summary["pass_candidate_selection"][
        "safe_0_10m_feet_bellman_ledger"
    ]["chosen_equal_or_better_breakdown"]
    assert breakdown["overall"]["decisions"] == 3
    assert breakdown["by_chosen_action"]["pass"]["decisions"] == 2
    assert breakdown["by_chosen_action"]["carry"]["decisions"] == 1
    assert "shoot" not in breakdown["by_chosen_action"]
    assert breakdown["by_chosen_pass_distance"]["20_30m"]["decisions"] == 1
    assert breakdown["by_chosen_pass_distance"]["30m_plus"]["decisions"] == 1

    pass_20_30 = breakdown["by_chosen_pass_distance"]["20_30m"]
    assert pass_20_30["safe_near_feet_minus_chosen_score"]["mean"] == pytest.approx(
        -0.0465
    )
    assert pass_20_30["effects"]["continuation_probability_effect"][
        "mean"
    ] == pytest.approx(0.05)
    assert pass_20_30["effects"]["continuation_state_value_effect"][
        "mean"
    ] == pytest.approx(-0.09)
    assert pass_20_30["effects"]["pre_discount_terminal_effect"][
        "mean"
    ] == pytest.approx(-0.01)
    assert pass_20_30["effects"]["pre_discount_turnover_effect"][
        "mean"
    ] == pytest.approx(-0.01)
    assert pass_20_30["effects"]["temporal_discount_effect"][
        "mean"
    ] == pytest.approx(0.0205)
    assert pass_20_30["effects"]["score_local_shaping_effect"][
        "mean"
    ] == pytest.approx(-0.01)
    assert pass_20_30["retained_state_deltas"]["retained_continuation_value"][
        "mean"
    ] == pytest.approx(-0.1)
    assert pass_20_30["retained_state_deltas"][
        "retained_network_time_budget_seconds"
    ]["mean"] == pytest.approx(1.0)
    assert pass_20_30["retained_state_deltas"][
        "retained_time_budget_continuation_value"
    ]["mean"] == pytest.approx(-0.02)
    assert pass_20_30["retained_state_deltas"][
        "retained_time_budget_continuation_value_delta"
    ]["mean"] == pytest.approx(0.08)
    assert pass_20_30["time_budget_counterfactual"]["counts"] == {
        "comparable_frames": 1,
        "safe_near_feet_becomes_better": 1,
    }
    assert pass_20_30["time_budget_counterfactual"]["metrics"][
        "time_budget_gap_shift_toward_safe"
    ]["mean"] == pytest.approx(0.0549)
    assert pass_20_30["decomposition_checks"][
        "score_decomposition_error"
    ]["mean"] == pytest.approx(0.0)


def test_action_pace_groups_exact_feet_receiver_task_motion_without_inference() -> None:
    near_feet = {
        "action_type": "pass",
        "target": [8.0, 0.0],
        "source": "pass",
        "value": {
            "score": 0.4,
            "success_prob": 0.2,
            "components": {
                "target_kind": "feet",
                "receiver_arrival": 0.9,
                "outcome_transition": {
                    "retained_control_probability": 0.2,
                    "opposing_control_probability": 0.1,
                    "unresolved_probability": 0.7,
                },
            },
        },
        "details": {
            "target_player_idx": 2,
            "receiver_motion": {
                "receiver_pos": [8.0, 0.0],
                "receiver_speed_mps": 1.0,
                "receiver_to_target_distance_m": 0.0,
                "receiver_movement_intent": "support",
                "receiver_effective_target": [10.0, 0.0],
                "receiver_distance_to_effective_target_m": 2.0,
                "receiver_effective_target_distance_from_holder_m": 10.0,
                "receiver_velocity_toward_holder_mps": -1.0,
                "receiver_velocity_toward_effective_target_mps": 1.0,
                "receiver_task_active": True,
                "receiver_tactical_task": {
                    "intent": "support",
                    "phase": "active",
                    "raw_target": [10.0, 0.0],
                },
            },
        },
    }
    summary = _action_pace_summary({
        "trace": {
            "detail": "full",
            "entries": [],
            "decisions": [{
                "tick": 12,
                "phase": "on_ball",
                "team": "home",
                "player_idx": 4,
                "pos": [0.0, 0.0],
                "control": {},
                "chosen": {
                    "action_type": "carry",
                    "target": [1.0, 0.0],
                    "value": {"score": 0.5, "components": {}},
                },
                "alternatives": [near_feet],
            }],
        },
        "events": [],
    })

    audit = summary["pass_candidate_selection"]["near_feet_receiver_task_motion"]
    assert "not acceleration or causality" in audit["scope"]
    assert audit["groups"]["offset=0_0.5m"]["counts"] == {
        "candidates": 1,
        "effective_target_farther_from_holder": 1,
        "moving_away_from_holder": 1,
        "selected": 0,
        "task_active": 1,
        "velocity_aligned_to_effective_target": 1,
    }
    joint = audit["groups"][
        "offset=0_0.5m:holder=away:effective_target=aligned"
    ]
    assert joint["counts"]["candidates"] == 1
    assert joint["metrics"]["retention"]["median"] == 0.2
    assert joint["metrics"]["unresolved"]["median"] == 0.7
    assert (
        audit["groups"]["offset=0_0.5m:task_intent=support"]["metrics"]
        ["effective_target_holder_distance_delta_m"]["median"]
        == 2.0
    )


def test_support_arrival_stability_joins_braking_and_exact_feet_control() -> None:
    supporter = {
        "idx": 2,
        "is_goalkeeper": False,
        "task_active": True,
        "task_intent": "Support",
        "task_accepted_tick": 7,
        "movement_intent": "recover_shape",
        "goal_type": "support_carrier",
        "effective_target": [7.8, 0.0],
    }
    entries = [
        {
            "event": "held_support_state",
            "tick": 10,
            "possession_id": 1,
            "team": "home",
            "holder_idx": 4,
            "holder_pos": [0.0, 0.0],
            "supporters": [{**supporter, "pos": [6.0, 0.0], "velocity": [2.0, 0.0]}],
        },
        {
            "event": "held_support_state",
            "tick": 11,
            "possession_id": 1,
            "team": "home",
            "holder_idx": 4,
            "holder_pos": [0.0, 0.0],
            "supporters": [{**supporter, "pos": [7.0, 0.0], "velocity": [1.0, 0.0]}],
        },
    ]
    exact_feet = {
        "action_type": "pass",
        "target": [7.0, 0.0],
        "details": {
            "target_player_idx": 2,
            "receiver_motion": {
                "receiver_to_target_distance_m": 0.0,
                "production_receipt_projection": {
                    "terminal_precontact_receiver_to_ball_m": 0.4
                },
            },
        },
        "value": {
            "score": 0.1,
            "components": {
                "target_kind": "feet",
                "outcome_transition": {
                    "retained_control_probability": 0.9,
                    "unresolved_probability": 0.05,
                },
            },
        },
    }
    decisions = [{
        "phase": "on_ball", "tick": 11, "team": "home", "player_idx": 4,
        "chosen": exact_feet, "alternatives": [],
    }]

    summary = _support_arrival_stability_summary(entries, decisions)

    near = summary["groups"]["target_gap=0.5_1m"]
    assert near["counts"]["frames"] == 1
    assert near["counts"]["braking"] == 1
    assert near["counts"]["closed_previous_target_gap"] == 1
    assert near["counts"]["exact_feet_candidate"] == 1
    assert near["metrics"]["speed_delta_mps"]["median"] == -1.0
    assert near["metrics"]["exact_feet_retention"]["median"] == 0.9
    assert (
        near["metrics"]["exact_feet_terminal_precontact_distance_m"]["median"]
        == 0.4
    )


def test_task_continuity_uses_exact_coordination_pre_accept_lifecycle() -> None:
    claim = {
        "active": True,
        "origin": [12.0, 0.0],
        "target": [8.0, 0.0],
        "occupancy_radius": 4.2,
        "corridor_half_width": 2.0,
        "depth_band": 1,
        "width_band": 0,
    }

    def supporter(tick: int, accepted_tick: int) -> dict:
        return {
            "idx": 2,
            "is_goalkeeper": False,
            "pos": [12.0 - tick, 0.0],
            "velocity": [-1.0, 0.0],
            "target_pos": [8.0, 0.0],
            "tactical_anchor": [14.0, 0.0],
            "effective_target": [8.0, 0.0],
            "movement_intent": "support",
            "goal_type": "support_carrier",
            "goal_phase": "support",
            "goal_target": [8.0, 0.0],
            "task_active": True,
            "task_intent": "Support",
            "task_raw_target": [8.0, 0.0],
            "task_accepted_tick": accepted_tick,
            "task_expires_tick": 8,
            "task_commitment": 0.8,
            "task_policy_utility": 0.3,
            "task_formation_debt": 0.2,
            "task_spatial_claim": claim,
            "plan_signals": {"compactness": 0.5},
        }

    entries = [
        {
            "event": "held_support_state",
            "tick": 1,
            "possession_id": 3,
            "team": "home",
            "holder_idx": 4,
            "holder_pos": [0.0, 0.0],
            "supporters": [supporter(1, 1)],
        },
        {
            "event": "held_support_state",
            "tick": 2,
            "possession_id": 3,
            "team": "home",
            "holder_idx": 4,
            "holder_pos": [0.0, 0.0],
            "supporters": [supporter(2, 2)],
        },
    ]
    decisions = [{
        "phase": "off_ball_attack_spatial_coordination",
        "tick": 2,
        "team": "home",
        "player_idx": 2,
        "resolution": {
            "candidate_index": 0,
            "preferred_candidate_index": 0,
            "pre_accept": {
                "current_tick": 2,
                "tactical_task_tick": 1,
                "current_active": False,
                "task": {
                    "phase": "cancelled",
                    "accepted_tick": 0,
                    "expires_tick": 0,
                },
            },
            "actual_task": {
                "intent": "support",
                "accepted_tick": 2,
            },
            "candidates": [{
                "candidate_index": 0,
                "target": [8.0, 0.0],
                "claim_active": True,
                "claim_origin": [12.0, 0.0],
                "occupancy_radius": 4.2,
                "corridor_half_width": 2.0,
                "depth_band": 1,
                "width_band": 0,
            }],
        },
        "declaration": {
            "task_accepted": True,
            "task_candidate_value": 0.4,
            "task_retained_value": None,
            "task_acceptance_gates": {
                "active_current": False,
                "same_responsibility": False,
                "coordinated_reassignment": False,
                "value_advantage_clears_margin": True,
            },
        },
        "claim": claim,
    }]

    summary = _action_pace_summary({
        "config": {"tick_duration": 1.0},
        "trace": {"detail": "full", "entries": entries, "decisions": decisions},
        "events": [],
    })
    counts = summary["off_ball_support_selection"][
        "held_physical_tick_task_continuity"
    ]["counts"]
    assert counts["task_reaccepted_pre_accept_phase=cancelled"] == 1
    assert counts["task_reaccepted_pre_accept_lifecycle=cancelled"] == 1
    assert counts["coordination_pre_accept_gate_match"] == 1


def test_action_pace_groups_visual_carrier_by_actual_holder_identity() -> None:
    def off_ball(player_idx: int, visual_idx: int | None) -> dict:
        return {
            "phase": "off_ball_attack",
            "tick": 4,
            "team": "home",
            "holder_idx": 2,
            "player_idx": player_idx,
            "pos": [12.0 + player_idx, 0.0],
            "perceived_visual_has_ball_carrier": visual_idx is not None,
            "visual_carrier_hint": (
                {"index": visual_idx, "pos": [0.0, 0.0], "confidence": 0.9}
                if visual_idx is not None
                else None
            ),
            "chosen": {
                "action_type": "move",
                "target": [8.0 + player_idx, 0.0],
                "candidate_source": "role_support",
                "value": {"score": 0.5, "components": {}},
            },
            "alternatives": [{
                "action_type": "move",
                "target": [6.0, 0.0],
                "candidate_source": "support_sample",
                "value": {"score": 0.4, "components": {}},
            }],
        }

    summary = _action_pace_summary({
        "trace": {
            "detail": "full",
            "entries": [{
                "event": "held_support_state",
                "tick": 4,
                "team": "home",
                "holder_idx": 2,
                "holder_pos": [0.0, 0.0],
                "nearest_opponent_distance_m": 1.0,
                "supporters": [],
            }],
            "decisions": [
                off_ball(3, 2),
                off_ball(4, 7),
                off_ball(5, None),
            ],
        },
        "events": [],
    })
    groups = summary["off_ball_support_selection"][
        "visual_carrier_truth_alignment"
    ]["groups"]
    assert groups["visual_actual_holder"]["counts"]["decisions"] == 1
    assert groups["visual_wrong_teammate"]["counts"]["decisions"] == 1
    assert groups["no_visual_carrier"]["counts"]["decisions"] == 1
    assert (
        groups["no_visual_carrier:pressure=0_2m"]["counts"][
            "candidate_pool_has_under_10m"
        ]
        == 1
    )
    retained_summary = _action_pace_summary({
        "trace": {
            "detail": "full",
            "entries": [
                {
                    "event": "held_support_state",
                    "tick": tick,
                    "team": "home",
                    "holder_idx": 2,
                    "holder_pos": [float(tick - 4), 0.0],
                    "nearest_opponent_distance_m": 1.0,
                    "supporters": [],
                }
                for tick in (4, 5)
            ],
            "decisions": [
                off_ball(3, 2),
                {**off_ball(3, None), "tick": 5},
            ],
        },
        "events": [],
    })
    retained = retained_summary["off_ball_support_selection"][
        "visual_carrier_retention_upper_bound"
    ]
    assert retained["counts"]["recent_association_matches_actual_holder"] == 1
    assert retained["counts"]["high_pressure_recent_match"] == 1
    assert retained["metrics"]["matching_association_position_error_m"][
        "median"
    ] == 1.0


def test_support_task_pass_funnel_joins_tasks_to_receiver_candidates() -> None:
    def pass_candidate(
        receiver_idx: int, target: list[float], score: float, selected: bool = False
    ) -> dict:
        return {
            "action_type": "pass",
            "target": target,
            "value": {
                "score": score,
                "success_prob": 0.9,
                "components": {"target_kind": "feet"},
            },
            "details": {
                "target_player_idx": receiver_idx,
                "receiver_motion": {"receiver_to_target_distance_m": 0.2},
            },
        }

    selected = pass_candidate(1, [8.0, 0.0], 0.4, selected=True)
    funnel = _support_task_pass_funnel([
        {
            "pos": [0.0, 0.0],
            "chosen": selected,
            "alternatives": [],
            "support_task_network_counterfactual": {
                "candidates": [
                    {
                        "player_idx": 1,
                        "intent": "support",
                        "current_pos": [8.0, 0.0],
                        "effective_target": [9.0, 0.0],
                        "move_distance_m": 1.0,
                        "value_delta": 0.01,
                    },
                    {
                        "player_idx": 2,
                        "intent": "receive",
                        "current_pos": [15.0, 0.0],
                        "effective_target": [7.0, 0.0],
                        "move_distance_m": 8.0,
                        "value_delta": 0.02,
                    },
                ]
            },
        }
    ])

    assert funnel["counts"]["active_support_task_observations"] == 2
    assert funnel["counts"]["tasks_with_pass_candidate"] == 1
    assert funnel["counts"]["tasks_with_feet_candidate"] == 1
    assert funnel["counts"]["tasks_best_feet_selected"] == 1
    assert funnel["counts"]["tasks_without_pass_candidate"] == 1
    assert funnel["counts"]["tasks_selected_as_receiver"] == 1
    assert funnel["by_task_current_distance"]["0_10m"]["counts"] == {
        "best_feet_selected": 1,
        "selected": 1,
        "tasks": 1,
        "with_feet_candidate": 1,
        "with_pass_candidate": 1,
    }
    assert funnel["by_task_current_distance"]["10_20m"]["counts"] == {
        "tasks": 1,
        "without_pass_candidate": 1,
    }
    assert funnel["metrics"]["task_pass_to_effective_task_target_gap_m"][
        "median"
    ] == 1.0


def test_support_task_pass_funnel_exposes_unselected_higher_value_task_pass() -> None:
    task_pass = {
        "action_type": "pass",
        "target": [6.0, 0.0],
        "value": {
            "score": 0.6,
            "success_prob": 0.9,
            "components": {"target_kind": "feet"},
        },
        "details": {
            "target_player_idx": 3,
            "receiver_motion": {"receiver_to_target_distance_m": 0.0},
        },
    }
    funnel = _support_task_pass_funnel([
        {
            "pos": [0.0, 0.0],
            "chosen": {
                "action_type": "carry",
                "target": [3.0, 0.0],
                "value": {"score": 0.5},
                "details": {},
            },
            "alternatives": [task_pass],
            "support_task_network_counterfactual": {
                "candidates": [
                    {
                        "player_idx": 3,
                        "intent": "support",
                        "current_pos": [6.0, 0.0],
                        "effective_target": [6.0, 0.0],
                        "move_distance_m": 0.0,
                    }
                ]
            },
        }
    ])

    assert funnel["counts"]["decisions_best_task_pass_not_selected"] == 1
    assert funnel["counts"]["decisions_unselected_task_pass_beats_chosen"] == 1
    assert funnel["metrics"]["task_pass_minus_chosen"]["median"] == 0.1


def test_action_pace_requires_instant_and_time_budget_team_marginal_gain() -> None:
    summary = _action_pace_summary({
        "trace": {
            "detail": "full",
            "entries": [],
            "decisions": [{
                "phase": "on_ball",
                "tick": 4,
                "team": "home",
                "player_idx": 2,
                "pos": [0.0, 0.0],
                "chosen": {
                    "action_type": "hold",
                    "target": [0.0, 0.0],
                    "value": {"score": 0.02, "components": {}},
                },
                "alternatives": [],
                "support_task_network_counterfactual": {
                    "current_value": 0.02,
                    "all_support_targets": {"candidate_count": 2},
                    "team_candidate_marginal": {
                        "candidates": [
                            {
                                "candidate_source": "role_support",
                                "target_distance_to_holder_m": 7.0,
                                "move_distance_m": 4.0,
                                "local_score": 0.01,
                                "local_to_selected_ratio": 0.4,
                                "passes_local_floor": False,
                                "value_delta": 0.003,
                                "time_budget_value_delta": 0.002,
                                "outlet_access_delta": 0.01,
                            },
                            {
                                "candidate_source": "support_sample",
                                "target_distance_to_holder_m": 8.0,
                                "move_distance_m": 12.0,
                                "local_score": 0.008,
                                "local_to_selected_ratio": 0.3,
                                "passes_local_floor": False,
                                "value_delta": 0.004,
                                "time_budget_value_delta": -0.001,
                                "outlet_access_delta": 0.02,
                            },
                        ]
                    },
                },
            }],
        },
        "events": [],
    })

    group = summary["support_task_network_counterfactual"][
        "team_candidate_marginal_by_holder_distance"
    ]["0_10m"]
    assert group["counts"]["positive"] == 2
    assert group["counts"]["time_budget_positive"] == 1
    assert group["counts"]["instant_and_time_budget_positive"] == 1
    assert (
        group["counts"][
            "instant_and_time_budget_positive_below_local_floor"
        ]
        == 1
    )
    assert (
        group["metrics"][
            "instant_and_time_budget_positive:move_distance_m"
        ]["median"]
        == 4.0
    )


def test_selected_pass_release_funnel_preserves_same_tick_multiplicity() -> None:
    decision = {
        "tick": 8,
        "team": "home",
        "player_idx": 4,
        "possession_id": 3,
        "pos": [10.0, 20.0],
        "chosen": {
            "action_type": "pass",
            "target": [18.0, 20.0],
            "source": "pass",
            "value": {"score": 0.03, "components": {"target_kind": "feet"}},
        },
    }
    summary = _selected_pass_release_funnel(
        [decision, decision],
        [
            {
                "tick": 8,
                "team": "home",
                "passer_player": 4,
                "action": "pass",
                "replay_id": 9,
            },
            {
                "tick": 8,
                "holder_team": "home",
                "holder_idx": 4,
                "event": "receipt_decision_wait",
                "reason": "insufficient_release_time",
            },
        ],
    )

    assert summary["counts"]["selected"] == 2
    assert summary["counts"]["released"] == 1
    assert summary["counts"]["not_released"] == 1
    assert (
        summary["counts"][
            "not_released:reason=receipt_wait:insufficient_release_time"
        ]
        == 1
    )
    assert summary["counts"]["release_actions_without_selected_decision"] == 0


def test_selected_pass_release_funnel_attributes_opponent_foul_before_release() -> None:
    decision = {
        "tick": 12,
        "team": "home",
        "player_idx": 6,
        "possession_id": 5,
        "pos": [40.0, 20.0],
        "chosen": {
            "action_type": "pass",
            "target": [58.0, 22.0],
            "source": "pass",
            "value": {"score": 0.02, "components": {"target_kind": "feet"}},
        },
    }

    summary = _selected_pass_release_funnel(
        [decision],
        [{"tick": 12, "event": "foul", "team": "away", "player_idx": 4}],
    )

    assert summary["counts"]["not_released:reason=foul:opponent_committed"] == 1
    assert summary["not_released_cases"][0]["tick_window"][0]["label"] == "foul"


def test_physical_short_pass_funnel_separates_belief_and_candidate_gates() -> None:
    chosen = {
        "action_type": "pass",
        "target": [8.0, 0.0],
        "details": {"target_player_idx": 1},
        "source": "pass",
        "value": {
            "score": 0.04,
            "success_prob": 0.92,
            "components": {
                "target_kind": "feet",
                "receiver_arrival": 0.85,
                "receiver_pressure": 0.1,
            },
        },
    }
    decisions = [{
        "tick": 3,
        "team": "home",
        "player_idx": 4,
        "pos": [0.0, 0.0],
        "control": {"pressure_load": 0.3},
        "chosen": chosen,
        "alternatives": [],
    }]
    entries = [
        {
            "tick": 3,
            "team": "home",
            "player_idx": 4,
            "event": "on_ball_candidate_counts",
            "teammate_goals": [
                {"idx": 1, "pos": [8.0, 0.0]},
                {"idx": 2, "pos": [9.0, 0.0]},
            ],
            "teammate_visibility": [
                {
                    "idx": 1,
                    "belief_confidence": 0.8,
                    "belief_position_error_m": 0.2,
                },
                {"idx": 2, "belief_confidence": None},
            ],
            "communicated_teammates": [{"idx": 2}],
        },
        {
            "tick": 3,
            "team": "home",
            "passer_player": 4,
            "action": "pass",
            "replay_id": 7,
        },
    ]

    funnel = _physical_short_pass_availability_funnel(decisions, entries)
    assert funnel["counts"]["physical_teammate_observations_under_10m"] == 2
    assert funnel["counts"]["physical_near_in_holder_belief"] == 1
    assert funnel["counts"]["physical_near_missing_from_holder_belief"] == 1
    assert funnel["counts"]["physical_near_with_communication_hint"] == 1
    assert funnel["counts"]["physical_near_with_near_feet_candidate"] == 1
    assert funnel["counts"]["physical_near_with_safe_near_feet_candidate"] == 1
    assert funnel["counts"]["physical_near_selected_near_feet"] == 1
    assert funnel["counts"]["physical_near_released_near_feet"] == 1


def test_communication_pass_counterfactual_aggregates_raw_candidates() -> None:
    summary = _communication_pass_counterfactual_summary([
        {
            "event": "communication_pass_counterfactual",
            "tick": 3,
            "team": "home",
            "player_idx": 4,
            "candidates": [
                {
                    "receiver_role": "CM",
                    "value": 0.04,
                    "minus_actual_temporal_best": 0.01,
                    "retention": 0.9,
                    "distance_m": 7.5,
                    "hint_distance_m": 7.4,
                    "hint_age_ticks": 1,
                    "actual_position_error_m": 0.08,
                },
                {
                    "receiver_role": "ST",
                    "value": 0.02,
                    "minus_actual_temporal_best": -0.01,
                    "retention": 0.84,
                    "distance_m": 9.2,
                    "hint_distance_m": 9.1,
                    "hint_age_ticks": 1,
                    "actual_position_error_m": 0.12,
                },
            ],
        },
        {
            "event": "communication_pass_counterfactual",
            "tick": 4,
            "team": "away",
            "player_idx": 2,
            "candidates": [],
        },
        {
            "event": "single_communication_pass_admission_counterfactual",
            "profile": "communicated_task_space",
            "tick": 3,
            "team": "home",
            "player_idx": 4,
            "player_position": "CM",
            "actual_best_action": "carry",
            "actual_best_source": "carry",
            "option": {
                "receiver_role": "ST",
                "distance_m": 18.0,
                "progress_m": 12.0,
                "hint_age_ticks": 1,
                "actual_position_error_m": 0.1,
            },
            "admission": {
                "option": {
                    "near_optimal": True,
                    "raw_score_gap_to_actual_best": -0.002,
                    "conditional_pass_family_probability": 0.3,
                    "overall_selection_probability": 0.12,
                    "retained_control_probability": 0.88,
                    "opposing_control_probability": 0.04,
                    "unresolved_probability": 0.08,
                },
                "family_stage": {
                    "counterfactual_pass_near_optimal": True,
                    "current_pass_probability": 0.25,
                    "counterfactual_pass_probability": 0.4,
                    "ground_overall_probability_displaced": 0.05,
                },
            },
        },
        {"event": "unrelated", "candidates": None},
    ], [{
        "tick": 3,
        "team": "home",
        "player_idx": 4,
        "chosen": {
            "action_type": "carry",
            "value": {"score": 0.03},
        },
    }])

    assert summary["counts"]["events"] == 2
    assert summary["counts"]["events_with_candidates"] == 1
    assert summary["counts"]["events_without_candidates"] == 1
    assert summary["counts"]["candidates"] == 2
    assert summary["counts"]["candidates_retention_ge_0.85"] == 1
    assert summary["counts"]["candidates_beating_actual_temporal_best"] == 1
    assert summary["selector_admission"]["counts"]["decisions"] == 1
    assert summary["selector_admission"]["counts"]["selectable_overall"] == 1
    assert summary["selector_admission"]["counts"][
        "direction=forward:selectable_overall"
    ] == 1
    assert summary["selector_admission"]["counts"][
        "profile=communicated_task_space:direction=forward:selectable_overall"
    ] == 1
    assert (
        summary["counts"][
            "candidates_safe_and_beating_actual_temporal_best"
        ]
        == 1
    )
    assert (
        summary["counts"][
            "events_with_safe_candidate_beating_actual_temporal_best"
        ]
        == 1
    )
    assert (
        summary["counts"][
            "events_with_safe_0_10m_candidate_beating_actual_temporal_best"
        ]
        == 1
    )
    assert summary["metrics"]["minus_actual_temporal_best"]["median"] == 0.0
    assert summary["by_candidate_distance"]["0_10m"]["counts"] == {
        "candidates": 2,
        "candidates_beating_actual_temporal_best": 1,
        "candidates_retention_ge_0.85": 1,
        "candidates_safe_and_beating_actual_temporal_best": 1,
    }
    assert summary["by_receiver_role"]["CM"]["counts"]["candidates"] == 1
    assert summary["counts"]["safe_0_10m:chosen_action=carry"] == 1
    assert summary["safe_0_10m_cases"][0]["chosen_score"] == 0.03
    assert summary["safe_0_10m_cases"][0]["best_candidate"]["value"] == 0.04
    assert (
        summary["by_receiver_role"]["ST"]["metrics"]["retention"][
            "median"
        ]
        == 0.84
    )


def test_communication_receipt_follow_up_requires_value_safety_and_time() -> None:
    candidate = {
        "distance_m": 7.0,
        "retention": 0.9,
        "minus_actual_temporal_best": 0.01,
        "hint_age_ticks": 1,
        "actual_position_error_m": 0.1,
    }
    summary = _communication_receipt_follow_up_counterfactual_summary([
        {
            "event": "receipt_fast_pass",
            "available_fraction": 0.4,
            "required_release_fraction": 0.2,
            "communication_pass_counterfactual": [candidate],
        },
        {
            "event": "receipt_decision_wait",
            "remaining_tick_fraction": 0.1,
            "communication_required_release_fraction": 0.3,
            "communication_pass_counterfactual": [candidate],
        },
        {
            "event": "receipt_decision_wait",
            "remaining_tick_fraction": 0.5,
            "reason": "follow_up_action_already_used",
        },
    ])

    assert summary["counts"]["receipt_decisions"] == 2
    assert summary["counts"]["candidates_safe_0_10m_beating_actual"] == 2
    assert (
        summary["counts"][
            "candidates_executable_safe_0_10m_beating_actual"
        ]
        == 1
    )
    assert (
        summary["counts"][
            "receipt_decisions_with_executable_safe_0_10m_candidate_beating_actual"
        ]
        == 1
    )
    assert summary["counts"]["receipt_events_without_counterfactual_snapshot"] == 1
    assert (
        summary["by_receipt_outcome"]["wait"]["counts"].get(
            "with_communication_release_budget", 0
        )
        == 0
    )


def test_action_pace_pairs_pass_outcomes_with_the_actual_team_plan() -> None:
    summary = _action_pace_summary(
        {
            "trace": {
                "detail": "full",
                "decisions": [
                    {
                        "tick": 12,
                        "phase": "on_ball",
                        "team": "home",
                        "player_idx": 4,
                        "team_plan_kind": "switch",
                        "pos": [10.0, 20.0],
                        "chosen": {
                            "action_type": "pass",
                            "target": [40.0, 24.0],
                            "value": {"score": 0.02, "components": {}},
                        },
                        "alternatives": [],
                    }
                ],
                "entries": [
                    {
                        "tick": 12,
                        "team": "home",
                        "passer_player": 4,
                        "action": "pass",
                        "replay_id": 7,
                        "origin": [10.0, 20.0],
                        "target": [40.0, 24.0],
                        "retention_probability": 0.72,
                        "lane_risk": 0.18,
                        "base_accuracy": 0.81,
                    },
                    {
                        "event": "pass_control_terminal",
                        "replay_id": 7,
                        "outcome": "completed",
                    },
                ],
            },
            "events": [],
        }
    )

    actual = summary["pass_candidate_selection"][
        "pass_outcome_by_actual_team_plan"
    ]["switch"]
    assert actual["outcomes"] == {"completed": 1}
    assert actual["completion_rate"] == 1.0
    assert actual["metrics"]["distance_m"]["mean"] == 30.265492
    assert actual["metrics"]["retention_probability"]["mean"] == 0.72
    assert actual["metrics"]["lane_risk"]["mean"] == 0.18
    assert actual["metrics"]["base_accuracy"]["mean"] == 0.81


def test_action_pace_counts_only_five_metre_carry_episodes_as_provider_compatible() -> None:
    summary = _action_pace_summary(
        {
            "trace": {
                "decisions": [],
                "entries": [
                    {
                        "action": "carry",
                        "phase": "start",
                        "team": "home",
                        "player_idx": 4,
                        "possession_id": 9,
                        "physical_distance": 3.2,
                    },
                    {
                        "action": "carry",
                        "phase": "continue",
                        "team": "home",
                        "player_idx": 4,
                        "possession_id": 9,
                        "physical_distance": 2.1,
                    },
                    {
                        "action": "carry",
                        "phase": "start",
                        "team": "away",
                        "player_idx": 7,
                        "possession_id": 10,
                        "physical_distance": 4.99,
                    },
                ],
            },
            "events": [],
        }
    )

    carries = summary["provider_compatible_carries"]
    assert carries["selected_episodes"] == 2
    assert carries["at_least_5m"] == 1
    assert carries["under_5m"] == 1
    assert carries["distance_m"]["median"] == 5.145


def test_action_pace_partitions_stable_control_provenance() -> None:
    summary = _action_pace_summary(
        {
            "trace": {
                "decisions": [],
                "entries": [
                    {"event": "ball_controlled", "settled_pass": True},
                    {
                        "event": "ball_controlled",
                        "settled_pass": False,
                        "same_team_as_previous_possession": True,
                    },
                    {
                        "event": "ball_controlled",
                        "settled_pass": False,
                        "same_team_as_previous_possession": False,
                    },
                ],
            },
            "events": [],
        }
    )

    assert summary["stable_control_provenance"]["counts"] == {
        "opponent_control_gain": 1,
        "pass": 1,
        "same_team_loose_recovery": 1,
    }


def test_release_calibration_separates_possession_retention_from_opta_completion() -> None:
    entries = []
    for replay_id, retention, outcome, possession_retained in [
        (1, 0.8, "completed", True),
        (2, 0.6, "loose", True),
        (3, 0.2, "opposing_control", False),
        (4, 0.4, "out_of_play", False),
    ]:
        entries.append(
            {
                "action": "pass",
                "replay_id": replay_id,
                "technical_probability": 1.0,
                "technical_roll": 0.5,
                "pass_type": "short",
                "retention_probability": retention,
                "frozen_retention_probability": retention,
                "opta_long": False,
                "delivery_miss": False,
            }
        )
        entries.append(
            {
                "event": "pass_control_terminal",
                "replay_id": replay_id,
                "outcome": outcome,
                "possession_retained": possession_retained,
                "retention_probability": retention,
                "delivery_miss": False,
            }
        )

    summary = _action_pace_summary(
        {"trace": {"detail": "chosen", "decisions": [], "entries": entries}, "events": []}
    )
    bucket = summary["release_outcome_calibration"][
        "unconditional_by_restart_length"
    ]["open_play:short"]

    assert bucket["attempted"] == 4
    assert bucket["observed_completion_rate"] == 0.25
    assert bucket["possession_labeled"] == 4
    assert bucket["observed_retention_rate"] == 0.5
    assert bucket["mean_predicted_retention"] == 0.5


def test_free_ball_summary_separates_same_tick_receipt_from_full_free_ball_ticks() -> None:
    summary = _free_ball_control_summary(
        {
            "trace": {
                "entries": [
                    {
                        "action": "pass",
                        "replay_id": 1,
                        "actual_distance_m": 8.0,
                        "target_kind": "feet",
                        "delivery_miss": False,
                    },
                    {
                        "event": "pass_physical_terminal",
                        "replay_id": 1,
                        "passer_team": "home",
                        "intended_receiver_player": 8,
                        "strongest_contact_team": "home",
                        "strongest_contact_player": 8,
                        "stable_controller_player": None,
                        "terminal_speed": 2.0,
                        "home_claim": 0.3,
                        "away_claim": 0.0,
                    },
                    {
                        "action": "pass",
                        "replay_id": 2,
                        "actual_distance_m": 35.0,
                        "target_kind": "space",
                        "delivery_miss": True,
                    },
                    {
                        "event": "pass_physical_terminal",
                        "replay_id": 2,
                        "passer_team": "home",
                        "intended_receiver_player": 9,
                        "strongest_contact_team": "away",
                        "strongest_contact_player": 4,
                        "stable_controller_player": None,
                        "terminal_speed": 4.0,
                        "home_claim": 0.2,
                        "away_claim": 0.4,
                    },
                    {
                        "event": "continuous_ball_control",
                        "tick": 10,
                        "pending_pass_replay_id": 1,
                        "receipt_follow_up": True,
                        "phase_tick_fraction": 0.6,
                        "free_ball_ticks": 0,
                        "stable": True,
                    },
                    {
                        "event": "continuous_ball_control",
                        "tick": 11,
                        "pending_pass_replay_id": 2,
                        "receipt_follow_up": True,
                        "phase_tick_fraction": 0.4,
                        "free_ball_ticks": 0,
                        "stable": False,
                    },
                    {
                        "event": "continuous_ball_control",
                        "tick": 12,
                        "pending_pass_replay_id": 2,
                        "receipt_follow_up": False,
                        "phase_tick_fraction": 1.0,
                        "free_ball_ticks": 1,
                        "stable": True,
                    },
                ]
            }
        }
    )

    pending = summary["by_source"]["pending_pass"]
    assert pending["episodes"] == 2
    assert pending["same_arrival_tick_resolved"] == 1
    assert pending["crossed_full_tick"] == 1
    assert pending["receipt_follow_up_phases"] == 2
    assert pending["ticks"] == 1
    short = pending["by_distance"]["0_10m"]
    assert short["episodes"] == 1
    assert short["same_arrival_tick_resolved"] == 1
    assert short["intended_receiver_strongest_contact"] == 1
    long = pending["by_distance"]["32m_plus"]
    assert long["crossed_full_tick"] == 1
    assert long["delivery_miss"] == 1


def test_pass_terminal_control_partitions_length_delivery_and_controller() -> None:
    summary = _pass_terminal_control_summary(
        {
            "trace": {
                "entries": [
                    {
                        "event": "pass_physical_terminal",
                        "is_long": True,
                        "delivery_miss": True,
                        "passer_team": "home",
                        "intended_receiver_player": 7,
                        "materially_contacted": True,
                        "strongest_contact_team": "home",
                        "strongest_contact_player": 7,
                        "stable_controller_team": "home",
                    },
                    {
                        "event": "pass_physical_terminal",
                        "is_long": True,
                        "delivery_miss": True,
                        "passer_team": "away",
                        "intended_receiver_player": 8,
                        "materially_contacted": True,
                        "strongest_contact_team": "home",
                        "strongest_contact_player": 4,
                        "stable_controller_team": "home",
                    },
                ]
            }
        }
    )

    bucket = summary["by_length_and_delivery"]["long:miss"]
    assert bucket["terminals"] == 2
    assert bucket["strongest_contact_passer_team"] == 1
    assert bucket["strongest_contact_intended_receiver"] == 1
    assert bucket["stable_passer_team"] == 1
    assert bucket["stable_opponent"] == 1


def test_aggregate_pass_terminal_control_uses_all_physical_terminals() -> None:
    summaries = [
        {
            "pass_terminal_control": {
                "terminals": 8,
                "stable_at_terminal": 3,
                "by_length_and_delivery": {
                    "short:on_target": {"terminals": 8, "stable_passer_team": 3}
                },
            }
        },
        {
            "pass_terminal_control": {
                "terminals": 2,
                "stable_at_terminal": 2,
                "by_length_and_delivery": {
                    "short:on_target": {"terminals": 2, "stable_passer_team": 2}
                },
            }
        },
    ]

    aggregate = _aggregate_pass_terminal_control(summaries)

    assert aggregate["terminals"] == 10
    assert aggregate["stable_at_terminal"] == 5
    assert aggregate["direct_stable_share"] == 0.5
    assert aggregate["by_length_and_delivery"]["short:on_target"] == {
        "stable_passer_team": 5,
        "terminals": 10,
    }


def test_action_pace_reports_repeated_reorientation_for_the_same_holder() -> None:
    def decision(tick: int, action: str, player_idx: int = 4) -> dict:
        chosen = {
            "action_type": action,
            "value": {"components": {"option_duration_ticks": 1}},
        }
        if action == "reorient":
            chosen["details"] = {"facing_target": [10.0, 0.0]}
        return {
            "tick": tick,
            "phase": "on_ball",
            "team": "home",
            "player_idx": player_idx,
            "pos": [0.0, 0.0],
            "control": {"facing_direction": 90.0},
            "chosen": chosen,
            "alternatives": [],
        }

    summary = _action_pace_summary(
        {
            "trace": {
                "decisions": [
                    decision(1, "reorient"),
                    decision(2, "reorient"),
                    decision(3, "pass"),
                    decision(4, "reorient", player_idx=7),
                ],
                "entries": [],
            },
            "events": [],
        }
    )

    follow_up = summary["reorient_follow_up"]
    assert {
        key: follow_up[key]
        for key in (
            "selected",
            "same_holder_next_decision",
            "consecutive_reorients",
            "next_action",
            "turn_angle_degrees",
            "required_tick_fraction",
        )
    } == {
        "selected": 3,
        "same_holder_next_decision": 2,
        "consecutive_reorients": 1,
        "next_action": {"pass": 1, "reorient": 1},
        "turn_angle_degrees": {"median": 90.0, "p10": 90.0, "p90": 90.0},
        "required_tick_fraction": {
            "count": 0,
            "median": None,
            "p10": 0.0,
            "p90": 0.0,
            "mean_unused_fraction": None,
        },
    }
    assert follow_up["consecutive_target_switch_degrees"] == {
        "count": 1,
        "median": 0.0,
        "p10": 0.0,
        "p90": 0.0,
    }


def test_engine_possession_interruption_hazard_uses_id_span_and_active_time() -> None:
    hazard = _engine_possession_interruption_hazard({
        "events": [
            {"possession_id": 4},
            {"possession_id": 4},
            {"possession_id": 6},
            {"possession_id": 7},
        ],
        "match_clock": {"active_play_seconds": 60.0},
    })

    assert hazard == {
        "scope": (
            "team-control changes encoded by the engine possession_id span, divided "
            "by match_clock.active_play_seconds; this is a match-level survival "
            "hazard, not an action-specific failure probability"
        ),
        "first_possession_id": 4,
        "last_possession_id": 7,
        "observed_possession_ids": 3,
        "missing_observed_ids_in_span": 1,
        "team_control_interruptions": 3,
        "active_play_seconds": 60.0,
        "hazard_per_active_second": 0.05,
        "mean_team_control_survival_seconds": 20.0,
    }


def test_temporal_hazard_uses_engine_interruption_rate_and_reports_pace_ceiling() -> None:
    def pass_candidate(target_x: float, duration: float, undiscounted: float) -> dict:
        production_discount = 0.99
        return {
            "action_type": "pass",
            "target": [target_x, 0.0],
            "value": {
                "components": {
                    "option_return": undiscounted * production_discount,
                    "temporal_discount": production_discount,
                    "option_duration_seconds": duration,
                    "local_shaping": 0.0,
                    "target_kind": "feet",
                    "outcome_transition": {
                        "retained_control_probability": 0.9,
                    },
                }
            },
        }

    summary = _action_pace_summary({
        "events": [
            {"possession_id": 1},
            {"possession_id": 5},
        ],
        "match_clock": {"active_play_seconds": 100.0},
        "home_stats": {"passes": 1},
        "away_stats": {"passes": 1},
        "trace": {
            "entries": [],
            "decisions": [{
                "tick": 10,
                "phase": "on_ball",
                "team": "home",
                "player_idx": 4,
                "pos": [0.0, 0.0],
                "control": {"release_preparation": 0.5},
                "chosen": pass_candidate(30.0, 4.0, 0.5),
                "alternatives": [pass_candidate(8.0, 1.0, 0.48)],
            }],
        },
    })

    report = summary["temporal_hazard_counterfactual"]
    assert report["possession_interruption"]["hazard_per_active_second"] == 0.04
    engine = report["scenarios"][
        "source=engine_possession_interruption:lambda=0.040000:pass_duration=flight"
    ]
    assert engine["counts"]["selected_pass_distance=0_10m"] == 1
    assert engine["pass_minute_ceiling"] == {
        "scope": (
            "duration-only upper bound over decisions where observed and "
            "counterfactual choices are both passes; assumes every net flight "
            "second saved is reinvested into the unchanged provider pass cycle "
            "and therefore is not a simulated production result"
        ),
        "comparable_pass_to_pass_decisions": 1,
        "net_flight_seconds_saved": 3.0,
        "baseline_provider_passes_per_active_minute": 1.2,
        "observed_selected_pass_decisions": 1,
        "counterfactual_selected_pass_decisions": 1,
        "selected_pass_decision_delta": 0,
        "duration_reinvestment_upper_bound": 1.237113,
        "selection_and_duration_upper_bound": 1.237113,
    }
    assert (
        report["candidate_transition_hazard"]["eligibility"]
        == "diagnostic_only_double_counts_action_outcome_risk"
    )


def test_aggregate_reorient_follow_up_sums_match_counts() -> None:
    aggregate = _aggregate_reorient_follow_up(
        [
            {"action_pace": {"reorient_follow_up": {
                "selected": 3, "same_holder_next_decision": 2,
                "consecutive_reorients": 1, "next_action": {"pass": 1},
                "turn_angle_degrees": {"median": 30.0},
            }}},
            {"action_pace": {"reorient_follow_up": {
                "selected": 4, "same_holder_next_decision": 3,
                "consecutive_reorients": 2, "next_action": {"pass": 2},
                "turn_angle_degrees": {"median": 40.0},
            }}},
        ]
    )

    assert aggregate["selected"] == 7
    assert aggregate["same_holder_next_decision"] == 5
    assert aggregate["consecutive_reorients"] == 3
    assert aggregate["next_action"] == {"pass": 3}


def test_reorient_live_same_tick_summary_pairs_one_follow_up_pass() -> None:
    summary = _reorient_live_same_tick_summary(
        [
            {
                "tick": 12, "type": "action", "action": "reorient",
                "team": "home", "player_idx": 6, "elapsed_fraction": 0.25,
            },
            {
                "tick": 12, "type": "event", "event": "receipt_fast_pass",
                "holder_team": "home", "holder_idx": 6,
                "required_release_fraction": 0.15, "flight_fraction": 0.60,
            },
            {
                "tick": 12, "type": "action", "action": "pass",
                "team": "home", "passer_player": 6,
            },
            {
                "tick": 13, "type": "action", "action": "pass",
                "team": "home", "passer_player": 6,
            },
        ]
    )

    assert summary["eligible_reorients"] == 1
    assert summary["executed_fast_passes"] == 1
    assert summary["waited"] == 0
    assert summary["release_interrupted"] == 0
    assert summary["unaccounted"] == 0
    assert summary["multiple_follow_up_action_violations"] == 0
    assert summary["elapsed_fraction"]["mean"] == 0.25
    assert summary["flight_fraction"]["mean"] == 0.6


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
    subset_dimensions = {
        "long_fine_breakdown",
        "provider_long_fine_breakdown",
    }
    for dimension, buckets in summary["breakdown"].items():
        if dimension in subset_dimensions:
            assert sum(bucket["attempted"] for bucket in buckets.values()) == 0
            assert sum(bucket["completed"] for bucket in buckets.values()) == 0
            continue
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
    profile_delivery = summary["breakdown"]["by_profile_and_delivery"]
    assert profile_delivery["short:feet:0-10m:error"] == {
        "attempted": 3,
        "completed": 1,
        "completion_rate": 0.3333,
        "outcomes": {"completed": 1, "intercepted": 1, "loose": 1},
    }
    assert profile_delivery["short:feet:0-10m:clean"] == {
        "attempted": 2,
        "completed": 0,
        "completion_rate": 0.0,
        "outcomes": {"intercepted": 1, "loose": 1},
    }


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
    assert summary["breakdown"]["by_restart_distance_target"] == {
        "open_play:20-30m:space": {
            "attempted": 1,
            "completed": 0,
            "completion_rate": 0.0,
            "outcomes": {"out_of_play": 1},
        }
    }


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
        == "direct_provider_scope_with_period_end_sensitivity"
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
    assert alignment["metrics"]["passes"]["calibration_eligible"] is True
    assert alignment["metrics"]["passes"]["absolute_gap"] is not None
    assert alignment["metrics"]["pass_success_rate"]["calibration_eligible"] is True
    assert alignment["metrics"]["pass_success_rate"]["absolute_gap"] is not None


def test_premier_league_alignment_reports_physical_ball_in_play_pace() -> None:
    summary = {
        "home_stats": {
            "passes": 10, "passes_completed": 8, "crosses": 1,
            "crosses_completed": 1, "shots": 0, "shots_on_target": 0,
            "goals": 0, "goal_kicks": 0, "corners": 0,
            "offside_free_kicks": 0,
        },
        "away_stats": {
            "passes": 0, "passes_completed": 0, "crosses": 0,
            "crosses_completed": 0, "shots": 0, "shots_on_target": 0,
            "goals": 0, "goal_kicks": 0, "corners": 0,
            "offside_free_kicks": 0,
        },
        "score": [0, 0],
        "match_clock": {"active_play_seconds": 60 * 60},
        "shot_outcomes": {"total": {"blocked": 0}},
    }

    alignment = _premier_league_alignment([summary])

    assert alignment["metrics"]["ball_in_play_minutes"]["current"] == 60.0
    assert alignment["metrics"]["ball_in_play_minutes"]["target"] == 51.527
    assert alignment["metrics"]["passes"]["target"] == round(
        339493 / 380 * (90 * 60 / 5984), 3
    )
    assert alignment["metrics"]["ball_in_play_minutes"]["comparison_status"] == "direct"
    diagnostics = alignment["engine_scope_diagnostics"]
    assert diagnostics["provider_scope_passes_per_active_play_minute"] == 0.15
    assert diagnostics["premier_league_passes_per_ball_in_play_minute"] == 15.646
    assert diagnostics["premier_league_touches_per_match"] == round(
        481659 / 380 * (90 * 60 / 5984), 3
    )
    assert diagnostics["premier_league_pass_share_of_touches"] == 0.7048
    assert "no engine touch gap is reported" in diagnostics["touch_proxy_caveat"]
    directions = diagnostics["pass_direction_shares"]
    assert sum(directions["premier_league"].values()) == 1.0
    assert directions["premier_league"] == {
        "backward": 0.1615,
        "forward": 0.3232,
        "left": 0.2551,
        "right": 0.2602,
    }
    assert directions["engine_observed_completed_passes"] == 0


def test_premier_league_alignment_excludes_goal_kicks_and_opponent_contact_from_accurate_long_balls() -> None:
    summary = {
        "home_stats": {
            "passes": 10,
            "passes_completed": 6,
            "crosses": 0,
            "crosses_completed": 0,
            "shots": 0,
            "shots_on_target": 0,
            "goals": 0,
            "fouls": 0,
            "goal_kicks": 2,
            "corners": 0,
            "throw_ins": 0,
            "free_kicks": 0,
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
            "fouls": 0,
            "goal_kicks": 0,
            "corners": 0,
            "throw_ins": 0,
            "free_kicks": 0,
            "offside_free_kicks": 0,
        },
        "score": [0, 0],
        "match_clock": {"active_play_seconds": 60.0, "match_seconds": 90.0},
        "shot_outcomes": {
            "total": {"blocked": 0},
            "censored_on_target": {"total": 0, "home": 0, "away": 0},
        },
        "pass_causality": {
            "provider_long_completion_contact": {
                "non_goal_kick_with_opponent_contact": 1,
            },
            "breakdown": {
                "by_provider_pass_scope_length": {
                    "short": {"attempted": 5, "completed": 3},
                    "long": {"attempted": 5, "completed": 3},
                },
                "by_restart_origin_and_length": {
                    "goal_kick:long": {"attempted": 2, "completed": 2},
                },
            },
            "restart_shot_releases": {},
            "restart_shot_goals": {},
        },
        "restart_release_lifecycle": {"resolved": {}},
    }

    alignment = _premier_league_alignment([summary])

    assert alignment["metrics"]["long_balls"]["current"] == 5.0
    assert alignment["metrics"]["long_ball_accuracy"]["current"] == 0.0
    assert (
        alignment["engine_scope_diagnostics"][
            "goal_kick_long_completions_excluded_from_accurate_long_balls_per_match"
        ]
        == 2.0
    )
    assert (
        alignment["engine_scope_diagnostics"][
            "opponent_contact_long_completions_excluded_from_accurate_long_balls_per_match"
        ]
        == 1.0
    )


def test_premier_league_alignment_reports_committed_fouls_separately_from_offsides() -> None:
    summary = {
        "home_stats": {
            "passes": 0, "passes_completed": 0, "crosses": 0,
            "crosses_completed": 0, "shots": 0, "shots_on_target": 0,
            "goals": 0, "goal_kicks": 0, "corners": 0,
            "offside_free_kicks": 7, "free_kicks": 12, "fouls": 9,
        },
        "away_stats": {
            "passes": 0, "passes_completed": 0, "crosses": 0,
            "crosses_completed": 0, "shots": 0, "shots_on_target": 0,
            "goals": 0, "goal_kicks": 0, "corners": 0,
            "offside_free_kicks": 5, "free_kicks": 10, "fouls": 8,
        },
        "score": [0, 0],
        "shot_outcomes": {"total": {"blocked": 0}},
    }

    alignment = _premier_league_alignment([summary])

    assert alignment["metrics"]["fouls"]["current"] == 17.0
    assert alignment["metrics"]["fouls"]["target"] == round(
        8398 / 380 * (90 * 60 / 5984), 3
    )
    assert alignment["metrics"]["fouls"]["calibration_eligible"] is True


def test_opta_pass_success_does_not_double_count_restart_events_as_missing_passes() -> None:
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
    assert (
        alignment["engine_scope_diagnostics"][
            "goal_kick_restarts_per_match"
        ]
        == 2.0
    )
    assert alignment["metrics"]["pass_success_rate"][
        "known_scope_sensitivity_interval"
    ] == [62.5, 62.5]


def test_goal_kick_pass_provenance_partitions_real_passes_without_synthetic_attempts() -> None:
    events = [
        _event(
            "pass",
            "completed",
            tags=["short", "feet", "goal_kick_origin"],
        ),
        _event("pass", "completed", tags=["short", "feet"]),
        _event(
            "pass",
            "loose",
            tags=["long", "space", "goal_kick_origin"],
        ),
    ]
    summary = _pass_causality_summary(
        events,
        {"passes": 3, "passes_completed": 2},
        {"passes": 0, "passes_completed": 0},
    )

    restart_origin = summary["breakdown"]["by_restart_origin"]
    restart_length = summary["breakdown"]["by_restart_origin_and_length"]
    assert restart_origin["goal_kick"]["attempted"] == 2
    assert restart_origin["goal_kick"]["completed"] == 1
    assert restart_origin["open_play"]["attempted"] == 1
    assert sum(bucket["attempted"] for bucket in restart_origin.values()) == 3
    assert restart_length["goal_kick:short"]["attempted"] == 1
    assert restart_length["goal_kick:long"]["attempted"] == 1
    provider_restart_origin = summary["breakdown"][
        "by_provider_pass_scope_restart_origin"
    ]
    provider_restart_length = summary["breakdown"][
        "by_provider_pass_scope_restart_origin_and_length"
    ]
    assert provider_restart_origin == restart_origin
    assert provider_restart_length == restart_length


def test_corner_and_free_kick_provenance_partition_passes_and_direct_shots() -> None:
    events = [
        _event(
            "pass",
            "completed",
            tags=["long", "aerial", "corner_origin"],
        ),
        _event("pass", "loose", tags=["short", "space", "free_kick_origin"]),
        _event("shot", "off_target", tags=["corner_origin"]),
        _event("shot", "blocked", tags=["free_kick_origin"]),
    ]
    summary = _pass_causality_summary(
        events,
        {"passes": 2, "passes_completed": 1},
        {"passes": 0, "passes_completed": 0},
    )

    origins = summary["breakdown"]["by_restart_origin"]
    assert origins["corner"]["attempted"] == 1
    assert origins["free_kick"]["attempted"] == 1
    assert summary["breakdown"]["by_target_kind"]["aerial"]["attempted"] == 1
    assert summary["breakdown"]["by_target_kind"].get("feet") is None
    assert summary["restart_shot_releases"] == {"corner": 1, "free_kick": 1}


def test_corner_header_shot_preserves_provenance_without_double_counting_restart_release() -> None:
    events = [
        _event("restart", "corner", tags=["set_piece"]),
        _event("pass", "completed", tags=["corner_origin", "cross"]),
        _event("shot", "saved", tags=["corner_origin", "header", "corner_header"]),
    ]

    summary = _pass_causality_summary(
        events,
        {"passes": 1, "passes_completed": 1},
        {"passes": 0, "passes_completed": 0},
    )

    assert summary["restart_shot_releases"] == {}
    assert summary["corner_header_shots"] == 1
    assert summary["corner_header_goals"] == 0


def test_penalty_restart_lifecycle_pairs_with_exactly_one_shot_release() -> None:
    events = [
        _event("restart", "penalty", tags=["set_piece"]),
        _event("shot", "goal", tags=["penalty_origin"]),
    ]
    events[0]["tick"] = 10
    events[0]["seq"] = 1
    events[0]["half"] = 1
    events[1]["tick"] = 12
    events[1]["seq"] = 2
    events[1]["half"] = 1

    lifecycle = _restart_release_lifecycle(events)
    summary = _pass_causality_summary(
        events,
        {"passes": 0, "passes_completed": 0},
        {"passes": 0, "passes_completed": 0},
    )

    assert lifecycle["resolved"] == {"penalty": 1}
    assert lifecycle["orphaned_count"] == 0
    assert lifecycle["stray_release_count"] == 0
    assert summary["restart_shot_releases"] == {"penalty": 1}


def test_long_ball_benchmark_uses_complete_non_cross_pass_scope() -> None:
    summary = {
        "home_stats": {
            "passes": 10,
            "passes_completed": 8,
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
        "shot_outcomes": {"total": {"blocked": 0}},
        "pass_causality": {
            "breakdown": {
                "by_length": {
                    "long": {"attempted": 6, "completed": 3}
                },
                "by_provider_pass_scope_length": {
                    "long": {"attempted": 4, "completed": 2}
                },
            }
        },
    }

    alignment = _premier_league_alignment([summary])

    assert alignment["metrics"]["long_balls"]["current"] == 4.0
    assert alignment["metrics"]["long_ball_accuracy"]["current"] == 50.0
    for metric in ("long_balls", "long_ball_accuracy"):
        assert alignment["metrics"][metric]["comparison_status"].startswith(
            "direct_provider_scope"
        )
        assert alignment["metrics"][metric]["calibration_eligible"] is True
        assert alignment["metrics"][metric]["absolute_gap"] is not None


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
        {
            **_event("pass", "completed"),
            "seq": 3,
            "tick": 30,
            "match_second": 50,
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
    assert summary["duration_by_pass_count_band"]["1"] == {
        "count": 2,
        "total_seconds": 10.0,
        "mean_seconds": 5.0,
        "completed_passes": 2,
        "completed_passes_per_observed_minute": 12.0,
    }


def test_sequence_pass_direction_flips_with_the_second_half() -> None:
    events = [
        {
            **_event("pass", "completed", "home"),
            "origin": [60.0, 34.0],
            "target": [50.0, 34.0],
            "seq": 1,
            "tick": 10,
            "match_second": 10,
            "possession_id": 1,
            "half": 2,
        }
    ]

    summary = _sequence_summary(events, home_attacking_right=True)

    assert summary["pass_directions"] == {
        "forward": {"count": 1, "share": 1.0}
    }


def test_possession_chain_budget_attributes_unique_physical_ticks() -> None:
    events = [
        {
            **_event("restart", "goal_kick", "home"),
            "seq": 1,
            "tick": 0,
            "possession_id": 1,
        },
        {
            **_event("pass", "completed", "home"),
            "seq": 2,
            "tick": 1,
            "possession_id": 1,
            "tags": ["goal_kick_origin"],
        },
        {
            **_event("shot", "goal", "home"),
            "seq": 3,
            "tick": 2,
            "possession_id": 1,
        },
        {
            **_event("interception", "won", "home", tags=["pass_cut_out"]),
            "seq": 4,
            "tick": 3,
            "possession_id": 2,
        },
        {
            **_event("pass", "out_of_play", "away"),
            "seq": 5,
            "tick": 3,
            "possession_id": 2,
            "tags": ["corner"],
        },
    ]
    trace_entries = [
        {
            "type": "state",
            "tick": 0,
            "clock_phase_before": "active",
            "ball_state_before": "held",
            "possession_id_before": 1,
        },
        {
            "type": "state",
            "tick": 1,
            "clock_phase_before": "active",
            "ball_state_before": "held",
            "possession_id_before": 1,
        },
        {
            "type": "state",
            "tick": 1,
            "clock_phase_before": "active",
            "ball_state_before": "in_flight",
            "possession_id_before": 1,
        },
        {
            "type": "state",
            "tick": 2,
            "clock_phase_before": "active",
            "ball_state_before": "free_ball",
            "possession_id_before": 1,
        },
        {
            "type": "state",
            "tick": 3,
            "clock_phase_before": "active",
            "ball_state_before": "held",
            "possession_id_before": 2,
        },
    ]

    summary = _possession_chain_budget_summary(
        {
            "events": events,
            "trace": {"entries": trace_entries},
            "config": {"total_ticks": 4, "tick_duration": 1.0},
        }
    )

    assert summary["trace_complete"] is True
    assert summary["duplicate_recursive_state_entries"] == 1
    assert summary["by_pass_count_band"]["1"] == {
        "sequences": 1,
        "pass_attempts": 1,
        "completed_passes": 1,
        "provider_pass_attempts": 1,
        "provider_pass_completions": 1,
        "shots": 1,
        "goals": 1,
        "resulting_corners": 0,
        "resulting_goal_kicks": 0,
        "ball_state_ticks": {
            "held": 1,
            "in_flight": 1,
            "free_ball": 1,
            "dead": 0,
        },
        "active_seconds": 3.0,
        "provider_passes_per_active_minute": 20.0,
    }
    assert summary["by_restart_origin"]["goal_kick"]["goals"] == 1
    assert summary["by_pass_count_band"]["0"]["resulting_corners"] == 1
    assert summary["by_pass_count_band"]["0"]["provider_pass_attempts"] == 2


def test_held_action_execution_joins_fractional_rows_to_possession_outcome() -> None:
    events = [
        {
            **_event("pass", "completed", "home"),
            "seq": 1,
            "tick": 0,
            "possession_id": 7,
        },
        {
            **_event("carry", "completed", "home"),
            "seq": 2,
            "tick": 2,
            "possession_id": 7,
        },
        {
            **_event("pass", "completed", "home"),
            "seq": 3,
            "tick": 4,
            "possession_id": 7,
        },
    ]
    trace_entries = [
        {
            "type": "state",
            "tick": tick,
            "possession_id_before": 7,
        }
        for tick in range(5)
    ]
    trace_entries.extend(
        [
            {"type": "action", "tick": 0, "team": "home", "action": "pass"},
            {
                "type": "action",
                "tick": 1,
                "team": "home",
                "action": "reorient",
                "phase": "start",
                "elapsed_fraction": 0.25,
            },
            {
                "type": "action",
                "tick": 2,
                "team": "home",
                "action": "carry",
                "phase": "start",
            },
            {
                "type": "event",
                "event": "action_commitment_ended",
                "tick": 2,
                "team": "home",
                "action": "reorient",
                "reason": "time_budget",
                "elapsed_seconds": 1.25,
            },
            {
                "type": "event",
                "event": "receipt_decision_wait",
                "tick": 2,
                "selected_action": "carry",
                "reason": "selected_action_requires_next_tick",
            },
            {
                "type": "action",
                "tick": 3,
                "team": "home",
                "action": "carry",
                "phase": "continue",
            },
            {"type": "action", "tick": 4, "team": "home", "action": "pass"},
        ]
    )

    summary = _held_action_execution_by_possession_summary(
        {
            "events": events,
            "trace": {"entries": trace_entries},
            "config": {"tick_duration": 1.0},
        }
    )

    group = summary["groups"]["2-4:non_shot"]
    assert group["sequences"] == 1
    assert group["action_execution"]["carry"]["total_elapsed_seconds"] == 2.0
    assert group["action_execution"]["reorient"]["total_elapsed_seconds"] == 0.25
    assert group["nonpass_execution_seconds_per_sequence"]["mean"] == 2.25
    assert group["commitment_endings"]["counts"] == {
        "reorient:time_budget": 1
    }
    assert group["provider_action_intervals"]["counts"] == {
        "carry->pass": 1,
        "pass->carry": 1,
    }
    assert group["provider_action_intervals"]["seconds"]["carry->pass"][
        "mean"
    ] == 2.0
    assert group["same_tick_reorient_follow_up"] == {
        "wait": 1,
        "wait:reason=selected_action_requires_next_tick": 1,
        "wait:selected=carry": 1,
    }


def test_nonpass_pass_opportunity_groups_existing_candidates_by_final_chain() -> None:
    events = [
        {
            **_event("pass", "completed", "home"),
            "seq": 1,
            "tick": 1,
            "possession_id": 9,
        },
        {
            **_event("pass", "out_of_play", "home"),
            "seq": 2,
            "tick": 3,
            "possession_id": 9,
        },
    ]
    chosen = {
        "action_type": "carry",
        "value": {"score": 0.03, "components": {}},
    }
    visible_pass = {
        "action_type": "pass",
        "target": [18.0, 0.0],
        "details": {"target_player_idx": 8},
        "value": {
            "score": 0.04,
            "success_prob": 0.84,
            "components": {
                "after_value": 0.05,
                "option_duration_seconds": 1.5,
            },
        },
    }

    summary = _nonpass_pass_opportunity_by_possession_summary({
        "events": events,
        "trace": {
            "decisions": [
                {
                    "phase": "on_ball",
                    "tick": 2,
                    "possession_id": 9,
                    "team": "home",
                    "player_idx": 6,
                    "pos": [0.0, 0.0],
                    "chosen": chosen,
                    "alternatives": [visible_pass],
                    "support_geometry": {
                        "nearest_outfield_teammate_distance": 8.0,
                        "teammates_within_10m": 1,
                    },
                }
            ]
        },
    })

    group = summary["groups"]["1:non_shot"]
    assert group["counts"] == {
        "best_pass_higher": 1,
        "chosen=carry": 1,
        "nonpass_decisions": 1,
        "with_visible_pass": 1,
    }
    assert group["metrics"]["best_pass_minus_chosen"]["mean"] == 0.01
    assert group["metrics"]["best_pass_retention"]["mean"] == 0.84
    assert group["metrics"]["visible_pass_receivers"]["mean"] == 1.0
    prefix = summary["by_completed_passes_before_decision"]["1"]
    assert prefix["counts"]["nonpass_decisions"] == 1
    assert prefix["final_outcomes"] == {"final=1:non_shot": 1}


def test_optional_trace_rows_treats_chosen_detail_null_as_empty() -> None:
    assert _optional_trace_rows(None) == []
    assert _optional_trace_rows({"idx": 1}) == []
    rows = [{"idx": 1}]
    assert _optional_trace_rows(rows) is rows


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

    assert integrity["external_comparability"]["pass_success_rate"] == (
        "direct_provider_scope_with_period_end_sensitivity"
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
        "provider_scope_with_period_end_sensitivity"
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
        "total": 4,
        "by_field": {
            "dribbles": 2,
            "tackles": 2,
        },
    }
    assert integrity["issue_counts"]["warning"] == 4


def test_fouls_and_awarded_free_kicks_close_against_events() -> None:
    response = {
        "home_score": 0,
        "away_score": 0,
        "events": [
            _event("foul", "committed", team="home"),
            _event("restart", "free_kick", team="away"),
            _event("restart", "offside", team="away"),
        ],
        "home_stats": {"possession": 50.0, "fouls": 1, "free_kicks": 0},
        "away_stats": {
            "possession": 50.0,
            "fouls": 0,
            "free_kicks": 2,
            "offside_free_kicks": 1,
        },
        "home_player_stats": [],
        "away_player_stats": [],
    }

    integrity = _metric_integrity_summary(response)

    assert integrity["teams"]["home"]["checks"]["fouls.team_vs_events"]["status"] == "ok"
    assert integrity["teams"]["away"]["checks"]["free_kicks.team_vs_events"]["status"] == "ok"


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
        "pre_release_contested_loose": 0,
        "released": 1,
        "unresolved": 0,
        "over_resolved": 0,
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


def test_shot_outcomes_classify_only_goal_line_blocks_as_on_target_candidates() -> None:
    events = [
        {**_event("shot", "blocked"), "half": 1, "target": [103.5, 34.0]},
        {**_event("shot", "blocked"), "half": 1, "target": [95.0, 34.0]},
        {**_event("shot", "blocked"), "half": 1, "target": [104.0, 45.0]},
    ]

    outcomes = _shot_outcome_summary(events, home_attacking_right=True)

    assert outcomes["total"]["blocked"] == 3
    assert outcomes["last_line_blocks"]["total"] == 1


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


def test_formal_tackle_trace_ignores_non_object_contact_and_pairs_same_players() -> None:
    response = {
        "trace": {
            "entries": [
                {"tick": 4, "event": "contact", "contact": [1, 2]},
                {
                    "tick": 10, "event": "duel", "outcome": "attacker_wins",
                    "context": "carry", "possession_id": 3, "holder_idx": 6,
                    "holder_team_home": True, "defender_idx": 2,
                    "contact": {"defender_action": "tackle"},
                },
                {
                    "tick": 11, "event": "tackle", "outcome": "defender_wins",
                    "context": "carry", "possession_id": 3, "holder_idx": 6,
                    "holder_team_home": True, "defender_idx": 2,
                    "contact": {"defender_action": "tackle"},
                },
            ]
        }
    }

    summary = _formal_tackle_trace_summary(response)

    assert summary["count"] == 2
    assert summary["by_context"] == {"carry": 2}
    assert summary["same_pair_within_1_tick"] == 1
