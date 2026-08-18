#!/usr/bin/env python3
"""Run a bounded raw-trace audit of stable-control team-plan handoffs."""

from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from math import exp, hypot
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.diagnose_engine_v2_match_pace import (  # noqa: E402
    _bellman_candidate_ledger,
    _build_cards,
    _team_plan_pass_policy_decomposition,
    _two_stage_bounded_rational_distribution,
)


TEAM_PLAN_SIGNALS = {
    "build_up": {"forward_bias": 0.34, "recycle_bias": 0.72, "switch_bias": 0.50, "risk_budget": 0.34},
    "advance": {"forward_bias": 0.68, "recycle_bias": 0.30, "switch_bias": 0.34, "risk_budget": 0.62},
    "recycle": {"forward_bias": 0.16, "recycle_bias": 0.92, "switch_bias": 0.56, "risk_budget": 0.24},
    "switch": {"forward_bias": 0.32, "recycle_bias": 0.66, "switch_bias": 0.96, "risk_budget": 0.46},
    "final_third": {"forward_bias": 0.86, "recycle_bias": 0.22, "switch_bias": 0.28, "risk_budget": 0.76},
    "defend_block": {"forward_bias": 0.18, "recycle_bias": 0.42, "switch_bias": 0.24, "risk_budget": 0.28},
    "defend_press": {"forward_bias": 0.28, "recycle_bias": 0.34, "switch_bias": 0.22, "risk_budget": 0.48},
}


def _distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)

    def quantile(fraction: float) -> float:
        index = round((len(ordered) - 1) * fraction)
        return ordered[index]

    return {
        "count": len(values),
        "mean": round(mean(values), 6),
        "median": round(median(values), 6),
        "p10": round(quantile(0.10), 6),
        "p90": round(quantile(0.90), 6),
    }


def _candidate_successor_endpoint(candidate: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {}
    target = candidate.get("target")
    details = candidate.get("details", {})
    components = candidate.get("value", {}).get("components", {})
    projected_state = components.get("projected_retained_state", {})
    branch = (
        projected_state.get("dominant_projected_branch", {})
        if isinstance(projected_state, dict)
        else {}
    )
    receiver_motion = (
        details.get("receiver_motion", {}) if isinstance(details, dict) else {}
    )
    receiver_pos = (
        receiver_motion.get("receiver_pos")
        if isinstance(receiver_motion, dict)
        else None
    )
    controller_pos = branch.get("controller_pos") if isinstance(branch, dict) else None

    def point_distance(left: Any, right: Any) -> float | None:
        if not (
            isinstance(left, list)
            and len(left) >= 2
            and isinstance(right, list)
            and len(right) >= 2
            and all(isinstance(value, (int, float)) for value in left[:2])
            and all(isinstance(value, (int, float)) for value in right[:2])
        ):
            return None
        return hypot(float(left[0]) - float(right[0]), float(left[1]) - float(right[1]))

    intended_receiver = (
        details.get("intended_receiver", details.get("target_player_idx"))
        if isinstance(details, dict)
        else None
    )
    controller_idx = branch.get("controller_idx") if isinstance(branch, dict) else None
    return {
        "target": target,
        "target_kind": components.get("target_kind"),
        "intended_receiver_idx": intended_receiver,
        "receiver_release_pos": receiver_pos,
        "dominant_retained_controller_idx": controller_idx,
        "dominant_retained_controller_pos": controller_pos,
        "dominant_retained_controller_is_intended": (
            controller_idx == intended_receiver
            if isinstance(controller_idx, int) and isinstance(intended_receiver, int)
            else None
        ),
        "dominant_retained_conditional_probability": (
            branch.get("conditional_probability")
            if isinstance(branch, dict)
            else None
        ),
        "target_to_dominant_controller_m": point_distance(target, controller_pos),
        "receiver_release_to_target_m": point_distance(receiver_pos, target),
        "receiver_release_to_dominant_controller_m": point_distance(
            receiver_pos, controller_pos
        ),
    }


def _plan_delta_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    for entry in entries:
        provenance = str(entry.get("control_provenance") or "unknown")
        controller_team = str(entry.get("controller_team") or "unknown")
        counts["handoffs"] += 1
        counts[f"provenance={provenance}"] += 1
        for team in ("home", "away"):
            payload = entry.get(team)
            if not isinstance(payload, dict):
                continue
            relation = "controller" if team == controller_team else "defender"
            production = str(payload.get("production_plan") or "unknown")
            counterfactual = str(payload.get("counterfactual_plan") or "unknown")
            event_phase = str(payload.get("event_phase_counterfactual") or "unknown")
            event_plan = str(
                payload.get("event_phase_counterfactual_plan") or "unknown"
            )
            changed = production != counterfactual
            transition = f"{production}->{counterfactual}"
            for group in (relation, f"{provenance}:{relation}"):
                counts[f"{group}:updates"] += 1
                counts[f"{group}:plan_changed={str(changed).lower()}"] += 1
                counts[f"{group}:transition={transition}"] += 1
                counts[f"{group}:event_phase={event_phase}"] += 1
                counts[
                    f"{group}:event_phase_plan_changed_from_production={str(event_plan != production).lower()}"
                ] += 1
                counts[
                    f"{group}:event_phase_plan_changed_from_plan_only={str(event_plan != counterfactual).lower()}"
                ] += 1
                counts[
                    f"{group}:event_phase_transition={production}->{event_plan}"
                ] += 1
            production_signals = payload.get("production_signals", {})
            counterfactual_signals = payload.get("counterfactual_signals", {})
            event_phase_signals = payload.get(
                "event_phase_counterfactual_signals", {}
            )
            for field in (
                "forward_bias",
                "recycle_bias",
                "switch_bias",
                "tempo",
                "risk_budget",
            ):
                before = production_signals.get(field)
                after = counterfactual_signals.get(field)
                if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                    metrics[f"{provenance}:{relation}:{field}_delta"].append(
                        float(after) - float(before)
                    )
                event_after = event_phase_signals.get(field)
                if isinstance(before, (int, float)) and isinstance(
                    event_after, (int, float)
                ):
                    metrics[
                        f"{provenance}:{relation}:event_phase:{field}_delta"
                    ].append(float(event_after) - float(before))
                if isinstance(after, (int, float)) and isinstance(
                    event_after, (int, float)
                ):
                    metrics[
                        f"{provenance}:{relation}:event_phase_minus_plan_only:{field}"
                    ].append(float(event_after) - float(after))
    return {
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
    }


def _plan_payload_signature(payload: Any) -> tuple[Any, ...] | None:
    if not isinstance(payload, dict):
        return None
    signals = payload.get("counterfactual_signals", {})
    return (
        payload.get("counterfactual_plan"),
        *(
            signals.get(field)
            for field in (
                "forward_bias",
                "recycle_bias",
                "switch_bias",
                "tempo",
                "risk_budget",
            )
        ),
    )


def _signal_delta(
    current_payload: Any, prior_payload: Any
) -> tuple[bool, float] | None:
    if not isinstance(current_payload, dict) or not isinstance(prior_payload, dict):
        return None
    current = current_payload.get("counterfactual_signals", {})
    prior = prior_payload.get("counterfactual_signals", {})
    fields = (
        "forward_bias",
        "recycle_bias",
        "switch_bias",
        "tempo",
        "risk_budget",
    )
    if not all(
        isinstance(current.get(field), (int, float))
        and isinstance(prior.get(field), (int, float))
        for field in fields
    ):
        return None
    maximum = max(abs(float(current[field]) - float(prior[field])) for field in fields)
    return maximum <= 1e-12, maximum


def _prior_shadow_overlap(trace_entries: list[dict[str, Any]]) -> dict[str, Any]:
    latest_free_ball_by_tick: dict[Any, dict[str, Any]] = {}
    latest_flight_by_replay: dict[Any, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    for entry in trace_entries:
        event = entry.get("event")
        if event == "free_ball_current_observation_team_plan_counterfactual":
            latest_free_ball_by_tick[entry.get("tick")] = entry
            continue
        if event == "flight_current_observation_team_plan_counterfactual":
            latest_flight_by_replay[entry.get("replay_id")] = entry
            continue
        if event != "stable_control_team_plan_counterfactual":
            continue
        provenance = str(entry.get("control_provenance") or "unknown")
        comparisons = {
            "same_tick_free_ball": latest_free_ball_by_tick.get(entry.get("tick")),
            "terminal_flight": latest_flight_by_replay.get(
                entry.get("pending_pass_replay_id")
            ),
        }
        for source, prior in comparisons.items():
            counts[f"{source}:eligible"] += int(prior is not None)
            counts[f"{source}:missing"] += int(prior is None)
            if prior is None:
                continue
            all_equal = True
            both_plans_equal = True
            for team in ("home", "away"):
                current_payload = entry.get(team)
                prior_payload = prior.get(team)
                equal = _plan_payload_signature(current_payload) == _plan_payload_signature(
                    prior_payload
                )
                plan_equal = (
                    current_payload.get("counterfactual_plan")
                    == prior_payload.get("counterfactual_plan")
                    if isinstance(current_payload, dict) and isinstance(prior_payload, dict)
                    else False
                )
                signal_delta = _signal_delta(
                    current_payload,
                    prior.get(team)
                )
                counts[f"{source}:{team}:exact_plan_and_signals={str(equal).lower()}"] += 1
                counts[f"{source}:{team}:plan_equal={str(plan_equal).lower()}"] += 1
                counts[
                    f"{source}:{provenance}:{team}:exact_plan_and_signals={str(equal).lower()}"
                ] += 1
                counts[
                    f"{source}:{provenance}:{team}:plan_equal={str(plan_equal).lower()}"
                ] += 1
                if signal_delta is not None:
                    signals_equal, maximum_delta = signal_delta
                    counts[
                        f"{source}:{team}:signals_equal={str(signals_equal).lower()}"
                    ] += 1
                    metrics[f"{source}:{provenance}:{team}:max_signal_delta"].append(
                        maximum_delta
                    )
                all_equal &= equal
                both_plans_equal &= plan_equal
            counts[f"{source}:both_teams_exact={str(all_equal).lower()}"] += 1
            counts[
                f"{source}:both_team_plans_equal={str(both_plans_equal).lower()}"
            ] += 1
            counts[
                f"{source}:{provenance}:both_teams_exact={str(all_equal).lower()}"
            ] += 1
            counts[
                f"{source}:{provenance}:both_team_plans_equal={str(both_plans_equal).lower()}"
            ] += 1
    return {
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
    }


def _pending_pass_plan_lifecycle(trace_entries: list[dict[str, Any]]) -> dict[str, Any]:
    updates = {
        (entry.get("tick"), entry.get("team")): entry
        for entry in trace_entries
        if entry.get("event") == "team_plan_update"
        and entry.get("team") in {"home", "away"}
    }
    stable_by_replay = {
        entry.get("pending_pass_replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "stable_control_team_plan_counterfactual"
        and entry.get("pending_pass_replay_id") is not None
    }
    terminal_by_replay = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_control_terminal"
        and entry.get("replay_id") is not None
    }
    ticks_by_replay: dict[Any, list[int]] = defaultdict(list)
    for entry in trace_entries:
        if entry.get("event") != "pending_pass_team_phase_counterfactual":
            continue
        replay_id = entry.get("replay_id")
        tick = entry.get("tick")
        if replay_id is not None and isinstance(tick, int):
            ticks_by_replay[replay_id].append(tick)

    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    cases: list[dict[str, Any]] = []
    for replay_id, replay_ticks in ticks_by_replay.items():
        replay_ticks = sorted(set(replay_ticks))
        terminal = terminal_by_replay.get(replay_id, {})
        stable = stable_by_replay.get(replay_id)
        outcome = str(terminal.get("outcome") or "unresolved")
        provenance = (
            str(stable.get("control_provenance") or "unknown")
            if isinstance(stable, dict)
            else outcome
        )
        counts["replays"] += 1
        counts[f"outcome={outcome}"] += 1
        counts[f"provenance={provenance}"] += 1
        metrics["free_ball_plan_update_frames"].append(float(len(replay_ticks)))
        case: dict[str, Any] = {
            "replay_id": replay_id,
            "outcome": outcome,
            "provenance": provenance,
            "first_tick": replay_ticks[0],
            "last_tick": replay_ticks[-1],
            "frames": len(replay_ticks),
            "teams": {},
        }
        for team in ("home", "away"):
            rows = [
                updates[(tick, team)]
                for tick in replay_ticks
                if (tick, team) in updates
            ]
            if not rows:
                counts[f"{team}:missing_updates"] += 1
                continue
            initial = rows[0].get("prior", {})
            selected = [str(row.get("selected") or "unknown") for row in rows]
            final = rows[-1]
            initial_kind = str(initial.get("kind") or "unknown")
            final_kind = selected[-1]
            initial_commitment = initial.get("commitment")
            final_commitment = final.get("selected_commitment")
            switches = sum(
                left != right
                for left, right in zip([initial_kind, *selected[:-1]], selected)
            )
            kind_changed = initial_kind != final_kind
            group = f"{provenance}:{team}"
            counts[f"{team}:observed"] += 1
            counts[f"{team}:kind_changed={str(kind_changed).lower()}"] += 1
            counts[f"{team}:switches={switches}"] += 1
            counts[f"{group}:kind_changed={str(kind_changed).lower()}"] += 1
            counts[f"{group}:had_any_switch={str(switches > 0).lower()}"] += 1
            metrics[f"{group}:switches"].append(float(switches))
            team_case: dict[str, Any] = {
                "initial_kind": initial_kind,
                "final_kind": final_kind,
                "switches": switches,
            }
            if isinstance(initial_commitment, (int, float)) and isinstance(
                final_commitment, (int, float)
            ):
                delta = float(final_commitment) - float(initial_commitment)
                absolute_delta = abs(delta)
                metrics[f"{group}:commitment_delta"].append(delta)
                metrics[f"{group}:absolute_commitment_delta"].append(absolute_delta)
                counts[
                    f"{group}:commitment_changed={str(absolute_delta > 1e-12).lower()}"
                ] += 1
                team_case.update(
                    initial_commitment=float(initial_commitment),
                    final_commitment=float(final_commitment),
                    commitment_delta=delta,
                )
            if isinstance(stable, dict) and isinstance(stable.get(team), dict):
                stable_production = str(
                    stable[team].get("production_plan") or "unknown"
                )
                counts[
                    f"{group}:stable_production_matches_final={str(stable_production == final_kind).lower()}"
                ] += 1
                team_case["stable_production_kind"] = stable_production
            case["teams"][team] = team_case
        cases.append(case)

    return {
        "scope": (
            "read-only lifecycle of normal team-plan updates during pending-pass FreeBall "
            "frames, from the first update prior state through the final pre-settlement "
            "selected state; no phase, plan, movement, or RNG is changed"
        ),
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "cases": cases[:40],
    }


def _control_acquisition_lifecycle(
    trace_entries: list[dict[str, Any]],
    trace_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join stable control provenance to its first decision and pass outcome."""
    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    cases: list[dict[str, Any]] = []
    event_rows = [
        entry
        for entry in trace_entries
        if isinstance(entry.get("tick"), int)
    ]
    decisions_by_possession: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for decision in trace_decisions:
        possession_id = decision.get("possession_id")
        if isinstance(possession_id, int):
            decisions_by_possession[possession_id].append(decision)
    for rows in decisions_by_possession.values():
        rows.sort(key=lambda row: int(row.get("tick", -1)))

    release_possession_by_replay: dict[Any, int] = {}
    completed_passes_by_possession: Counter[int] = Counter()
    for entry in trace_entries:
        if entry.get("action") == "pass":
            replay_id = entry.get("replay_id")
            possession_id = entry.get("possession_id")
            if replay_id is not None and isinstance(possession_id, int):
                release_possession_by_replay[replay_id] = possession_id
    for entry in trace_entries:
        if (
            entry.get("event") == "pass_control_terminal"
            and entry.get("outcome") == "completed"
        ):
            possession_id = release_possession_by_replay.get(entry.get("replay_id"))
            if isinstance(possession_id, int):
                completed_passes_by_possession[possession_id] += 1

    for entry in trace_entries:
        if entry.get("event") != "ball_controlled":
            continue
        possession_id = entry.get("possession_id")
        tick = entry.get("tick")
        team = entry.get("team")
        player_idx = entry.get("player_idx")
        provenance = str(entry.get("control_provenance") or "unknown")
        if not (
            isinstance(possession_id, int)
            and isinstance(tick, int)
            and team in {"home", "away"}
            and isinstance(player_idx, int)
        ):
            continue
        first_decision = next(
            (
                decision
                for decision in decisions_by_possession.get(possession_id, [])
                if decision.get("team") == team
                and decision.get("player_idx") == player_idx
                and isinstance(decision.get("tick"), int)
                and int(decision["tick"]) >= tick
            ),
            None,
        )
        first_action = str(
            first_decision.get("chosen", {}).get("action_type") or "missing"
        ) if isinstance(first_decision, dict) else "missing"
        completed_passes = completed_passes_by_possession[possession_id]
        group = provenance
        counts["acquisitions"] += 1
        counts[f"provenance={group}"] += 1
        counts[f"{group}:first_action={first_action}"] += 1
        counts[
            f"{group}:completed_passes={'zero' if completed_passes == 0 else 'positive'}"
        ] += 1
        metrics[f"{group}:completed_passes"].append(float(completed_passes))
        if isinstance(first_decision, dict):
            metrics[f"{group}:ticks_to_first_decision"].append(
                float(int(first_decision["tick"]) - tick)
            )
        live = entry.get("live_control", {})
        counterfactual = entry.get("pass_arrival_control_counterfactual")
        local_contact_counterfactual = entry.get(
            "local_contact_control_counterfactual"
        )
        if isinstance(live, dict):
            for field in (
                "pressure_load",
                "forward_control",
                "turn_readiness",
                "release_window",
                "shape_readiness",
                "release_preparation",
                "continuation_control_readiness",
                "shot_release_readiness",
            ):
                value = live.get(field)
                if isinstance(value, (int, float)):
                    metrics[f"{group}:live:{field}"].append(float(value))
                    counterfactual_value = (
                        counterfactual.get(field)
                        if isinstance(counterfactual, dict)
                        else None
                    )
                    if isinstance(counterfactual_value, (int, float)):
                        counts[f"{group}:pass_arrival_counterfactual"] += int(
                            field == "continuation_control_readiness"
                        )
                        metrics[f"{group}:counterfactual:{field}"].append(
                            float(counterfactual_value)
                        )
                        metrics[f"{group}:counterfactual_minus_live:{field}"].append(
                            float(counterfactual_value) - float(value)
                        )
                    local_contact_value = (
                        local_contact_counterfactual.get(field)
                        if isinstance(local_contact_counterfactual, dict)
                        else None
                    )
                    if isinstance(local_contact_value, (int, float)):
                        counts[f"{group}:local_contact_counterfactual"] += int(
                            field == "continuation_control_readiness"
                        )
                        metrics[f"{group}:local_contact:{field}"].append(
                            float(local_contact_value)
                        )
                        metrics[f"{group}:local_contact_minus_live:{field}"].append(
                            float(local_contact_value) - float(value)
                        )
        cases.append({
            "tick": tick,
            "possession_id": possession_id,
            "team": team,
            "player_idx": player_idx,
            "provenance": provenance,
            "first_action": first_action,
            "first_decision_tick": first_decision.get("tick")
            if isinstance(first_decision, dict) else None,
            "completed_passes": completed_passes,
            "live_control": live,
            "pass_arrival_control_counterfactual": counterfactual,
            "local_contact_control_counterfactual": local_contact_counterfactual,
            "nearby_events": [
                {
                    key: nearby.get(key)
                    for key in (
                        "tick", "type", "event", "action", "phase",
                        "team", "player_idx", "holder_idx", "defender_idx",
                        "winner", "loser", "outcome", "context",
                        "possession_id", "previous_possession_id",
                    )
                    if nearby.get(key) is not None
                }
                for nearby in event_rows
                if tick - 1 <= int(nearby["tick"]) <= tick + 2
                and (
                    nearby.get("possession_id") in {
                        possession_id,
                        entry.get("previous_possession_id"),
                    }
                    or nearby.get("event") in {
                        "duel", "tackle", "interception",
                        "pass_control_terminal", "ball_controlled",
                    }
                )
            ],
        })
    return {
        "scope": (
            "read-only join from each stable ball_controlled event to the first "
            "same-player on-ball decision in that team-control possession and the "
            "number of completed pass terminals released in the same possession"
        ),
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "cases": cases,
    }


def _tactical_possession_reversal_lifecycle(
    trace_entries: list[dict[str, Any]],
    trace_decisions: list[dict[str, Any]],
    tick_duration: float,
) -> dict[str, Any]:
    def completed_pass_band(count: int) -> str:
        return "0" if count == 0 else "1" if count == 1 else "2_4" if count <= 4 else "5_plus"

    def pass_distance_band(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "unknown"
        distance_m = float(value)
        return (
            "0_10m" if distance_m < 10.0
            else "10_20m" if distance_m < 20.0
            else "20_30m" if distance_m < 30.0
            else "30m_plus"
        )

    on_ball_decision_by_identity = {
        (decision.get("tick"), decision.get("team"), decision.get("player_idx")):
            decision
        for decision in trace_decisions
        if decision.get("phase") == "on_ball"
        and isinstance(decision.get("chosen"), dict)
    }

    """Measure every observed engine possession id and adjacent A-B-A reversals."""
    decisions_by_possession: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for decision in trace_decisions:
        possession_id = decision.get("possession_id")
        if isinstance(possession_id, int):
            decisions_by_possession[possession_id].append(decision)
    for rows in decisions_by_possession.values():
        rows.sort(key=lambda row: int(row.get("tick", -1)))
    releases_by_possession: dict[int, list[dict[str, Any]]] = defaultdict(list)
    terminals_by_replay: dict[Any, dict[str, Any]] = {}
    controls_by_possession: dict[int, list[dict[str, Any]]] = defaultdict(list)
    direct_acquisitions_by_possession: dict[int, list[dict[str, Any]]] = defaultdict(list)
    candidate_context_by_identity: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    rows_by_possession: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in trace_entries:
        if (
            entry.get("event") == "on_ball_candidate_counts"
            and isinstance(entry.get("tick"), int)
            and entry.get("team") in {"home", "away"}
            and isinstance(entry.get("player_idx"), int)
        ):
            candidate_context_by_identity[(
                entry.get("tick"), entry.get("team"), entry.get("player_idx")
            )] = entry
        if entry.get("action") == "pass" and entry.get("replay_id") is not None:
            possession_id = entry.get("possession_id")
            if isinstance(possession_id, int):
                releases_by_possession[possession_id].append(entry)
        elif (
            entry.get("event") == "pass_control_terminal"
            and entry.get("replay_id") is not None
        ):
            terminals_by_replay[entry.get("replay_id")] = entry
        possession_id = entry.get("possession_id")
        if isinstance(possession_id, int):
            rows_by_possession[possession_id].append(entry)
            if (
                entry.get("event") == "ball_controlled"
                and entry.get("team") in {"home", "away"}
            ):
                controls_by_possession[possession_id].append(entry)
        acquired_possession_id = entry.get("acquired_possession_id")
        if (
            isinstance(acquired_possession_id, int)
            and entry.get("acquisition_provenance")
            in {"direct_tackle_win", "direct_pressure_turnover"}
        ):
            direct_acquisitions_by_possession[acquired_possession_id].append(entry)

    possession_ids = sorted(
        set(decisions_by_possession)
        | set(releases_by_possession)
        | set(controls_by_possession)
        | set(rows_by_possession)
    )
    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    cases: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for possession_id in possession_ids:
        decisions = decisions_by_possession.get(possession_id, [])
        releases = releases_by_possession.get(possession_id, [])
        controls = controls_by_possession.get(possession_id, [])
        direct_acquisitions = direct_acquisitions_by_possession.get(possession_id, [])
        rows = rows_by_possession.get(possession_id, [])
        team_candidates = [
            row.get("team")
            for row in [*decisions, *releases, *controls]
            if row.get("team") in {"home", "away"}
        ]
        team = str(team_candidates[0]) if team_candidates else "unknown"
        tick_values = [
            int(row["tick"])
            for row in [*decisions, *releases, *controls, *rows]
            if isinstance(row.get("tick"), int)
        ]
        if not tick_values or team not in {"home", "away"}:
            continue
        start_tick = min(tick_values)
        end_tick = max(tick_values)
        decision_actions = [
            str(decision.get("chosen", {}).get("action_type") or "unknown")
            for decision in decisions
            if decision.get("team") == team
        ]
        compact_actions: list[str] = []
        for action in decision_actions:
            if not compact_actions or compact_actions[-1] != action:
                compact_actions.append(action)
        outcomes = [
            str(terminals_by_replay.get(release.get("replay_id"), {}).get("outcome") or "missing")
            for release in releases
        ]
        completed_passes = sum(outcome == "completed" for outcome in outcomes)
        completion_band = completed_pass_band(completed_passes)
        same_team_recoveries = sum(
            entry.get("event") == "ball_controlled"
            and entry.get("control_provenance") == "same_team_loose_recovery"
            for entry in controls
        )
        pass_group = "zero_pass" if completed_passes == 0 else "positive_pass"
        first_action = compact_actions[0] if compact_actions else "missing"
        counts["segments"] += 1
        counts[f"{pass_group}:segments"] += 1
        counts[f"{pass_group}:first_action={first_action}"] += 1
        counts[f"{pass_group}:released_passes={len(releases)}"] += 1
        counts[f"{pass_group}:same_team_recoveries={same_team_recoveries}"] += 1
        counts[f"completed_band={completion_band}:segments"] += 1
        counts[f"completed_band={completion_band}:first_action={first_action}"] += 1
        duration_ticks = max(end_tick - start_tick, 0)
        metrics[f"{pass_group}:duration_ticks"].append(float(duration_ticks))
        metrics[f"{pass_group}:duration_seconds"].append(
            float(duration_ticks) * tick_duration
        )
        metrics[f"{pass_group}:decision_count"].append(float(len(decisions)))
        metrics[f"{pass_group}:released_passes"].append(float(len(releases)))
        metrics[f"{pass_group}:same_team_recoveries"].append(
            float(same_team_recoveries)
        )
        metrics[f"completed_band={completion_band}:duration_seconds"].append(
            float(duration_ticks) * tick_duration
        )
        release_rows = []
        for release, outcome in zip(releases, outcomes):
            distance_m = release.get("actual_distance_m")
            row = {
                "replay_id": release.get("replay_id"),
                "tick": release.get("tick"),
                "distance_m": distance_m,
                "distance_band": pass_distance_band(distance_m),
                "target_kind": release.get("target_kind"),
                "retention_probability": release.get("retention_probability"),
                "predicted_retained_control_probability": release.get(
                    "predicted_retained_control_probability"
                ),
                "predicted_opposing_control_probability": release.get(
                    "predicted_opposing_control_probability"
                ),
                "predicted_unresolved_probability": release.get(
                    "predicted_unresolved_probability"
                ),
                "predicted_out_of_play_probability": release.get(
                    "predicted_out_of_play_probability"
                ),
                "lane_risk": release.get("lane_risk"),
                "receiver_pressure": release.get("receiver_pressure"),
                "outcome": outcome,
            }
            release_rows.append(row)
        for ordinal, release_row in enumerate(release_rows[:3], 1):
            prefix = f"completed_band={completion_band}:pass_ordinal={ordinal}"
            counts[f"{prefix}:distance={release_row['distance_band']}"] += 1
            counts[f"{prefix}:outcome={release_row['outcome']}"] += 1
            counts[
                f"{prefix}:distance={release_row['distance_band']}:"
                f"outcome={release_row['outcome']}"
            ] += 1
            if isinstance(release_row["distance_m"], (int, float)):
                metrics[f"{prefix}:distance_m"].append(
                    float(release_row["distance_m"])
                )
            release = releases[ordinal - 1]
            context = candidate_context_by_identity.get((
                release.get("tick"), release.get("team"), release.get("passer_player")
            ), {})
            holder_pos = context.get("player_pos")
            physical_distances = []
            for teammate in context.get("teammate_goals", []):
                teammate_pos = teammate.get("pos") if isinstance(teammate, dict) else None
                if (
                    isinstance(holder_pos, list)
                    and len(holder_pos) >= 2
                    and isinstance(teammate_pos, list)
                    and len(teammate_pos) >= 2
                ):
                    physical_distances.append(hypot(
                        float(teammate_pos[0]) - float(holder_pos[0]),
                        float(teammate_pos[1]) - float(holder_pos[1]),
                    ))
            belief = context.get("belief_teammates", {})
            pass_count = context.get("pass_count")
            nearest_physical = min(physical_distances) if physical_distances else None
            for field, value in (
                ("nearest_physical_teammate_m", nearest_physical),
                ("physical_teammates_within_10m", sum(
                    distance_m < 10.0 for distance_m in physical_distances
                )),
                ("belief_teammates_within_10m", belief.get("within_10m") if isinstance(belief, dict) else None),
                ("pass_candidate_count", pass_count),
            ):
                if isinstance(value, (int, float)):
                    metrics[f"{prefix}:{field}"].append(float(value))
            if isinstance(nearest_physical, (int, float)):
                counts[
                    f"{prefix}:physical_nearby=true"
                    if nearest_physical < 10.0
                    else f"{prefix}:physical_nearby=false"
                ] += 1
            if isinstance(belief, dict) and isinstance(belief.get("within_10m"), int):
                counts[
                    f"{prefix}:belief_nearby=true"
                    if int(belief["within_10m"]) > 0
                    else f"{prefix}:belief_nearby=false"
                ] += 1
            release_row["candidate_funnel"] = {
                "nearest_physical_teammate_m": nearest_physical,
                "physical_teammates_within_10m": sum(
                    distance_m < 10.0 for distance_m in physical_distances
                ),
                "belief_teammates_within_10m": (
                    belief.get("within_10m") if isinstance(belief, dict) else None
                ),
                "pass_candidate_count": pass_count,
            }
            decision = on_ball_decision_by_identity.get((
                release.get("tick"), release.get("team"), release.get("passer_player")
            ), {})
            chosen = decision.get("chosen", {}) if isinstance(decision, dict) else {}
            origin = release.get("origin")
            release_row["team_plan_kind"] = decision.get("team_plan_kind")
            release_row["control"] = decision.get("control")
            release_row["trajectory"] = release.get("trajectory")
            release_row["chosen_failed_delivery_quadrature"] = decision.get(
                "chosen_failed_delivery_quadrature"
            )
            release_row["sampled_endpoint_projection"] = release.get(
                "sampled_endpoint_projection"
            )
            release_row["chosen_source"] = chosen.get("source")
            release_row["chosen_target_kind"] = (
                chosen.get("value", {}).get("components", {}).get("target_kind")
            )
            release_row["chosen_direction"] = (
                "forward"
                if isinstance(origin, list)
                and len(origin) >= 2
                and isinstance(chosen.get("target"), list)
                and len(chosen["target"]) >= 2
                and (float(chosen["target"][0]) - float(origin[0]))
                    * (1.0 if decision.get("attacking_right") else -1.0) > 1e-9
                else "backward"
                if isinstance(origin, list)
                and len(origin) >= 2
                and isinstance(chosen.get("target"), list)
                and len(chosen["target"]) >= 2
                and (float(chosen["target"][0]) - float(origin[0]))
                    * (1.0 if decision.get("attacking_right") else -1.0) < -1e-9
                else "lateral"
            )
            chosen_ledger_for_release = (
                _bellman_candidate_ledger(chosen, origin)
                if isinstance(chosen, dict) else {}
            )
            release_row["chosen_ledger"] = chosen_ledger_for_release
            release_row["chosen_successor_endpoint"] = (
                _candidate_successor_endpoint(chosen)
            )
            chosen_receiver_idx = chosen.get("details", {}).get(
                "intended_receiver",
                chosen.get("details", {}).get("target_player_idx"),
            )
            same_receiver_feet_candidates = [
                candidate
                for candidate in [chosen, *decision.get("alternatives", [])]
                if isinstance(candidate, dict)
                and candidate.get("action_type") == "pass"
                and candidate.get("value", {}).get("components", {}).get(
                    "target_kind"
                ) == "feet"
                and candidate.get("details", {}).get(
                    "intended_receiver",
                    candidate.get("details", {}).get("target_player_idx"),
                ) == chosen_receiver_idx
                and isinstance(candidate.get("value", {}).get("score"), (int, float))
            ]
            best_same_receiver_feet = (
                max(
                    same_receiver_feet_candidates,
                    key=lambda candidate: float(candidate["value"]["score"]),
                )
                if same_receiver_feet_candidates else None
            )
            same_receiver_feet_ledger = (
                _bellman_candidate_ledger(best_same_receiver_feet, origin)
                if isinstance(best_same_receiver_feet, dict) else {}
            )
            release_row["same_receiver_feet_pair"] = {
                "receiver_idx": chosen_receiver_idx,
                "exists": best_same_receiver_feet is not None,
                "target": (
                    best_same_receiver_feet.get("target")
                    if isinstance(best_same_receiver_feet, dict) else None
                ),
                "ledger": same_receiver_feet_ledger,
                "successor_endpoint": _candidate_successor_endpoint(
                    best_same_receiver_feet
                ),
                "feet_minus_chosen": {
                    field: same_receiver_feet_ledger[field]
                    - chosen_ledger_for_release[field]
                    for field in same_receiver_feet_ledger.keys()
                    & chosen_ledger_for_release.keys()
                },
            }
            plan_signals = TEAM_PLAN_SIGNALS.get(str(decision.get("team_plan_kind")))
            direct_policy_candidates = []
            if isinstance(plan_signals, dict):
                for candidate in [chosen, *decision.get("alternatives", [])]:
                    if not isinstance(candidate, dict) or candidate.get("action_type") != "pass":
                        continue
                    components = candidate.get("value", {}).get("components", {})
                    transition = components.get("outcome_transition", {})
                    direct_probability = transition.get("direct_retained_probability")
                    total_probability = transition.get("retained_control_probability")
                    if not isinstance(direct_probability, (int, float)) or not isinstance(
                        total_probability, (int, float)
                    ):
                        continue
                    production_decomposition = _team_plan_pass_policy_decomposition(
                        candidate,
                        origin,
                        attacking_right=bool(decision.get("attacking_right")),
                        signals=plan_signals,
                    )
                    decomposition = _team_plan_pass_policy_decomposition(
                        candidate,
                        origin,
                        attacking_right=bool(decision.get("attacking_right")),
                        signals=plan_signals,
                        success_probability_override=float(direct_probability),
                        continuation_probability_override=float(total_probability),
                    )
                    if not isinstance(production_decomposition, dict) or not isinstance(
                        decomposition, dict
                    ):
                        continue
                    production_score = candidate.get("value", {}).get("score")
                    production_team_plan_policy = production_decomposition.get(
                        "team_plan_policy_value"
                    )
                    counterfactual_team_plan_policy = decomposition.get(
                        "team_plan_policy_value"
                    )
                    if not all(
                        isinstance(value, (int, float))
                        for value in (
                            production_score,
                            production_team_plan_policy,
                            counterfactual_team_plan_policy,
                        )
                    ):
                        continue
                    counterfactual_score = float(production_score) + (
                        float(counterfactual_team_plan_policy)
                        - float(production_team_plan_policy)
                    )
                    direct_policy_candidates.append({
                        "receiver_idx": candidate.get("details", {}).get(
                            "intended_receiver",
                            candidate.get("details", {}).get("target_player_idx"),
                        ),
                        "target": candidate.get("target"),
                        "target_kind": components.get("target_kind"),
                        "production_score": float(production_score),
                        "counterfactual_score": counterfactual_score,
                        "direct_retained_probability": float(direct_probability),
                        "total_retained_probability": float(total_probability),
                        "decomposition": decomposition,
                        "production_decomposition": production_decomposition,
                    })
            best_direct_policy = (
                max(direct_policy_candidates, key=lambda row: row["counterfactual_score"])
                if direct_policy_candidates else None
            )
            release_row["direct_intended_receipt_policy_shadow"] = {
                "scope": (
                    "read-only Pass-pool rerank; Bellman outcome, total team-retention "
                    "continuation, goal-policy residual, family selection, execution, and RNG "
                    "remain unchanged; only TeamPlan retention uses intended-receipt "
                    "probability times total team-retention probability"
                ),
                "best": best_direct_policy,
                "changes_from_chosen": (
                    isinstance(best_direct_policy, dict)
                    and (
                        best_direct_policy.get("target") != chosen.get("target")
                        or best_direct_policy.get("receiver_idx") != chosen_receiver_idx
                    )
                ),
                "candidates": direct_policy_candidates,
            }
            chosen_score = chosen.get("value", {}).get("score")
            near_feet_candidates = []
            for candidate in [chosen, *decision.get("alternatives", [])]:
                if not isinstance(candidate, dict) or candidate.get("action_type") != "pass":
                    continue
                target = candidate.get("target")
                components = candidate.get("value", {}).get("components", {})
                if not (
                    isinstance(origin, list)
                    and len(origin) >= 2
                    and isinstance(target, list)
                    and len(target) >= 2
                    and components.get("target_kind") == "feet"
                ):
                    continue
                candidate_distance = hypot(
                    float(target[0]) - float(origin[0]),
                    float(target[1]) - float(origin[1]),
                )
                if candidate_distance >= 10.0:
                    continue
                score = candidate.get("value", {}).get("score")
                retention = candidate.get("value", {}).get("success_prob")
                if not isinstance(score, (int, float)):
                    continue
                near_feet_candidates.append({
                    "receiver_idx": candidate.get("details", {}).get(
                        "intended_receiver",
                        candidate.get("details", {}).get("target_player_idx"),
                    ),
                    "distance_m": candidate_distance,
                    "score": float(score),
                    "retention": retention,
                    "target": target,
                })
            best_near_feet = (
                max(near_feet_candidates, key=lambda candidate: candidate["score"])
                if near_feet_candidates else None
            )
            prefix = f"completed_band={completion_band}:pass_ordinal={ordinal}"
            counts[
                f"{prefix}:with_near_feet_candidate"
                if best_near_feet is not None
                else f"{prefix}:without_near_feet_candidate"
            ] += 1
            if isinstance(best_near_feet, dict):
                metrics[f"{prefix}:best_near_feet_distance_m"].append(
                    float(best_near_feet["distance_m"])
                )
                retention = best_near_feet.get("retention")
                if isinstance(retention, (int, float)):
                    metrics[f"{prefix}:best_near_feet_retention"].append(
                        float(retention)
                    )
                if isinstance(chosen_score, (int, float)):
                    gap = float(best_near_feet["score"]) - float(chosen_score)
                    metrics[f"{prefix}:best_near_feet_minus_chosen_score"].append(gap)
                    counts[
                        f"{prefix}:near_feet_beats_chosen"
                        if gap > 0.0
                        else f"{prefix}:near_feet_does_not_beat_chosen"
                    ] += 1
            best_near_candidate = next(
                (
                    candidate
                    for candidate in [chosen, *decision.get("alternatives", [])]
                    if isinstance(best_near_feet, dict)
                    and isinstance(candidate, dict)
                    and candidate.get("action_type") == "pass"
                    and candidate.get("target") == best_near_feet.get("target")
                    and candidate.get("details", {}).get(
                        "intended_receiver",
                        candidate.get("details", {}).get("target_player_idx"),
                    ) == best_near_feet.get("receiver_idx")
                ),
                None,
            )
            near_ledger = (
                _bellman_candidate_ledger(best_near_candidate, origin)
                if isinstance(best_near_candidate, dict) else {}
            )
            chosen_ledger = (
                _bellman_candidate_ledger(chosen, origin)
                if isinstance(chosen, dict) else {}
            )
            ledger_delta = {
                field: near_ledger[field] - chosen_ledger[field]
                for field in near_ledger.keys() & chosen_ledger.keys()
            }
            for field, value in ledger_delta.items():
                metrics[f"{prefix}:near_minus_chosen:{field}"].append(float(value))
            release_row["near_feet_pair"] = {
                "chosen_action": chosen.get("action_type"),
                "chosen_score": chosen_score,
                "best_near_feet": best_near_feet,
                "best_near_feet_minus_chosen_score": (
                    float(best_near_feet["score"]) - float(chosen_score)
                    if isinstance(best_near_feet, dict)
                    and isinstance(chosen_score, (int, float))
                    else None
                ),
                "near_ledger": near_ledger,
                "chosen_ledger": chosen_ledger,
                "near_minus_chosen_ledger": ledger_delta,
            }
        first_opponent_gain = next(
            (
                entry
                for entry in controls
                if entry.get("control_provenance") == "opponent_control_gain"
            ),
            None,
        )
        direct_acquisition = direct_acquisitions[0] if direct_acquisitions else None
        acquisition_provenance = (
            str(direct_acquisition.get("acquisition_provenance"))
            if isinstance(direct_acquisition, dict)
            else str(first_opponent_gain.get("control_provenance"))
            if isinstance(first_opponent_gain, dict)
            else "restart_or_unobserved"
        )
        live = (
            direct_acquisition.get("acquisition_live_control", {})
            if isinstance(direct_acquisition, dict)
            else
            first_opponent_gain.get("live_control", {})
            if isinstance(first_opponent_gain, dict)
            else {}
        )
        counts[f"{pass_group}:acquisition={acquisition_provenance}"] += 1
        counts[
            f"completed_band={completion_band}:acquisition={acquisition_provenance}"
        ] += 1
        if isinstance(live, dict):
            for field in (
                "continuation_control_readiness",
                "pressure_load",
                "release_preparation",
                "turn_readiness",
                "release_window",
            ):
                value = live.get(field)
                if isinstance(value, (int, float)):
                    metrics[f"{pass_group}:acquisition_{field}"].append(float(value))
        segment = {
            "start_tick": start_tick,
            "end_tick": end_tick,
            "duration_ticks": duration_ticks,
            "possession_id": possession_id,
            "team": team,
            "completed_passes": completed_passes,
            "completed_pass_band": completion_band,
            "released_passes": len(releases),
            "pass_outcomes": outcomes,
            "pass_releases": release_rows,
            "decision_count": len(decisions),
            "action_path": compact_actions,
            "same_team_loose_recoveries": same_team_recoveries,
            "acquisition_live_control": live,
            "acquisition_provenance": acquisition_provenance,
            "acquisition_event": direct_acquisition or first_opponent_gain,
        }
        if completed_passes == 0:
            direct_turnover = next(
                (
                    entry
                    for entry in rows
                    if entry.get("event") in {"tackle", "duel"}
                    and entry.get("outcome") == "defender_wins"
                    and entry.get("acquisition_provenance")
                    in {"direct_tackle_win", "direct_pressure_turnover"}
                ),
                None,
            )
            termination_profile = (
                "released_pass"
                if releases
                else "pass_release_duel_turnover"
                if isinstance(direct_turnover, dict)
                and direct_turnover.get("context") == "pass_release"
                else "direct_tackle_turnover"
                if isinstance(direct_turnover, dict)
                and direct_turnover.get("acquisition_provenance")
                == "direct_tackle_win"
                else "direct_pressure_turnover"
                if isinstance(direct_turnover, dict)
                else "shot"
                if "shoot" in compact_actions
                else "clearance"
                if "clear" in compact_actions
                else "restart_only"
                if any(
                    entry.get("event") == "restart" for entry in rows
                )
                else "no_formal_release"
            )
            segment["zero_pass_termination_profile"] = termination_profile
            segment["zero_pass_direct_turnover"] = direct_turnover
            counts[f"zero_pass:termination={termination_profile}"] += 1
        segments.append(segment)

    for index, segment in enumerate(segments):
        previous = segments[index - 1] if index > 0 else None
        following = segments[index + 1] if index + 1 < len(segments) else None
        aba = (
            isinstance(previous, dict)
            and isinstance(following, dict)
            and previous["team"] == following["team"]
            and segment["team"] != previous["team"]
        )
        segment["aba_middle_reversal"] = aba
        segment["previous_team"] = previous["team"] if previous else None
        segment["next_team"] = following["team"] if following else None
        pass_group = (
            "zero_pass" if segment["completed_passes"] == 0 else "positive_pass"
        )
        counts[f"{pass_group}:aba_middle={str(aba).lower()}"] += 1
        if aba:
            metrics[f"{pass_group}:aba_middle_duration_ticks"].append(
                float(segment["duration_ticks"])
            )
            metrics[f"{pass_group}:aba_middle_duration_seconds"].append(
                float(segment["duration_ticks"]) * tick_duration
            )
            if pass_group == "zero_pass":
                profile = str(
                    segment.get("zero_pass_termination_profile") or "unknown"
                )
                counts[f"zero_pass:aba_middle:termination={profile}"] += 1
                counts[
                    f"zero_pass:aba_middle:acquisition={segment.get('acquisition_provenance')}"
                ] += 1
                counts[
                    f"zero_pass:aba_middle:acquisition={segment.get('acquisition_provenance')}:"
                    f"termination={profile}"
                ] += 1
                metrics[
                    f"zero_pass:aba_middle:termination={profile}:duration_ticks"
                ].append(float(segment["duration_ticks"]))
        cases.append(segment)

    aligned_segments: list[dict[str, Any]] = []
    aligned_counts: Counter[str] = Counter()
    aligned_metrics: dict[str, list[float]] = defaultdict(list)
    for segment in cases:
        if aligned_segments and aligned_segments[-1]["team"] == segment["team"]:
            merged = aligned_segments[-1]
            aligned_counts["adjacent_same_team_segments_merged"] += 1
            merged["source_possession_ids"].append(segment["possession_id"])
            merged["end_tick"] = max(merged["end_tick"], segment["end_tick"])
            merged["duration_ticks"] = max(
                merged["end_tick"] - merged["start_tick"], 0
            )
            merged["completed_passes"] += segment["completed_passes"]
            merged["released_passes"] += segment["released_passes"]
            merged["pass_outcomes"].extend(segment["pass_outcomes"])
            merged["pass_releases"].extend(segment["pass_releases"])
            merged["decision_count"] += segment["decision_count"]
            merged["action_path"].extend(segment["action_path"])
            merged["same_team_loose_recoveries"] += segment[
                "same_team_loose_recoveries"
            ]
            continue
        aligned = copy.deepcopy(segment)
        aligned["source_possession_ids"] = [segment["possession_id"]]
        aligned_segments.append(aligned)

    for segment in aligned_segments:
        completed = int(segment["completed_passes"])
        band = completed_pass_band(completed)
        segment["completed_pass_band"] = band
        aligned_counts["segments"] += 1
        aligned_counts[f"completed_band={band}:segments"] += 1
        aligned_counts[
            f"completed_band={band}:attempted={segment['released_passes']}"
        ] += 1
        aligned_metrics["completed_passes"].append(float(completed))
        aligned_metrics["attempted_passes"].append(
            float(segment["released_passes"])
        )
        aligned_metrics["duration_seconds"].append(
            float(segment["duration_ticks"]) * tick_duration
        )
        aligned_metrics[f"completed_band={band}:completed_passes"].append(
            float(completed)
        )
        aligned_metrics[f"completed_band={band}:attempted_passes"].append(
            float(segment["released_passes"])
        )
        aligned_metrics[f"completed_band={band}:duration_seconds"].append(
            float(segment["duration_ticks"]) * tick_duration
        )
        for ordinal, release in enumerate(segment["pass_releases"][:3], 1):
            distance_m = release.get("distance_m")
            if isinstance(distance_m, (int, float)):
                aligned_metrics[
                    f"completed_band={band}:pass_ordinal={ordinal}:distance_m"
                ].append(float(distance_m))
            aligned_counts[
                f"completed_band={band}:pass_ordinal={ordinal}:"
                f"outcome={release.get('outcome', 'unknown')}"
            ] += 1

    return {
        "scope": (
            "read-only lifecycle of every observed engine possession_id, with team identity "
            "resolved from same-id decisions, pass releases, or ball_controlled events and "
            "adjacent A-B-A reversals flagged; no duration threshold or merging rule is applied"
        ),
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "cases": cases,
        "provider_aligned_team_control_segments": {
            "scope": (
                "adjacent raw possession_id segments are merged while team identity "
                "stays unchanged, matching the StatsBomb team-control audit; no duration "
                "threshold is applied"
            ),
            "counts": dict(sorted(aligned_counts.items())),
            "metrics": {
                field: _distribution(values)
                for field, values in sorted(aligned_metrics.items())
                if values
            },
            "cases": aligned_segments,
        },
    }


def _pass_boundary_control_lifecycle(
    trace_entries: list[dict[str, Any]],
    pitch_length: float,
    pitch_width: float,
) -> dict[str, Any]:
    """Join pass release, physical contact, free control, and terminal outcome."""
    releases = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("action") == "pass" and entry.get("replay_id") is not None
    }
    physical_by_replay = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_physical_terminal"
        and entry.get("replay_id") is not None
    }
    terminal_by_replay = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_control_terminal"
        and entry.get("replay_id") is not None
    }
    controlled_by_replay = {
        entry.get("pending_pass_replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "ball_controlled"
        and entry.get("pending_pass_replay_id") is not None
    }
    continuous_by_replay: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    stable_budget_by_replay: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    material_contacts_by_replay: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    flight_observations_by_replay: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    continuous_out_by_replay: dict[Any, dict[str, Any]] = {}
    direct_out_by_tick: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in trace_entries:
        replay_id = entry.get("pending_pass_replay_id")
        event = entry.get("event")
        if event == "continuous_ball_control" and replay_id is not None:
            continuous_by_replay[replay_id].append(entry)
        elif event == "free_ball_stable_control_budget" and replay_id is not None:
            stable_budget_by_replay[replay_id].append(entry)
        elif (
            event == "pending_pass_opponent_material_contact"
            and entry.get("replay_id") is not None
        ):
            material_contacts_by_replay[entry.get("replay_id")].append(entry)
        elif (
            event == "flight_observed_destination"
            and entry.get("replay_id") is not None
        ):
            flight_observations_by_replay[entry.get("replay_id")].append(entry)
        elif event == "out_of_bounds" and entry.get("source") == "continuous_ball":
            if replay_id is not None:
                continuous_out_by_replay[replay_id] = entry
        elif (
            event == "out_of_bounds"
            and entry.get("source") == "flight"
            and isinstance(entry.get("tick"), int)
        ):
            direct_out_by_tick[int(entry["tick"])].append(entry)
    for rows in continuous_by_replay.values():
        rows.sort(
            key=lambda row: (
                int(row.get("tick", -1)),
                float(row.get("phase_tick_fraction", 0.0) or 0.0),
            )
        )
    for rows in flight_observations_by_replay.values():
        rows.sort(
            key=lambda row: (
                int(row.get("tick", -1)),
                float(row.get("elapsed_after", 0.0) or 0.0),
            )
        )

    def boundary_margin(point: Any) -> float | None:
        if not isinstance(point, list) or len(point) < 2:
            return None
        x, y = float(point[0]), float(point[1])
        return min(x, pitch_length - x, y, pitch_width - y)

    def margin_bucket(value: float | None) -> str:
        if value is None:
            return "unknown"
        if value < 1.0:
            return "under_1m"
        if value < 3.0:
            return "1_3m"
        if value < 5.0:
            return "3_5m"
        return "5m_plus"

    def distance_bucket(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "unknown"
        distance_m = float(value)
        if distance_m < 10.0:
            return "0_10m"
        if distance_m < 20.0:
            return "10_20m"
        if distance_m < 30.0:
            return "20_30m"
        return "30m_plus"

    def point_distance(left: Any, right: Any) -> float | None:
        if not (
            isinstance(left, list)
            and len(left) >= 2
            and isinstance(right, list)
            and len(right) >= 2
        ):
            return None
        return hypot(
            float(left[0]) - float(right[0]),
            float(left[1]) - float(right[1]),
        )

    def strongest_role(physical: dict[str, Any]) -> str:
        strongest_team = physical.get("strongest_contact_team")
        strongest_player = physical.get("strongest_contact_player")
        passer_team = physical.get("passer_team")
        if strongest_team is None:
            return "none"
        if strongest_team != passer_team:
            return "opponent"
        if strongest_player == physical.get("intended_receiver_player"):
            return "intended_receiver"
        if strongest_player == physical.get("passer_player"):
            return "passer"
        return "other_teammate"

    def material_deflection_role(physical: dict[str, Any]) -> str:
        deflection_team = physical.get("material_deflection_contact_team")
        deflection_player = physical.get("material_deflection_contact_player")
        passer_team = physical.get("passer_team")
        if deflection_team is None:
            return "none"
        if deflection_team != passer_team:
            return "opponent"
        if deflection_player == physical.get("intended_receiver_player"):
            return "intended_receiver"
        if deflection_player == physical.get("passer_player"):
            return "passer"
        return "other_teammate"

    def instability_reason(row: dict[str, Any] | None) -> str:
        if not isinstance(row, dict):
            return "no_observed_free_ball_phase"
        quality = row.get("strongest_contact_quality")
        post_speed = row.get("strongest_contact_post_relative_speed")
        winner = max(
            float(row.get("home_confidence", 0.0) or 0.0),
            float(row.get("away_confidence", 0.0) or 0.0),
        )
        opponent = min(
            float(row.get("home_confidence", 0.0) or 0.0),
            float(row.get("away_confidence", 0.0) or 0.0),
        )
        if not isinstance(quality, (int, float)):
            return "no_contact"
        if not isinstance(post_speed, (int, float)):
            return "contact_without_post_relative_speed"
        speed = float(post_speed)
        if speed > 6.5:
            return "post_relative_speed_above_6_5"
        if winner < 0.60:
            return "winning_claim_below_0_60"
        if opponent > 0.08 and winner < 0.72:
            return "contested_claim_below_0_72"
        if opponent > 0.08 and winner - opponent < 0.12:
            return "contested_claim_margin_below_0_12"
        if speed > 4.5:
            return "post_relative_speed_above_unopposed_4_5"
        return "other_or_unobservable_stability_condition"

    counts: Counter[str] = Counter()
    endpoint_projection_counts: Counter[str] = Counter()
    controller_task_counts: Counter[str] = Counter()
    controller_task_metrics: dict[str, list[float]] = defaultdict(list)
    controller_task_cases: list[dict[str, Any]] = []
    endpoint_profiles = (
        "production_targeting",
        "teammates_exact",
        "receiver_exact",
        "opponents_exact",
        "teammates_and_opponents_exact",
        "receiver_and_opponents_exact",
        "receiver_oriented",
        "hidden_target_blind",
    )
    metrics: dict[str, list[float]] = defaultdict(list)
    strata: dict[str, Counter[str]] = defaultdict(Counter)
    out_cases: list[dict[str, Any]] = []
    for replay_id, release in releases.items():
        terminal = terminal_by_replay.get(replay_id, {})
        physical = physical_by_replay.get(replay_id, {})
        controlled = controlled_by_replay.get(replay_id)
        phases = continuous_by_replay.get(replay_id, [])
        stable_budgets = stable_budget_by_replay.get(replay_id, [])
        outcome = str(terminal.get("outcome") or "unresolved")
        delivery = "error" if release.get("delivery_miss") else "clean"
        target_kind = str(release.get("target_kind") or "unknown")
        endpoint_projection = release.get("sampled_endpoint_projection")
        if isinstance(endpoint_projection, dict):
            endpoint_projection_counts["observed"] += 1
            production_stage = str(
                endpoint_projection.get("production_targeting", {}).get(
                    "resolution_stage"
                )
                or "unknown"
            )
            production_stable_retained = production_stage in {
                "arrival_stable_retained",
                "residual_stable_retained",
            }
            endpoint_projection_counts[
                f"actual={outcome}:production_stage={production_stage}"
            ] += 1
            endpoint_projection_counts[
                f"actual={outcome}:production_stable_retained="
                f"{str(production_stable_retained).lower()}"
            ] += 1
            for profile in endpoint_profiles:
                profile_stage = str(
                    endpoint_projection.get(profile, {}).get("resolution_stage")
                    or "unknown"
                )
                profile_stable_retained = profile_stage in {
                    "arrival_stable_retained",
                    "residual_stable_retained",
                }
                profile_payload = endpoint_projection.get(profile, {})
                retained_probability = profile_payload.get("retained_probability")
                opposing_probability = profile_payload.get("opposing_probability")
                unresolved_probability = profile_payload.get("unresolved_probability")
                out_of_play_probability = profile_payload.get("out_of_play_probability")
                if all(
                    isinstance(value, (int, float))
                    for value in (
                        retained_probability,
                        opposing_probability,
                        unresolved_probability,
                        out_of_play_probability,
                    )
                ):
                    ownership_target = {
                        "completed": (1.0, 0.0, 0.0),
                        "opposing_control": (0.0, 1.0, 0.0),
                        "loose": (0.0, 0.0, 1.0),
                        "out_of_play": (0.0, 0.0, 1.0),
                        "unresolved": (0.0, 0.0, 1.0),
                    }.get(outcome)
                    if ownership_target is not None:
                        ownership_brier = sum(
                            (float(predicted) - expected) ** 2
                            for predicted, expected in zip(
                                (
                                    retained_probability,
                                    opposing_probability,
                                    unresolved_probability,
                                ),
                                ownership_target,
                            )
                        )
                        metrics[
                            f"sampled_endpoint:actual={outcome}:profile={profile}:"
                            "ownership_brier"
                        ].append(ownership_brier)
                        metrics[
                            f"sampled_endpoint:actual={outcome}:profile={profile}:out_brier"
                        ].append(
                            (
                                float(out_of_play_probability)
                                - float(outcome == "out_of_play")
                            )
                            ** 2
                        )
                for field in (
                    "retained_probability",
                    "opposing_probability",
                    "unresolved_probability",
                    "out_of_play_probability",
                ):
                    value = endpoint_projection.get(profile, {}).get(field)
                    if isinstance(value, (int, float)):
                        metrics[
                            f"sampled_endpoint:actual={outcome}:profile={profile}:{field}"
                        ].append(float(value))
                        if production_stable_retained:
                            metrics[
                                f"sampled_endpoint:actual={outcome}:production_stable_retained:"
                                f"profile={profile}:{field}"
                            ].append(float(value))
                endpoint_projection_counts[
                    f"actual={outcome}:profile={profile}:stage={profile_stage}"
                ] += 1
                endpoint_projection_counts[
                    f"actual={outcome}:profile={profile}:stable_retained="
                    f"{str(profile_stable_retained).lower()}"
                ] += 1
                if production_stable_retained:
                    endpoint_projection_counts[
                        f"actual={outcome}:production_stable_retained:"
                        f"profile={profile}:preserved="
                        f"{str(profile_stable_retained).lower()}"
                    ] += 1
            ensemble_profiles = {
                "mean_rounded_teammates_exact": (
                    "production_targeting",
                    "teammates_exact",
                ),
                "mean_rounded_opponents_exact": (
                    "production_targeting",
                    "opponents_exact",
                ),
                "mean_rounded_two_sided_exact": (
                    "production_targeting",
                    "teammates_and_opponents_exact",
                ),
                "mean_formation_time_factorial": (
                    "production_targeting",
                    "teammates_exact",
                    "opponents_exact",
                    "teammates_and_opponents_exact",
                ),
                "mean_receiver_opponent_time_factorial": (
                    "production_targeting",
                    "receiver_exact",
                    "opponents_exact",
                    "receiver_and_opponents_exact",
                ),
                "profile_mean": endpoint_profiles,
            }
            for ensemble_name, member_profiles in ensemble_profiles.items():
                probability_rows = [
                    tuple(
                        endpoint_projection.get(profile, {}).get(field)
                        for field in (
                            "retained_probability",
                            "opposing_probability",
                            "unresolved_probability",
                            "out_of_play_probability",
                        )
                    )
                    for profile in member_profiles
                ]
                if not probability_rows or not all(
                    all(isinstance(value, (int, float)) for value in row)
                    for row in probability_rows
                ):
                    continue
                ensemble_mean = tuple(
                    mean(float(row[index]) for row in probability_rows)
                    for index in range(4)
                )
                ownership_target = {
                    "completed": (1.0, 0.0, 0.0),
                    "opposing_control": (0.0, 1.0, 0.0),
                    "loose": (0.0, 0.0, 1.0),
                    "out_of_play": (0.0, 0.0, 1.0),
                    "unresolved": (0.0, 0.0, 1.0),
                }.get(outcome)
                if ownership_target is not None:
                    metrics[
                        f"sampled_endpoint:actual={outcome}:profile={ensemble_name}:"
                        "ownership_brier"
                    ].append(
                        sum(
                            (predicted - expected) ** 2
                            for predicted, expected in zip(
                                ensemble_mean[:3], ownership_target
                            )
                        )
                    )
                    metrics[
                        f"sampled_endpoint:actual={outcome}:profile={ensemble_name}:"
                        "out_brier"
                    ].append(
                        (ensemble_mean[3] - float(outcome == "out_of_play")) ** 2
                    )
                for index, field in enumerate((
                    "retained_probability",
                    "opposing_probability",
                    "unresolved_probability",
                    "out_of_play_probability",
                )):
                    metrics[
                        f"sampled_endpoint:actual={outcome}:profile={ensemble_name}:{field}"
                    ].append(ensemble_mean[index])
            rounded_payload = endpoint_projection.get("production_targeting", {})
            exact_payload = endpoint_projection.get(
                "teammates_and_opponents_exact", {}
            )
            rounded_stage = str(rounded_payload.get("resolution_stage") or "unknown")
            exact_stage = str(exact_payload.get("resolution_stage") or "unknown")
            stage_disagrees = rounded_stage != exact_stage
            conditional_rows = [
                tuple(rounded_payload.get(field) for field in (
                    "retained_probability",
                    "opposing_probability",
                    "unresolved_probability",
                    "out_of_play_probability",
                )),
                tuple(exact_payload.get(field) for field in (
                    "retained_probability",
                    "opposing_probability",
                    "unresolved_probability",
                    "out_of_play_probability",
                )),
            ]
            if all(
                all(isinstance(value, (int, float)) for value in row)
                for row in conditional_rows
            ):
                conditional_probability = tuple(
                    mean(float(row[index]) for row in conditional_rows)
                    if stage_disagrees
                    else float(conditional_rows[0][index])
                    for index in range(4)
                )
                conditional_name = "stage_disagreement_mean"
                endpoint_projection_counts[
                    f"actual={outcome}:profile={conditional_name}:"
                    f"stage_disagrees={str(stage_disagrees).lower()}"
                ] += 1
                ownership_target = {
                    "completed": (1.0, 0.0, 0.0),
                    "opposing_control": (0.0, 1.0, 0.0),
                    "loose": (0.0, 0.0, 1.0),
                    "out_of_play": (0.0, 0.0, 1.0),
                    "unresolved": (0.0, 0.0, 1.0),
                }.get(outcome)
                if ownership_target is not None:
                    metrics[
                        f"sampled_endpoint:actual={outcome}:profile={conditional_name}:"
                        "ownership_brier"
                    ].append(
                        sum(
                            (predicted - expected) ** 2
                            for predicted, expected in zip(
                                conditional_probability[:3], ownership_target
                            )
                        )
                    )
                    metrics[
                        f"sampled_endpoint:actual={outcome}:profile={conditional_name}:"
                        "out_brier"
                    ].append(
                        (
                            conditional_probability[3]
                            - float(outcome == "out_of_play")
                        )
                        ** 2
                    )
                for index, field in enumerate((
                    "retained_probability",
                    "opposing_probability",
                    "unresolved_probability",
                    "out_of_play_probability",
                )):
                    metrics[
                        f"sampled_endpoint:actual={outcome}:profile={conditional_name}:{field}"
                    ].append(conditional_probability[index])
            production_payload = endpoint_projection.get("production_targeting", {})
            projected_controller_idx = production_payload.get(
                "dominant_retained_controller_idx"
            )
            observations = flight_observations_by_replay.get(replay_id, [])
            controller_rows = []
            if isinstance(projected_controller_idx, int):
                for observation in observations:
                    players = observation.get("attacking_players", [])
                    if not isinstance(players, list):
                        continue
                    player = next(
                        (
                            row
                            for row in players
                            if isinstance(row, dict)
                            and row.get("idx") == projected_controller_idx
                        ),
                        None,
                    )
                    if isinstance(player, dict):
                        controller_rows.append((observation, player))
            if controller_rows:
                first_observation, first = controller_rows[0]
                last_observation, last = controller_rows[-1]

                first_intent = str(first.get("movement_intent") or "unknown")
                last_intent = str(last.get("movement_intent") or "unknown")
                intent_changed = first_intent != last_intent
                intended_receiver_idx = physical.get("intended_receiver_player")
                controller_is_intended = projected_controller_idx == intended_receiver_idx
                first_active = bool(first.get("local_response_active"))
                last_active = bool(last.get("local_response_active"))
                first_active_defenders = first_observation.get(
                    "defending_active_indices", []
                )
                last_active_defenders = last_observation.get(
                    "defending_active_indices", []
                )
                if not isinstance(first_active_defenders, list):
                    first_active_defenders = []
                if not isinstance(last_active_defenders, list):
                    last_active_defenders = []
                physical_strongest_player = physical.get("strongest_contact_player")
                physical_strongest_opponent = strongest_role(physical) == "opponent"
                first_strongest_opponent_active = physical_strongest_opponent and any(
                    index == physical_strongest_player
                    for index in first_active_defenders
                )
                last_strongest_opponent_active = physical_strongest_opponent and any(
                    index == physical_strongest_player
                    for index in last_active_defenders
                )
                controller_task_counts["observed"] += 1
                controller_task_counts[f"actual={outcome}"] += 1
                controller_task_counts[
                    f"actual={outcome}:intent={first_intent}->{last_intent}"
                ] += 1
                controller_task_counts[
                    f"actual={outcome}:intent_changed={str(intent_changed).lower()}"
                ] += 1
                controller_task_counts[
                    f"actual={outcome}:controller_response_mode="
                    + (
                        "intended_receiver"
                        if controller_is_intended
                        else "nonintended_active"
                        if first_active
                        else "nonintended_inactive"
                    )
                ] += 1
                controller_task_counts[
                    f"actual={outcome}:controller_active={str(first_active).lower()}"
                    f"->{str(last_active).lower()}"
                ] += 1
                if physical_strongest_opponent:
                    controller_task_counts[
                        f"actual={outcome}:strongest_opponent_active="
                        f"{str(first_strongest_opponent_active).lower()}"
                        f"->{str(last_strongest_opponent_active).lower()}"
                    ] += 1
                if production_stable_retained:
                    controller_task_counts[
                        f"actual={outcome}:production_stable_retained:"
                        f"intent={first_intent}->{last_intent}"
                    ] += 1
                    controller_task_counts[
                        f"actual={outcome}:production_stable_retained:"
                        f"intent_changed={str(intent_changed).lower()}"
                    ] += 1
                    controller_task_counts[
                        f"actual={outcome}:production_stable_retained:"
                        "controller_response_mode="
                        + (
                            "intended_receiver"
                            if controller_is_intended
                            else "nonintended_active"
                            if first_active
                            else "nonintended_inactive"
                        )
                    ] += 1
                    if physical_strongest_opponent:
                        controller_task_counts[
                            f"actual={outcome}:production_stable_retained:"
                            "strongest_opponent_active="
                            f"{str(first_strongest_opponent_active).lower()}"
                            f"->{str(last_strongest_opponent_active).lower()}"
                        ] += 1
                controller_task_counts[
                    f"actual={outcome}:projected_controller_is_intended="
                    f"{str(projected_controller_idx == physical.get('intended_receiver_player')).lower()}"
                ] += 1
                controller_task_metrics[
                    f"actual={outcome}:observation_count"
                ].append(float(len(controller_rows)))
                controller_task_metrics[
                    f"actual={outcome}:first_active_defender_count"
                ].append(float(len(first_active_defenders)))
                controller_task_metrics[
                    f"actual={outcome}:last_active_defender_count"
                ].append(float(len(last_active_defenders)))
                for field, value in (
                    (
                        "controller_position_drift_m",
                        point_distance(first.get("pos"), last.get("pos")),
                    ),
                    (
                        "effective_target_drift_m",
                        point_distance(
                            first.get("effective_target"),
                            last.get("effective_target"),
                        ),
                    ),
                    (
                        "first_distance_to_observed_destination_m",
                        first.get("distance_to_observed_destination_m"),
                    ),
                    (
                        "last_distance_to_observed_destination_m",
                        last.get("distance_to_observed_destination_m"),
                    ),
                    (
                        "first_effective_target_to_observed_destination_m",
                        first.get(
                            "effective_target_to_observed_destination_m"
                        ),
                    ),
                    (
                        "last_effective_target_to_observed_destination_m",
                        last.get("effective_target_to_observed_destination_m"),
                    ),
                    (
                        "last_effective_target_to_physical_terminal_m",
                        point_distance(
                            last.get("effective_target"),
                            physical.get("terminal_position"),
                        ),
                    ),
                ):
                    if isinstance(value, (int, float)):
                        controller_task_metrics[f"actual={outcome}:{field}"].append(
                            float(value)
                        )
                        if production_stable_retained:
                            controller_task_metrics[
                                f"actual={outcome}:production_stable_retained:{field}"
                            ].append(float(value))
                if len(controller_task_cases) < 80:
                    controller_task_cases.append(
                        {
                            "replay_id": replay_id,
                            "release_tick": release.get("tick"),
                            "actual_outcome": outcome,
                            "projected_resolution_stage": production_stage,
                            "projected_controller_idx": projected_controller_idx,
                            "intended_receiver_idx": intended_receiver_idx,
                            "controller_response_mode": (
                                "intended_receiver"
                                if controller_is_intended
                                else "nonintended_active"
                                if first_active
                                else "nonintended_inactive"
                            ),
                            "physical_strongest_role": strongest_role(physical),
                            "physical_strongest_player": physical.get(
                                "strongest_contact_player"
                            ),
                            "observation_count": len(controller_rows),
                            "first": {
                                "tick": first_observation.get("tick"),
                                "elapsed_before": first_observation.get(
                                    "elapsed_before"
                                ),
                                "intent": first_intent,
                                "pos": first.get("pos"),
                                "effective_target": first.get("effective_target"),
                                "distance_to_observed_destination_m": first.get(
                                    "distance_to_observed_destination_m"
                                ),
                                "local_response_active": first_active,
                                "active_defender_indices": [
                                    index for index in first_active_defenders
                                ],
                                "physical_strongest_opponent_active":
                                    first_strongest_opponent_active,
                            },
                            "last": {
                                "tick": last_observation.get("tick"),
                                "elapsed_after": last_observation.get("elapsed_after"),
                                "intent": last_intent,
                                "pos": last.get("pos"),
                                "effective_target": last.get("effective_target"),
                                "distance_to_observed_destination_m": last.get(
                                    "distance_to_observed_destination_m"
                                ),
                                "local_response_active": last_active,
                                "active_defender_indices": [
                                    index for index in last_active_defenders
                                ],
                                "physical_strongest_opponent_active":
                                    last_strongest_opponent_active,
                            },
                        }
                    )
        distance_group = distance_bucket(release.get("actual_distance_m"))
        target_margin = boundary_margin(release.get("target"))
        margin_group = margin_bucket(target_margin)
        role = strongest_role(physical)
        deflection_role = material_deflection_role(physical)
        stable_at_physical = physical.get("stable_controller_player") is not None
        free_ball_stable = isinstance(controlled, dict) and not stable_at_physical
        residual_ticks = max(
            (
                int(row.get("free_ball_ticks", 0) or 0)
                for row in phases
            ),
            default=0,
        )
        out_entry = continuous_out_by_replay.get(replay_id)
        out_stage = None
        if outcome == "out_of_play":
            if out_entry is not None:
                out_stage = "residual_free_ball"
            else:
                tick = terminal.get("tick")
                direct = direct_out_by_tick.get(int(tick), []) if isinstance(tick, int) else []
                if len(direct) == 1:
                    out_entry = direct[0]
                    out_stage = "direct_flight"
                else:
                    out_stage = "unmatched"

        counts["pass_releases"] += 1
        counts[f"outcome={outcome}"] += 1
        counts[f"physical_strongest_role={role}"] += 1
        counts[f"material_deflection_role={deflection_role}"] += 1
        counts[
            f"material_deflection_role={deflection_role}:outcome={outcome}"
        ] += 1
        counts[f"stable_at_physical={str(stable_at_physical).lower()}"] += 1
        counts[f"free_ball_stable={str(free_ball_stable).lower()}"] += 1
        for dimension, value in (
            ("target_margin", margin_group),
            ("delivery", delivery),
            ("target_kind", target_kind),
            ("distance", distance_group),
        ):
            strata[f"{dimension}:{value}"]["attempted"] += 1
            strata[f"{dimension}:{value}"][f"outcome={outcome}"] += 1
            if stable_at_physical:
                strata[f"{dimension}:{value}"]["stable_at_physical"] += 1
            elif free_ball_stable:
                strata[f"{dimension}:{value}"]["stable_after_free_ball"] += 1
        distance_m = release.get("actual_distance_m")
        if isinstance(distance_m, (int, float)):
            metrics[f"outcome={outcome}:distance_m"].append(float(distance_m))
        if isinstance(target_margin, (int, float)):
            metrics[f"outcome={outcome}:target_boundary_margin_m"].append(
                float(target_margin)
            )
        terminal_speed = physical.get("terminal_speed")
        if isinstance(terminal_speed, (int, float)):
            metrics[f"outcome={outcome}:physical_terminal_speed"].append(
                float(terminal_speed)
            )
        for field in (
            "material_deflection_incoming_speed",
            "material_deflection_velocity_change",
            "material_deflection_post_speed",
        ):
            value = physical.get(field)
            if isinstance(value, (int, float)):
                metrics[
                    f"material_deflection_role={deflection_role}:outcome={outcome}:{field}"
                ].append(float(value))
        for team in ("home", "away"):
            target_errors = [
                float(row[f"{team}_primary_target_error"])
                for row in phases
                if isinstance(
                    row.get(f"{team}_primary_target_error"), (int, float)
                )
            ]
            ball_distances = [
                float(row[f"{team}_primary_ball_distance"])
                for row in phases
                if isinstance(
                    row.get(f"{team}_primary_ball_distance"), (int, float)
                )
            ]
            if target_errors:
                metrics[f"outcome={outcome}:{team}_primary_target_error"].append(
                    min(target_errors)
                )
            if ball_distances:
                metrics[f"outcome={outcome}:{team}_primary_ball_distance"].append(
                    min(ball_distances)
                )
        metrics[f"outcome={outcome}:residual_free_ball_ticks"].append(
            float(residual_ticks)
        )

        if outcome != "out_of_play":
            continue
        terminal_phase = phases[-1] if phases else None
        reason = instability_reason(terminal_phase)
        counts["out_of_play"] += 1
        counts[f"out_of_play:stage={out_stage}"] += 1
        counts[f"out_of_play:target_margin={margin_group}"] += 1
        counts[f"out_of_play:delivery={delivery}"] += 1
        counts[f"out_of_play:target_kind={target_kind}"] += 1
        counts[f"out_of_play:distance={distance_group}"] += 1
        counts[f"out_of_play:physical_strongest_role={role}"] += 1
        counts[f"out_of_play:material_deflection_role={deflection_role}"] += 1
        counts[f"out_of_play:terminal_instability={reason}"] += 1
        counts["out_of_play:target_margin_over_3m"] += int(
            isinstance(target_margin, (int, float)) and target_margin > 3.0
        )
        counts["out_of_play:target_margin_over_5m"] += int(
            isinstance(target_margin, (int, float)) and target_margin > 5.0
        )
        counts["out_of_play:intended_receiver_physical_strongest"] += int(
            role == "intended_receiver"
        )
        counts["out_of_play:intended_receiver_strongest_then_no_stable_control"] += int(
            role == "intended_receiver" and controlled is None
        )
        out_cases.append(
            {
                "replay_id": replay_id,
                "release_tick": release.get("tick"),
                "terminal_tick": terminal.get("tick"),
                "origin": release.get("origin"),
                "target": release.get("target"),
                "target_boundary_margin_m": (
                    round(target_margin, 6)
                    if isinstance(target_margin, (int, float))
                    else None
                ),
                "distance_m": release.get("actual_distance_m"),
                "distance_group": distance_group,
                "delivery": delivery,
                "target_kind": target_kind,
                "trajectory": release.get("trajectory"),
                "planned_arrival_outcome": release.get("planned_arrival_outcome"),
                "planned_arrival_receiver_player": release.get(
                    "planned_arrival_receiver_player"
                ),
                "planned_arrival_opponent_player": release.get(
                    "planned_arrival_opponent_player"
                ),
                "planned_arrival_receiver_control": release.get(
                    "planned_arrival_receiver_control"
                ),
                "planned_arrival_opponent_control": release.get(
                    "planned_arrival_opponent_control"
                ),
                "planned_arrival_loose_control": release.get(
                    "planned_arrival_loose_control"
                ),
                "sampled_endpoint_projection": release.get(
                    "sampled_endpoint_projection"
                ),
                "out_stage": out_stage,
                "out_boundary": out_entry.get("boundary") if out_entry else None,
                "out_reason": out_entry.get("reason") if out_entry else None,
                "physical_terminal": {
                    key: physical.get(key)
                    for key in (
                        "terminal_position",
                        "terminal_velocity",
                        "match_tick",
                        "release_match_tick",
                        "physical_terminal_replay_tick",
                        "exact_flight_ticks",
                        "consumed_tick_fraction",
                        "reaches_target",
                        "materially_contacted",
                        "material_deflection_contact_team",
                        "material_deflection_contact_player",
                        "material_deflection_contact_quality",
                        "material_deflection_substep",
                        "material_deflection_incoming_speed",
                        "material_deflection_velocity_change",
                        "material_deflection_post_speed",
                        "strongest_contact_team",
                        "strongest_contact_player",
                        "intended_receiver_player",
                        "strongest_contact_quality",
                        "strongest_contact_incoming_speed",
                        "strongest_contact_relative_speed",
                        "strongest_contact_post_relative_speed",
                        "strongest_contact_impulse_access",
                        "strongest_contact_player_speed",
                        "strongest_contact_velocity_alignment",
                        "strongest_contact_reception_readiness",
                        "strongest_contact_position",
                        "strongest_contact_initial_position",
                        "strongest_contact_player_displacement",
                        "strongest_contact_separation",
                        "strongest_contact_target_distance",
                        "terminal_speed",
                        "intended_receiver_terminal_position",
                        "intended_receiver_initial_position",
                        "intended_receiver_displacement",
                        "intended_receiver_target_distance",
                        "intended_receiver_movement_target",
                        "intended_receiver_intent",
                        "planned_opponent_player",
                        "planned_opponent_terminal_position",
                        "planned_opponent_displacement",
                        "planned_opponent_terminal_ball_distance",
                        "passer_team_terminal_players",
                        "opponent_team_terminal_players",
                        "home_claim",
                        "away_claim",
                        "stable_controller_team",
                        "stable_controller_player",
                    )
                },
                "physical_strongest_role": role,
                "stable_at_physical_terminal": stable_at_physical,
                "stable_controller": (
                    {
                        "team": controlled.get("team"),
                        "player": controlled.get("player_idx"),
                        "provenance": controlled.get("control_provenance"),
                    }
                    if isinstance(controlled, dict)
                    else None
                ),
                "stable_budget_events": len(stable_budgets),
                "residual_free_ball_ticks": residual_ticks,
                "observed_free_ball_phases": len(phases),
                "terminal_instability_reason": reason,
                "pursuit_phases": [
                    {
                        key: phase.get(key)
                        for key in (
                            "tick",
                            "phase_tick_fraction",
                            "ball",
                            "speed",
                            "boundary_margin",
                            "home_primary_pursuer",
                            "home_primary_ball_distance",
                            "home_primary_target_error",
                            "home_primary_arrival_ticks",
                            "away_primary_pursuer",
                            "away_primary_ball_distance",
                            "away_primary_target_error",
                            "away_primary_arrival_ticks",
                            "home_candidate",
                            "home_confidence",
                            "away_candidate",
                            "away_confidence",
                            "stable",
                        )
                        if phase.get(key) is not None
                    }
                    for phase in phases
                ],
                "terminal_free_ball_phase": (
                    {
                        key: terminal_phase.get(key)
                        for key in (
                            "tick",
                            "phase_tick_fraction",
                            "free_ball_ticks",
                            "ball",
                            "speed",
                            "boundary_margin",
                            "nearest_player_distance",
                            "home_candidate",
                            "home_confidence",
                            "away_candidate",
                            "away_confidence",
                            "strongest_contact_quality",
                            "strongest_contact_post_relative_speed",
                            "strongest_home_contact_quality",
                            "strongest_away_contact_quality",
                            "stable",
                        )
                    }
                    if isinstance(terminal_phase, dict)
                    else None
                ),
                "opponent_material_contacts": material_contacts_by_replay.get(
                    replay_id, []
                ),
                "last_visible_flight_observation": (
                    {
                        key: flight_observations_by_replay[replay_id][-1].get(key)
                        for key in (
                            "tick",
                            "elapsed_before",
                            "elapsed_after",
                            "observed_destination",
                            "attacking_players",
                            "defending_active_indices",
                            "attacking_activation_radius_m",
                            "defending_activation_radius_m",
                        )
                    }
                    if flight_observations_by_replay.get(replay_id)
                    else None
                ),
            }
        )

    return {
        "scope": (
            "read-only replay_id join from every traced pass release through its physical "
            "terminal, pending-pass FreeBall control phases, stable controller, and final "
            "pass_control_terminal/out_of_bounds event; production state and RNG are unchanged"
        ),
        "observability": {
            "physical_contact_identity": (
                "pass_physical_terminal exposes the strongest contact at the physical "
                "terminal, not the chronologically first substep contact"
            ),
            "first_contact_identity": "not observable in the current raw trace",
            "stability_attribution": (
                "stable is authoritative per phase; categorical failure reasons are a "
                "read-only summary of observable claim/post-contact fields and cannot "
                "reconstruct the untraced pinned-ball velocity scale or winning-contact identity"
            ),
        },
        "counts": dict(sorted(counts.items())),
        "sampled_endpoint_projection_counts": dict(
            sorted(endpoint_projection_counts.items())
        ),
        "projected_controller_flight_task_dynamics": {
            "scope": (
                "read-only join of the production sampled-endpoint retained controller "
                "to that player's first and last full-trace flight observations; no "
                "threshold, movement replay, state mutation, or RNG consumption"
            ),
            "counts": dict(sorted(controller_task_counts.items())),
            "metrics": {
                field: _distribution(values)
                for field, values in sorted(controller_task_metrics.items())
                if values
            },
            "cases": controller_task_cases,
        },
        "strata": {
            group: dict(sorted(values.items()))
            for group, values in sorted(strata.items())
        },
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "out_of_play_cases": out_cases[:80],
    }


def _completed_pass_cadence_lifecycle(
    trace_entries: list[dict[str, Any]], tick_duration: float
) -> dict[str, Any]:
    """Split completed-pass release cadence into flight, settlement, and held time."""
    releases = sorted(
        (
            (trace_index, entry)
            for trace_index, entry in enumerate(trace_entries)
            if entry.get("action") == "pass"
            and entry.get("replay_id") is not None
            and isinstance(entry.get("release_replay_tick"), (int, float))
        ),
        key=lambda indexed: float(indexed[1]["release_replay_tick"]),
    )
    physical = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_physical_terminal"
        and entry.get("replay_id") is not None
    }
    terminals = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_control_terminal"
        and entry.get("replay_id") is not None
    }
    control_budget = {
        entry.get("pending_pass_replay_id"): (trace_index, entry)
        for trace_index, entry in enumerate(trace_entries)
        if entry.get("event") == "free_ball_stable_control_budget"
        and entry.get("pending_pass_replay_id") is not None
        and isinstance(entry.get("control_replay_tick"), (int, float))
    }
    metrics: dict[str, list[float]] = defaultdict(list)
    counts: Counter[str] = Counter()
    cases: list[dict[str, Any]] = []
    direct_control = {
        entry.get("pending_pass_replay_id"): (trace_index, entry)
        for trace_index, entry in enumerate(trace_entries)
        if entry.get("event") == "ball_controlled"
        and entry.get("pending_pass_replay_id") is not None
    }
    for index, (release_trace_index, release) in enumerate(releases):
        replay_id = release.get("replay_id")
        terminal = terminals.get(replay_id, {})
        if terminal.get("outcome") != "completed":
            continue
        release_tick = float(release["release_replay_tick"])
        possession_id = release.get("possession_id")
        team = release.get("team")
        following = next(
            (
                (candidate_trace_index, candidate)
                for candidate_trace_index, candidate in releases[index + 1 :]
                if candidate.get("possession_id") == possession_id
                and candidate.get("team") == team
            ),
            None,
        )
        if following is None:
            counts["completed_without_following_same_possession_pass"] += 1
            continue
        next_release_trace_index, following = following
        next_release_tick = float(following["release_replay_tick"])
        physical_row = physical.get(replay_id, {})
        physical_tick = physical_row.get("physical_terminal_replay_tick")
        controlled = control_budget.get(replay_id)
        control_tick = (
            controlled[1].get("control_replay_tick")
            if isinstance(controlled, tuple)
            else physical_tick
            if physical_row.get("stable_controller_player") is not None
            else None
        )
        control_trace_index = (
            controlled[0]
            if isinstance(controlled, tuple)
            else direct_control.get(replay_id, (release_trace_index, {}))[0]
        )
        if not isinstance(physical_tick, (int, float)) or not isinstance(
            control_tick, (int, float)
        ):
            counts["missing_exact_phase_time"] += 1
            continue
        physical_tick = float(physical_tick)
        control_tick = float(control_tick)
        flight_seconds = max(physical_tick - release_tick, 0.0) * tick_duration
        settlement_seconds = max(control_tick - physical_tick, 0.0) * tick_duration
        held_seconds = max(next_release_tick - control_tick, 0.0) * tick_duration
        total_seconds = max(next_release_tick - release_tick, 0.0) * tick_duration
        counts["joined_completed_pass_pairs"] += 1
        counts[
            "same_arrival_tick_control"
            if settlement_seconds <= 1e-9
            else "post_flight_free_ball_control"
        ] += 1
        for field, value in (
            ("release_to_physical_terminal_seconds", flight_seconds),
            ("physical_terminal_to_control_seconds", settlement_seconds),
            ("control_to_next_release_seconds", held_seconds),
            ("release_to_next_release_seconds", total_seconds),
        ):
            metrics[field].append(value)
        action_path = [
            str(entry.get("action"))
            for entry in trace_entries[control_trace_index + 1 : next_release_trace_index]
            if entry.get("type") == "action"
            and entry.get("team") == team
            and entry.get("action") in {
                "carry",
                "clear",
                "hold",
                "pass",
                "reorient",
                "shoot",
            }
        ]
        path_label = "->".join(action_path) if action_path else "direct_pass"
        counts[f"intervening_action_path={path_label}"] += 1
        counts[
            f"first_intervening_action={action_path[0] if action_path else 'pass'}"
        ] += 1
        metrics[f"path={path_label}:release_to_next_release_seconds"].append(
            total_seconds
        )
        metrics[f"path={path_label}:control_to_next_release_seconds"].append(
            held_seconds
        )
        cases.append(
            {
                "replay_id": replay_id,
                "next_replay_id": following.get("replay_id"),
                "possession_id": possession_id,
                "release_tick": release_tick,
                "physical_terminal_tick": physical_tick,
                "control_tick": control_tick,
                "next_release_tick": next_release_tick,
                "flight_seconds": round(flight_seconds, 6),
                "settlement_seconds": round(settlement_seconds, 6),
                "held_seconds": round(held_seconds, 6),
                "total_seconds": round(total_seconds, 6),
                "intervening_action_path": action_path,
            }
        )
    return {
        "scope": (
            "read-only exact replay-time join for completed passes with a later same-team, "
            "same-possession pass release; the interval is partitioned into release-to-physical "
            "terminal, physical-terminal-to-stable-control, and stable-control-to-next-release"
        ),
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "cases": cases,
    }


def _flight_defense_counterfactual_lifecycle(
    trace_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join existing active-defender shadows to the realized pass terminal."""
    releases = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("action") == "pass" and entry.get("replay_id") is not None
    }
    terminals = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_control_terminal"
        and entry.get("replay_id") is not None
    }
    physical = {
        entry.get("replay_id"): entry
        for entry in trace_entries
        if entry.get("event") == "pass_physical_terminal"
        and entry.get("replay_id") is not None
    }
    visible_by_key = {
        (entry.get("replay_id"), entry.get("tick")): entry
        for entry in trace_entries
        if entry.get("event") == "visible_flight_defense_one_tick_counterfactual"
    }
    no_carrier_by_key = {
        (entry.get("replay_id"), entry.get("tick")): entry
        for entry in trace_entries
        if entry.get("event") == "flight_defense_no_carrier_counterfactual"
    }
    zero_maturity_rows = [
        entry
        for entry in trace_entries
        if entry.get("event")
        == "flight_defense_zero_carrier_maturity_counterfactual"
    ]

    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    cases: list[dict[str, Any]] = []

    def row_for(entry: Any, field: str, player_idx: int) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        rows = entry.get(field, [])
        if not isinstance(rows, list):
            return None
        return next(
            (
                row
                for row in rows
                if isinstance(row, dict) and row.get("player_idx") == player_idx
            ),
            None,
        )

    def point_distance(left: Any, right: Any) -> float | None:
        if not (
            isinstance(left, list)
            and len(left) >= 2
            and isinstance(right, list)
            and len(right) >= 2
        ):
            return None
        return hypot(
            float(left[0]) - float(right[0]),
            float(left[1]) - float(right[1]),
        )

    def compare(
        label: str,
        outcome: str,
        production_stable: bool,
        baseline: dict[str, Any] | None,
        counterfactual: dict[str, Any] | None,
        terminal_pos: Any,
        case_payload: dict[str, Any],
    ) -> None:
        if not isinstance(baseline, dict) or not isinstance(counterfactual, dict):
            counts[f"{label}:missing_pair"] += 1
            return
        prefix = f"actual={outcome}:production_stable={str(production_stable).lower()}:{label}"
        counts[f"{prefix}:pairs"] += 1
        baseline_action = str(baseline.get("action_type") or "unknown")
        counterfactual_action = str(counterfactual.get("action_type") or "unknown")
        counts[
            f"{prefix}:action_changed={str(baseline_action != counterfactual_action).lower()}"
        ] += 1
        counts[f"{prefix}:action={baseline_action}->{counterfactual_action}"] += 1
        baseline_target = baseline.get("target")
        counterfactual_target = counterfactual.get("target")
        displacement = point_distance(baseline_target, counterfactual_target)
        baseline_terminal = point_distance(baseline_target, terminal_pos)
        counterfactual_terminal = point_distance(counterfactual_target, terminal_pos)
        for field, value in (
            ("target_displacement_m", displacement),
            ("baseline_target_to_terminal_m", baseline_terminal),
            ("counterfactual_target_to_terminal_m", counterfactual_terminal),
            (
                "counterfactual_minus_baseline_terminal_distance_m",
                (
                    counterfactual_terminal - baseline_terminal
                    if isinstance(counterfactual_terminal, (int, float))
                    and isinstance(baseline_terminal, (int, float))
                    else None
                ),
            ),
        ):
            if isinstance(value, (int, float)):
                metrics[f"{prefix}:{field}"].append(float(value))
        case_payload[label] = {
            "baseline_action": baseline_action,
            "counterfactual_action": counterfactual_action,
            "baseline_target": baseline_target,
            "counterfactual_target": counterfactual_target,
            "target_displacement_m": displacement,
            "baseline_target_to_terminal_m": baseline_terminal,
            "counterfactual_target_to_terminal_m": counterfactual_terminal,
        }

    for zero_entry in zero_maturity_rows:
        replay_id = zero_entry.get("replay_id")
        tick = zero_entry.get("tick")
        terminal = terminals.get(replay_id, {})
        outcome = str(terminal.get("outcome") or "unresolved")
        physical_row = physical.get(replay_id, {})
        if physical_row.get("strongest_contact_team") == physical_row.get("passer_team"):
            continue
        strongest_player = physical_row.get("strongest_contact_player")
        if not isinstance(strongest_player, int):
            continue
        release = releases.get(replay_id, {})
        production_stage = str(
            release.get("sampled_endpoint_projection", {})
            .get("production_targeting", {})
            .get("resolution_stage")
            or "unknown"
        )
        production_stable = production_stage in {
            "arrival_stable_retained",
            "residual_stable_retained",
        }
        terminal_pos = physical_row.get("terminal_position")
        key = (replay_id, tick)
        visible = visible_by_key.get(key, {})
        no_carrier = no_carrier_by_key.get(key, {})
        control = row_for(zero_entry, "control_shadow", strongest_player)
        payload: dict[str, Any] = {
            "replay_id": replay_id,
            "tick": tick,
            "actual_outcome": outcome,
            "production_stage": production_stage,
            "strongest_opponent_player": strongest_player,
            "terminal_position": terminal_pos,
        }
        compare(
            "one_tick_forecast_same_mask",
            outcome,
            production_stable,
            row_for(visible, "current_belief_shadow", strongest_player),
            row_for(
                visible,
                "one_tick_forecast_same_mask_shadow",
                strongest_player,
            ),
            terminal_pos,
            payload,
        )
        compare(
            "one_tick_forecast_new_mask",
            outcome,
            production_stable,
            row_for(visible, "current_belief_shadow", strongest_player),
            row_for(visible, "one_tick_forecast_shadow", strongest_player),
            terminal_pos,
            payload,
        )
        compare(
            "no_carrier",
            outcome,
            production_stable,
            control,
            row_for(no_carrier, "no_carrier_shadow", strongest_player),
            terminal_pos,
            payload,
        )
        compare(
            "zero_carrier_maturity",
            outcome,
            production_stable,
            control,
            row_for(
                zero_entry,
                "zero_carrier_maturity_shadow",
                strongest_player,
            ),
            terminal_pos,
            payload,
        )
        if len(cases) < 80:
            cases.append(payload)

    return {
        "scope": (
            "read-only replay_id/tick join of existing visible-forecast, no-carrier, "
            "and zero-carrier-maturity defense shadows to the realized strongest "
            "opponent contact; action selection, movement, state, and RNG are unchanged"
        ),
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values)
            for field, values in sorted(metrics.items())
            if values
        },
        "cases": cases,
    }


def _restart_branch_value_shadow(
    trace_decisions: list[dict[str, Any]],
    tick_duration: float,
    restart_wait_ticks: dict[str, float],
) -> dict[str, Any]:
    """Price already-projected pass restart branches without changing production."""
    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    expected: Counter[str] = Counter()
    cases: list[dict[str, Any]] = []

    def candidate_shadow(
        candidate: dict[str, Any],
        tempo: float,
        risk_budget: float,
    ) -> tuple[dict[str, Any], float, float, float, float]:
        production_score = candidate.get("value", {}).get("score")
        if not isinstance(production_score, (int, float)):
            return candidate, 0.0, 0.0, 0.0, 0.0
        if candidate.get("action_type") != "pass":
            return candidate, float(production_score), 0.0, 0.0, 0.0
        value = candidate.get("value", {})
        components = value.get("components", {})
        transition = components.get("outcome_transition", {})
        restart_rows = transition.get("restart_by_kind", [])
        option_return = components.get("option_return")
        local_shaping = components.get("local_shaping")
        current_value = components.get("current_value")
        duration = components.get("option_duration_seconds")
        if not (
            isinstance(restart_rows, list)
            and isinstance(option_return, (int, float))
            and isinstance(local_shaping, (int, float))
            and isinstance(current_value, (int, float))
            and isinstance(duration, (int, float))
        ):
            return candidate, float(production_score), 0.0, 0.0, 0.0

        tempo = max(0.0, min(1.0, tempo))
        risk_budget = max(0.0, min(1.0, risk_budget))
        discount_rate = 0.0015 + 0.0060 * tempo
        turnover_severity = 0.76 + 0.12 * (1.0 - risk_budget)
        restart_return = 0.0
        retained_restart = 0.0
        opposing_restart = 0.0
        for row in restart_rows:
            if not isinstance(row, dict):
                continue
            reason = str(row.get("reason") or "unknown")
            delay_ticks = restart_wait_ticks.get(reason, 0.0)
            delay_seconds = max(delay_ticks, 0.0) * max(tick_duration, 0.0)
            retained_probability = float(
                row.get("retained_probability", 0.0) or 0.0
            )
            opposing_probability = float(
                row.get("opposing_probability", 0.0) or 0.0
            )
            retained_value = float(row.get("retained_value", 0.0) or 0.0)
            opposing_value = float(row.get("opposing_value", 0.0) or 0.0)
            restart_return += exp(
                -discount_rate * max(float(duration) + delay_seconds, 0.1)
            ) * (
                retained_probability * retained_value
                - turnover_severity * opposing_probability * opposing_value
            )
            retained_restart += retained_probability
            opposing_restart += opposing_probability

        old_outcome = float(option_return)
        old_current = max(0.0, min(1.0, float(current_value)))
        old_budget = min(
            0.12 * abs(max(-1.0, min(1.0, old_outcome)) - old_current)
            + 0.002 * old_current,
            0.012,
        )
        alignment = (
            max(-0.25, min(1.0, float(local_shaping) / old_budget))
            if old_budget > 1e-12
            else 0.0
        )
        new_outcome = old_outcome + restart_return
        new_budget = min(
            0.12 * abs(max(-1.0, min(1.0, new_outcome)) - old_current)
            + 0.002 * old_current,
            0.012,
        )
        residual_policy = (
            float(production_score) - old_outcome - float(local_shaping)
        )
        shadow_score = new_outcome + new_budget * alignment + residual_policy

        shadow = copy.deepcopy(candidate)
        shadow_transition = (
            shadow.setdefault("value", {})
            .setdefault("components", {})
            .setdefault("outcome_transition", {})
        )
        shadow_transition["retained_control_probability"] = min(
            1.0,
            float(shadow_transition.get("retained_control_probability", 0.0) or 0.0)
            + retained_restart,
        )
        shadow_transition["opposing_control_probability"] = min(
            1.0,
            float(shadow_transition.get("opposing_control_probability", 0.0) or 0.0)
            + opposing_restart,
        )
        shadow["value"]["score"] = shadow_score
        return (
            shadow,
            shadow_score,
            restart_return,
            retained_restart,
            opposing_restart,
        )

    for decision in trace_decisions:
        candidates = [
            candidate
            for candidate in [
                decision.get("chosen", {}),
                *decision.get("alternatives", []),
            ]
            if isinstance(candidate, dict)
            and isinstance(candidate.get("value", {}).get("score"), (int, float))
        ]
        selection = decision.get("bounded_rational_selection", {})
        iq = selection.get("iq")
        pressure = selection.get("pressure")
        fatigue = selection.get("fatigue")
        if not candidates or not all(
            isinstance(value, (int, float)) for value in (iq, pressure, fatigue)
        ):
            continue
        signals = decision.get("plan_signals", {})
        tempo = float(signals.get("tempo", 0.5) or 0.5)
        risk_budget = float(signals.get("risk_budget", 0.5) or 0.5)
        production_rows = [
            (candidate, float(candidate["value"]["score"]))
            for candidate in candidates
        ]
        shadow_rows: list[tuple[dict[str, Any], float]] = []
        restart_data: dict[int, tuple[float, float, float]] = {}
        for candidate in candidates:
            shadow, score, restart_return, retained_restart, opposing_restart = (
                candidate_shadow(candidate, tempo, risk_budget)
            )
            shadow_rows.append((shadow, score))
            restart_data[id(candidate)] = (
                restart_return,
                retained_restart,
                opposing_restart,
            )
            if candidate.get("action_type") == "pass":
                counts["pass_candidates"] += 1
                restart_probability = retained_restart + opposing_restart
                counts["pass_candidates_with_restart_mass"] += int(
                    restart_probability > 1e-12
                )
                metrics["pass_candidate_score_delta"].append(
                    score - float(candidate["value"]["score"])
                )
                metrics["pass_candidate_restart_probability"].append(
                    restart_probability
                )
                predicted_out = (
                    candidate.get("value", {})
                    .get("components", {})
                    .get("outcome_transition", {})
                    .get("out_of_play_probability")
                )
                if isinstance(predicted_out, (int, float)):
                    metrics["pass_candidate_predicted_out_of_play"].append(
                        float(predicted_out)
                    )

        production_distribution = _two_stage_bounded_rational_distribution(
            production_rows,
            iq=float(iq),
            pressure=float(pressure),
            fatigue=float(fatigue),
        )
        shadow_distribution = _two_stage_bounded_rational_distribution(
            shadow_rows,
            iq=float(iq),
            pressure=float(pressure),
            fatigue=float(fatigue),
        )
        shadow_probability_by_signature = {
            (
                row.get("action_type"),
                json.dumps(row.get("target"), sort_keys=True),
                row.get("source"),
            ): probability
            for row, probability in shadow_distribution
        }
        production_probability_by_signature = {
            (
                row.get("action_type"),
                json.dumps(row.get("target"), sort_keys=True),
                row.get("source"),
            ): probability
            for row, probability in production_distribution
        }
        production_pass_probability = sum(
            probability
            for candidate, probability in production_distribution
            if candidate.get("action_type") == "pass"
        )
        shadow_pass_probability = sum(
            probability
            for candidate, probability in shadow_distribution
            if candidate.get("action_type") == "pass"
        )
        production_out_risk = 0.0
        shadow_out_risk = 0.0
        for candidate in candidates:
            predicted_out = (
                candidate.get("value", {})
                .get("components", {})
                .get("outcome_transition", {})
                .get("out_of_play_probability")
            )
            if not isinstance(predicted_out, (int, float)):
                continue
            signature = (
                candidate.get("action_type"),
                json.dumps(candidate.get("target"), sort_keys=True),
                candidate.get("source"),
            )
            production_out_risk += production_probability_by_signature.get(
                signature, 0.0
            ) * float(predicted_out)
            shadow_out_risk += shadow_probability_by_signature.get(
                signature, 0.0
            ) * float(predicted_out)

        counts["decisions"] += 1
        expected["production_pass_probability"] += production_pass_probability
        expected["shadow_pass_probability"] += shadow_pass_probability
        expected["production_out_of_play_probability"] += production_out_risk
        expected["shadow_out_of_play_probability"] += shadow_out_risk
        metrics["decision_pass_probability_delta"].append(
            shadow_pass_probability - production_pass_probability
        )
        metrics["decision_out_of_play_probability_delta"].append(
            shadow_out_risk - production_out_risk
        )
        production_best = max(production_rows, key=lambda row: row[1])[0]
        shadow_best = max(shadow_rows, key=lambda row: row[1])[0]
        best_changed = (
            production_best.get("action_type"),
            production_best.get("target"),
            production_best.get("source"),
        ) != (
            shadow_best.get("action_type"),
            shadow_best.get("target"),
            shadow_best.get("source"),
        )
        counts[f"raw_best_changed={str(best_changed).lower()}"] += 1
        if best_changed and len(cases) < 40:
            cases.append({
                "tick": decision.get("tick"),
                "possession_id": decision.get("possession_id"),
                "team": decision.get("team"),
                "player_idx": decision.get("player_idx"),
                "production_best": {
                    "action": production_best.get("action_type"),
                    "target": production_best.get("target"),
                    "source": production_best.get("source"),
                    "score": production_best.get("value", {}).get("score"),
                    "restart": restart_data.get(id(production_best)),
                },
                "shadow_best": {
                    "action": shadow_best.get("action_type"),
                    "target": shadow_best.get("target"),
                    "source": shadow_best.get("source"),
                    "score": shadow_best.get("value", {}).get("score"),
                },
                "production_pass_probability": production_pass_probability,
                "shadow_pass_probability": shadow_pass_probability,
                "production_out_of_play_probability": production_out_risk,
                "shadow_out_of_play_probability": shadow_out_risk,
            })

    return {
        "scope": (
            "read-only candidate replay that adds already-projected retained/opposing "
            "restart branch values to pass outcome value after the existing restart wait, "
            "recomputes only the generic policy budget, and reuses the production two-stage "
            "bounded-rational probability distribution; world state, physics, choice, and RNG "
            "are unchanged"
        ),
        "counts": dict(sorted(counts.items())),
        "expected_totals": {
            field: round(value, 6) for field, value in sorted(expected.items())
        },
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "raw_best_change_cases": cases,
    }


def _pass_obstruction_trajectory_shadow(
    trace_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate obstruction-gated one-slot Pass trajectory selector replays."""
    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    expected: dict[str, Counter[str]] = {
        "production": Counter(),
        "collapsed": Counter(),
    }
    cases: list[dict[str, Any]] = []

    def direction(origin: Any, target: Any, attacking_right: bool) -> str:
        if not (
            isinstance(origin, list)
            and len(origin) >= 2
            and isinstance(target, list)
            and len(target) >= 2
        ):
            return "unknown"
        progress = (float(target[0]) - float(origin[0])) * (
            1.0 if attacking_right else -1.0
        )
        lateral = abs(float(target[1]) - float(origin[1]))
        return (
            "forward"
            if progress >= lateral
            else "backward"
            if -progress >= lateral
            else "lateral"
        )

    def summarize_selector(
        profile: str,
        selector: dict[str, Any],
        origin: Any,
        attacking_right: bool,
    ) -> dict[str, float]:
        decision: Counter[str] = Counter()
        for action in selector.get("actions", []):
            probability = action.get("overall_selection_probability")
            if not isinstance(probability, (int, float)):
                continue
            probability = float(probability)
            action_name = str(action.get("action") or "unknown")
            decision[f"action={action_name}"] += probability
            if action_name != "pass":
                continue
            decision["pass"] += probability
            is_long = action.get("is_long") is True
            is_lofted = action.get("lofted") is True
            length = "long" if is_long else "short"
            trajectory = "aerial" if is_lofted else "ground"
            pass_direction = direction(
                origin, action.get("target"), attacking_right
            )
            decision[f"pass:{length}"] += probability
            decision[f"pass:{trajectory}"] += probability
            decision[f"pass:{length}:{trajectory}"] += probability
            decision[f"pass:{length}:direction={pass_direction}"] += probability
            retention = action.get("retention_probability")
            if isinstance(retention, (int, float)):
                decision[f"weighted_retention:{length}"] += (
                    probability * float(retention)
                )
            distance_m = action.get("distance_m")
            if isinstance(distance_m, (int, float)):
                decision[f"weighted_distance:{length}"] += (
                    probability * float(distance_m)
                )
        for field, value in decision.items():
            expected[profile][field] += value
        return dict(decision)

    for entry in trace_entries:
        if entry.get("event") != "pass_obstruction_trajectory_counterfactual":
            continue
        counts["decisions"] += 1
        origin = entry.get("origin")
        attacking_right = bool(entry.get("attacking_right"))
        production = summarize_selector(
            "production",
            entry.get("production_selector", {}),
            origin,
            attacking_right,
        )
        collapsed = summarize_selector(
            "collapsed",
            entry.get("collapsed_selector", {}),
            origin,
            attacking_right,
        )
        trajectories = entry.get("trajectories", [])
        aerial_selected = [
            row
            for row in trajectories
            if row.get("selected_trajectory") == "aerial"
        ]
        counts["pass_intents"] += len(trajectories)
        counts["aerial_preferred_intents"] += len(aerial_selected)
        counts["decisions_with_aerial_preference"] += int(bool(aerial_selected))
        for row in trajectories:
            distance_m = row.get("distance_m")
            progress_m = row.get("progress_m")
            is_long = row.get("is_long") is True
            pass_direction = (
                "unknown"
                if not isinstance(distance_m, (int, float))
                or not isinstance(progress_m, (int, float))
                else "forward"
                if float(progress_m) >= max(
                    0.0,
                    (
                        float(distance_m) ** 2 - float(progress_m) ** 2
                    ) ** 0.5,
                )
                else "backward"
                if -float(progress_m) >= max(
                    0.0,
                    (
                        float(distance_m) ** 2 - float(progress_m) ** 2
                    ) ** 0.5,
                )
                else "lateral"
            )
            selected = str(row.get("selected_trajectory") or "unknown")
            length = "long" if is_long else "short"
            counts[f"intent:{length}:trajectory={selected}"] += 1
            counts[f"intent:{length}:direction={pass_direction}:trajectory={selected}"] += 1
            for field in (
                "aerial_minus_ground",
                "ground_retention",
                "aerial_retention",
                "distance_m",
                "progress_m",
            ):
                value = row.get(field)
                if isinstance(value, (int, float)):
                    metrics[
                        f"intent:{length}:trajectory={selected}:{field}"
                    ].append(float(value))
        production_long = production.get("pass:long", 0.0)
        collapsed_long = collapsed.get("pass:long", 0.0)
        production_pass = production.get("pass", 0.0)
        collapsed_pass = collapsed.get("pass", 0.0)
        metrics["decision:pass_probability_delta"].append(
            collapsed_pass - production_pass
        )
        metrics["decision:long_probability_delta"].append(
            collapsed_long - production_long
        )
        metrics["decision:aerial_probability"].append(
            collapsed.get("pass:aerial", 0.0)
        )
        if (
            abs(collapsed_long - production_long) > 1e-12
            or collapsed.get("pass:aerial", 0.0) > 1e-12
        ) and len(cases) < 60:
            cases.append({
                "tick": entry.get("tick"),
                "team": entry.get("team"),
                "player_idx": entry.get("player_idx"),
                "player_position": entry.get("player_position"),
                "production": production,
                "collapsed": collapsed,
                "aerial_preferred_intents": aerial_selected[:12],
            })

    expected_summary: dict[str, dict[str, float]] = {}
    for profile, values in expected.items():
        long_probability = values["pass:long"]
        short_probability = values["pass:short"]
        expected_summary[profile] = {
            field: round(value, 6) for field, value in sorted(values.items())
        }
        expected_summary[profile]["long_retention_given_long"] = round(
            values["weighted_retention:long"] / max(long_probability, 1e-12),
            6,
        )
        expected_summary[profile]["short_retention_given_short"] = round(
            values["weighted_retention:short"] / max(short_probability, 1e-12),
            6,
        )
        expected_summary[profile]["long_share_given_pass"] = round(
            long_probability / max(values["pass"], 1e-12), 6
        )
    return {
        "scope": (
            "read-only aggregation of pass_obstruction_trajectory_counterfactual: only "
            "ground Pass intents with a physically reachable interceptor receive an aerial "
            "mirror valued by the shared pipeline, the higher-valued trajectory occupies "
            "the same copied selector slot, and no state, production choice, execution, "
            "or RNG is changed"
        ),
        "counts": dict(sorted(counts.items())),
        "expected_selections": expected_summary,
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "cases": cases,
    }


def _switch_commitment_reset_lifecycle(
    trace_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    inertia = {
        "build_up": 0.16,
        "advance": 0.13,
        "recycle": 0.23,
        "switch": 0.19,
        "final_third": 0.12,
        "defend_block": 0.24,
        "defend_press": 0.13,
    }
    updates_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in trace_entries:
        if (
            entry.get("event") == "team_plan_update"
            and entry.get("team") in {"home", "away"}
            and isinstance(entry.get("tick"), int)
        ):
            updates_by_team[str(entry["team"])].append(entry)
    for rows in updates_by_team.values():
        rows.sort(key=lambda row: int(row["tick"]))

    counts: Counter[str] = Counter()
    metrics: dict[str, list[float]] = defaultdict(list)
    cases: list[dict[str, Any]] = []

    def candidates(row: dict[str, Any]) -> list[dict[str, float | str]]:
        return [
            candidate
            for candidate in row.get("candidates", [])
            if isinstance(candidate, dict)
            and isinstance(candidate.get("kind"), str)
            and isinstance(candidate.get("raw_value"), (int, float))
        ]

    def advance(
        current_kind: str, current_commitment: float, row: dict[str, Any]
    ) -> tuple[str, float, float]:
        rows = candidates(row)
        current_inertia = inertia.get(current_kind, 0.15)
        switch_cost = current_inertia * (
            0.30 + 0.70 * max(0.0, min(1.0, current_commitment))
        )
        selected = max(
            rows,
            key=lambda candidate: float(candidate["raw_value"])
            - (0.0 if candidate["kind"] == current_kind else switch_cost),
        )
        selected_kind = str(selected["kind"])
        selected_raw = float(selected["raw_value"])
        best_raw = max(float(candidate["raw_value"]) for candidate in rows)
        retained = selected_kind == current_kind
        evidence = max(0.0, min(1.0, selected_raw - best_raw + 1.0))
        next_commitment = max(
            0.0,
            min(
                1.0,
                current_commitment * (0.85 if retained else 0.45)
                + (0.20 if retained else 0.0)
                + 0.14 * evidence,
            ),
        )
        return selected_kind, next_commitment, switch_cost

    for team, updates in updates_by_team.items():
        run: list[dict[str, Any]] = []

        def close_run(rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
            points = [
                (float(row["ball_pos"][0]), float(row["ball_pos"][1]))
                for row in rows
                if isinstance(row.get("ball_pos"), list)
                and len(row["ball_pos"]) >= 2
            ]
            if len(points) != len(rows):
                return
            start_side = points[0][1] - 34.0
            crossing = next(
                (
                    index
                    for index, (_, y) in enumerate(points[1:], 1)
                    if start_side * (y - 34.0) < 0.0
                ),
                None,
            )
            counts["switch_runs"] += 1
            if crossing is None:
                counts["runs_without_completion"] += 1
                return
            counts["completed_runs"] += 1
            crossing_row = rows[crossing]
            prior = crossing_row.get("prior", {})
            current_kind = str(prior.get("kind") or "switch")
            production_commitment = float(prior.get("commitment", 0.0) or 0.0)
            metrics["production_commitment_at_completion"].append(
                production_commitment
            )
            cf_kind, cf_commitment, reset_switch_cost = advance(
                current_kind, 0.0, crossing_row
            )
            production_kind = str(crossing_row.get("selected") or "unknown")
            counts[
                f"completion_transition={production_kind}->{cf_kind}"
            ] += 1
            counts[
                f"completion_changed={str(cf_kind != production_kind).lower()}"
            ] += 1
            metrics["reset_switch_cost"].append(reset_switch_cost)
            first_non_switch_offset = 0 if cf_kind != "switch" else None
            simulated = [cf_kind]
            for offset, row in enumerate(rows[crossing + 1 :], 1):
                cf_kind, cf_commitment, _ = advance(cf_kind, cf_commitment, row)
                simulated.append(cf_kind)
                if first_non_switch_offset is None and cf_kind != "switch":
                    first_non_switch_offset = offset
            production_updates_after = len(rows) - crossing - 1
            metrics["production_updates_after_completion"].append(
                float(production_updates_after)
            )
            if first_non_switch_offset is None:
                counts["counterfactual_never_exits_within_run"] += 1
                saved = 0
            else:
                counts["counterfactual_exits_within_run"] += 1
                counts[
                    f"counterfactual_first_non_switch={simulated[first_non_switch_offset]}"
                ] += 1
                metrics["counterfactual_updates_to_exit"].append(
                    float(first_non_switch_offset)
                )
                saved = max(production_updates_after - first_non_switch_offset, 0)
            metrics["switch_updates_saved"].append(float(saved))
            if len(cases) < 30:
                cases.append(
                    {
                        "team": team,
                        "start_tick": rows[0].get("tick"),
                        "completion_tick": crossing_row.get("tick"),
                        "end_tick": rows[-1].get("tick"),
                        "production_commitment": production_commitment,
                        "production_selected": production_kind,
                        "commitment_reset_selected": simulated[0],
                        "counterfactual_updates_to_exit": first_non_switch_offset,
                        "production_updates_after_completion": production_updates_after,
                        "switch_updates_saved": saved,
                        "counterfactual_sequence": simulated,
                    }
                )

        for entry in updates:
            if entry.get("selected") == "switch":
                run.append(entry)
            else:
                close_run(run)
                run = []
        close_run(run)

    return {
        "scope": (
            "read-only replay of completed Switch runs with only TeamPlanState.commitment "
            "reset to zero at the first perceived lateral center crossing. Every plan remains "
            "eligible; raw candidate values and the normal inertia/commitment recurrence are "
            "reused. World state, signals, movement, selection, and RNG are unchanged"
        ),
        "counts": dict(sorted(counts.items())),
        "metrics": {
            field: _distribution(values) for field, values in sorted(metrics.items())
        },
        "cases": cases,
    }


def _run(args: argparse.Namespace) -> dict[str, Any]:
    from psl_core.engine_v2 import load_config_from_service
    from psl_core.engine_v2.rust_bridge import run_match
    from server.database import Database
    from server.services.game_config import GameConfigService

    with tempfile.TemporaryDirectory(prefix="psl-stable-control-plan-") as temp_dir:
        snapshot = Path(temp_dir) / "psl.db"
        with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
        db = Database(str(snapshot))
        try:
            home_cards, home_formation = _build_cards(db, args.home_qq)
            away_cards, away_formation = _build_cards(db, args.away_qq)
            config = load_config_from_service(GameConfigService(db))
            config.trace.detail = args.trace_detail
            config.total_ticks = args.ticks
            config.half_ticks = args.ticks // 2
            response = run_match(
                home_cards,
                away_cards,
                home_formation,
                away_formation,
                config,
                seed=args.seed,
            )
        finally:
            db.close()

    trace_entries = response.get("trace", {}).get("entries", [])
    stable_control_entries = [
        entry
        for entry in trace_entries
        if entry.get("event") == "stable_control_team_plan_counterfactual"
    ]
    return {
        "seed": args.seed,
        "ticks": args.ticks,
        "formations": {"home": home_formation, "away": away_formation},
        "score": {
            "home": response.get("home_score"),
            "away": response.get("away_score"),
        },
        "match_clock": response.get("match_clock", {}),
        "home_stats": response.get("home_stats", {}),
        "away_stats": response.get("away_stats", {}),
        "trace_counts": {
            "entries": len(trace_entries),
            "stable_control_plan_handoffs": len(stable_control_entries),
        },
        "stable_control_team_plan_counterfactual": {
            "scope": (
                "read-only one-shot replay immediately after stable Held ownership; "
                "the production plan, signals, movement, selection, and RNG are unchanged"
            ),
            **_plan_delta_summary(stable_control_entries),
            "overlap_with_prior_ball_state_shadows": _prior_shadow_overlap(
                trace_entries
            ),
        },
        "pending_pass_team_plan_lifecycle": _pending_pass_plan_lifecycle(
            trace_entries
        ),
        "control_acquisition_lifecycle": _control_acquisition_lifecycle(
            trace_entries, response.get("trace", {}).get("decisions", [])
        ),
        "tactical_possession_reversal_lifecycle": (
            _tactical_possession_reversal_lifecycle(
                trace_entries,
                response.get("trace", {}).get("decisions", []),
                config.tick_duration,
            )
        ),
        "pass_boundary_control_lifecycle": _pass_boundary_control_lifecycle(
            trace_entries,
            config.pitch_length,
            config.pitch_width,
        ),
        "flight_defense_counterfactual_lifecycle": (
            _flight_defense_counterfactual_lifecycle(trace_entries)
        ),
        "completed_pass_cadence_lifecycle": _completed_pass_cadence_lifecycle(
            trace_entries, config.tick_duration
        ),
        "restart_branch_value_shadow": _restart_branch_value_shadow(
            response.get("trace", {}).get("decisions", []),
            config.tick_duration,
            {
                "throw_in": float(config.throw_in_restart_ticks),
                "corner": float(config.corner_restart_ticks),
                "goal_kick": float(config.goal_kick_restart_ticks),
            },
        ),
        "pass_obstruction_trajectory_shadow": _pass_obstruction_trajectory_shadow(
            trace_entries
        ),
        "switch_commitment_reset_lifecycle": _switch_commitment_reset_lifecycle(
            trace_entries
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "psl.db")
    parser.add_argument("--home-qq", type=int, default=10001)
    parser.add_argument("--away-qq", type=int, default=10002)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--ticks", type=int, default=900)
    parser.add_argument(
        "--trace-detail",
        choices=("chosen", "top_candidates", "full"),
        default="full",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--reversal-only",
        action="store_true",
        help=(
            "Serialize only the team-control reversal lifecycle and core match context; "
            "the underlying full-trace run is unchanged."
        ),
    )
    args = parser.parse_args()
    if args.ticks < 2:
        parser.error("--ticks must be at least 2")
    payload = _run(args)
    if args.reversal_only:
        payload = {
            key: payload[key]
            for key in (
                "seed",
                "ticks",
                "formations",
                "score",
                "match_clock",
                "home_stats",
                "away_stats",
                "trace_counts",
                "tactical_possession_reversal_lifecycle",
            )
        }
    report = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
