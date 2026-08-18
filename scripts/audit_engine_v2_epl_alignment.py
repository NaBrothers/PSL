#!/usr/bin/env python3
"""Aggregate engine-v2 fixture reports and audit them against EPL 2024/25."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

try:
    from scripts.diagnose_engine_v2_match_pace import PREMIER_LEAGUE_2024_25_BENCHMARK
except ModuleNotFoundError:
    from diagnose_engine_v2_match_pace import PREMIER_LEAGUE_2024_25_BENCHMARK


def _nested(payload: dict[str, Any], *path: str, default: Any = 0) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key, default)
    return value


def _target_metrics() -> dict[str, float]:
    benchmark = PREMIER_LEAGUE_2024_25_BENCHMARK
    matches = float(benchmark["matches"])
    totals = benchmark["totals"]
    count_timebase_scale = (90.0 * 60.0) / benchmark["average_match_duration"]["seconds"]
    ball_in_play_minutes = (
        benchmark["ball_in_play"]["average_seconds"]
        / benchmark["average_match_duration"]["seconds"]
        * 90.0
    )
    def fixed_90_count(total: float) -> float:
        return total / matches * count_timebase_scale

    passes = fixed_90_count(totals["passes"])
    long_balls = fixed_90_count(totals["long_balls"])
    return {
        "ball_in_play_minutes": ball_in_play_minutes,
        "fouls": fixed_90_count(totals["fouls"]),
        "passes": passes,
        "passes_per_active_play_minute": passes / ball_in_play_minutes,
        "pass_success_rate": totals["passes_completed"] / totals["passes"] * 100.0,
        "shots": fixed_90_count(totals["shots"]),
        "shots_on_target": fixed_90_count(totals["shots_on_target"]),
        "goals": fixed_90_count(totals["goals"]),
        "goal_conversion_rate": totals["goals"] / totals["shots"] * 100.0,
        "long_balls": long_balls,
        "long_ball_accuracy": totals["accurate_long_balls"] / totals["long_balls"] * 100.0,
        "long_ball_share": long_balls / passes * 100.0,
        "penalties": fixed_90_count(84.0),
        "penalty_goals": fixed_90_count(69.0),
    }


def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    match_count = sum(int(report.get("match_count", 0)) for report in reports)
    if match_count <= 0:
        raise ValueError("reports must contain at least one match")
    attempted = completed = shots = shots_on_target = goals = 0.0
    long_attempted = long_accurate = short_attempted = short_completed = 0.0
    goal_kick_long_completed_excluded = 0.0
    opponent_contact_long_completed_excluded = 0.0
    match_seconds = active_seconds = fouls = corners = penalties = penalty_goals = 0.0
    last_line_blocks = 0.0
    ball_state_seconds: Counter[str] = Counter()
    distance_bands: dict[str, Counter[str]] = {}
    restart_profiles: dict[str, Counter[str]] = {}
    provider_restart_profiles: dict[str, Counter[str]] = {}
    delivery_profiles: dict[str, Counter[str]] = {}
    integrity: list[str] = []
    for report in reports:
        count = int(report["match_count"])
        aggregate = report["aggregate"]
        alignment = aggregate["premier_league_alignment"]
        metrics = alignment["metrics"]
        diagnostics = alignment["engine_scope_diagnostics"]
        core = aggregate["metric_integrity"]["core_totals"]
        provider_lengths = aggregate["pass_causality"]["breakdown"]["by_provider_pass_scope_length"]
        pass_breakdown = aggregate["pass_causality"]["breakdown"]
        attempted += float(diagnostics["comparable_non_cross_passes_per_match"]) * count
        completed += float(diagnostics["comparable_non_cross_completed_passes_per_match"]) * count
        shots += float(core["shots"])
        shots_on_target += float(core["shots_on_target"])
        goals += float(core["stat_goals"])
        short_attempted += float(_nested(provider_lengths, "short", "attempted"))
        short_completed += float(_nested(provider_lengths, "short", "completed"))
        long_attempted += float(_nested(provider_lengths, "long", "attempted"))
        report_long_completed = float(_nested(provider_lengths, "long", "completed"))
        report_goal_kick_long_completed = float(
            _nested(
                pass_breakdown,
                "by_restart_origin_and_length",
                "goal_kick:long",
                "completed",
            )
        )
        report_opponent_contact_long_completed = float(
            _nested(
                aggregate,
                "pass_causality",
                "provider_long_completion_contact",
                "non_goal_kick_with_opponent_contact",
            )
        )
        long_accurate += max(
            report_long_completed
            - report_goal_kick_long_completed
            - report_opponent_contact_long_completed,
            0.0,
        )
        goal_kick_long_completed_excluded += report_goal_kick_long_completed
        opponent_contact_long_completed_excluded += (
            report_opponent_contact_long_completed
        )
        active_seconds += float(aggregate["match_clock"]["average_active_play_seconds"]) * count
        match_seconds += float(aggregate["match_clock"]["average_match_seconds"]) * count
        fouls += float(metrics["fouls"]["current"]) * count
        corners += float(diagnostics["corner_restarts_per_match"]) * count
        penalties += float(diagnostics["penalty_restarts_per_match"]) * count
        penalty_goals += float(diagnostics["penalty_goals_per_match"]) * count
        last_line_blocks += float(_nested(aggregate, "shot_outcomes", "last_line_blocks", "total"))
        tick_duration = float(_nested(report, "runtime_config", "tick_duration", default=1.0))
        for state, ticks in aggregate["match_clock"].get("average_ball_state_ticks", {}).items():
            ball_state_seconds[state] += float(ticks) * tick_duration * count
        for band, data in pass_breakdown.get("by_provider_pass_scope_distance", {}).items():
            bucket = distance_bands.setdefault(band, Counter())
            bucket["attempted"] += float(data.get("attempted", 0))
            bucket["completed"] += float(data.get("completed", 0))
        for profile, data in pass_breakdown.get("by_restart_origin", {}).items():
            bucket = restart_profiles.setdefault(profile, Counter())
            bucket["attempted"] += float(data.get("attempted", 0))
            bucket["completed"] += float(data.get("completed", 0))
        for profile, data in pass_breakdown.get(
            "by_provider_pass_scope_restart_origin", {}
        ).items():
            bucket = provider_restart_profiles.setdefault(profile, Counter())
            bucket["attempted"] += float(data.get("attempted", 0))
            bucket["completed"] += float(data.get("completed", 0))
        for profile, data in pass_breakdown.get("by_profile_and_delivery", {}).items():
            bucket = delivery_profiles.setdefault(profile, Counter())
            bucket["attempted"] += float(data.get("attempted", 0))
            bucket["completed"] += float(data.get("completed", 0))
        integrity.append(aggregate["metric_integrity"]["status"])
    current = {
        "ball_in_play_minutes": (
            active_seconds / max(match_seconds, 1.0) * 90.0
        ),
        "fouls": fouls / match_count,
        "passes": attempted / match_count,
        "passes_per_active_play_minute": (
            attempted / max(active_seconds / 60.0, 1.0)
        ),
        "pass_success_rate": completed / max(attempted, 1.0) * 100.0,
        "short_passes": short_attempted / match_count,
        "short_pass_accuracy": short_completed / max(short_attempted, 1.0) * 100.0,
        "shots": shots / match_count,
        "shots_on_target": shots_on_target / match_count,
        "provider_shots_on_target": (shots_on_target + last_line_blocks) / match_count,
        "goals": goals / match_count,
        "goal_conversion_rate": goals / max(shots, 1.0) * 100.0,
        "long_balls": long_attempted / match_count,
        "long_ball_accuracy": long_accurate / max(long_attempted, 1.0) * 100.0,
        "long_ball_share": long_attempted / max(attempted, 1.0) * 100.0,
        "corners": corners / match_count,
        "penalties": penalties / match_count,
        "penalty_goals": penalty_goals / match_count,
    }
    targets = _target_metrics()
    relative_gaps = {metric: (current[metric] - target) / target for metric, target in targets.items()}
    def profile_summary(groups: dict[str, Counter[str]]) -> dict[str, dict[str, float]]:
        return {
            profile: {
                "attempted": round(values["attempted"], 6),
                "completed": round(values["completed"], 6),
                "completion_rate": round(
                    values["completed"] / max(values["attempted"], 1.0) * 100.0,
                    6,
                ),
                "attempt_share": round(
                    values["attempted"] / max(sum(v["attempted"] for v in groups.values()), 1.0)
                    * 100.0,
                    6,
                ),
            }
            for profile, values in sorted(groups.items())
        }

    mechanism_diagnostics = {
        "scope": (
            "engine-internal mechanism diagnostics; these fields are not EPL targets and are "
            "used to attribute rate changes without changing provider metric definitions"
        ),
        "active_state_seconds_per_provider_scope_pass": {
            state: round(seconds / max(attempted, 1.0), 6)
            for state, seconds in sorted(ball_state_seconds.items())
            if state != "dead"
        },
        "all_state_seconds_per_provider_scope_pass": {
            state: round(seconds / max(attempted, 1.0), 6)
            for state, seconds in sorted(ball_state_seconds.items())
        },
        "match_clock_comparability": {
            "engine_average_match_minutes": round(match_seconds / match_count / 60.0, 6),
            "engine_active_play_share": round(
                active_seconds / max(match_seconds, 1.0), 6
            ),
            "epl_target_ball_in_play_minutes": round(
                targets["ball_in_play_minutes"], 6
            ),
            "epl_average_match_minutes": round(
                PREMIER_LEAGUE_2024_25_BENCHMARK["average_match_duration"]["seconds"]
                / 60.0,
                6,
            ),
            "comparison_caveat": (
                "the engine and EPL active-play times are both normalized to a fixed 90 "
                "minutes because the published EPL absolute total includes added time"
            ),
        },
        "pass_distance_bands": profile_summary(distance_bands),
        "pass_restart_origins": profile_summary(restart_profiles),
        "provider_scope_pass_restart_origins": (
            profile_summary(provider_restart_profiles)
            if provider_restart_profiles
            else {
                "status": "unavailable_in_source_report",
                "scope": (
                    "legacy source reports expose restart origins across all engine pass "
                    "releases, including crosses"
                ),
            }
        ),
        "pass_profile_and_delivery": profile_summary(delivery_profiles),
        "long_ball_accuracy_scope": {
            "total_long_balls": round(long_attempted, 6),
            "accurate_long_balls": round(long_accurate, 6),
            "goal_kick_long_completions_excluded_from_accurate": round(
                goal_kick_long_completed_excluded, 6
            ),
            "opponent_contact_long_completions_excluded_from_accurate": round(
                opponent_contact_long_completed_excluded, 6
            ),
            "definition": (
                "Opta total_long_balls counts passes longer than 35 yards; "
                "accurate_long_balls uses successful passes over the same distance but "
                "excludes crosses, throw-ins, keeper throws, goal kicks, and any "
                "terminal opponent touch"
            ),
        },
    }
    provider_distance_attempted = sum(
        values["attempted"] for values in distance_bands.values()
    )
    provider_distance_completed = sum(
        values["completed"] for values in distance_bands.values()
    )
    # The source report exposes comparable per-match totals rounded to three
    # decimals, while distance bands retain integer sample totals.  Scaling a
    # displayed mean back by the match count can therefore differ by at most
    # half of one displayed unit per match without any event-accounting gap.
    distance_scope_tolerance = match_count * 0.0005 + 1e-9
    distance_scope_closed = (
        abs(provider_distance_attempted - attempted) <= distance_scope_tolerance
        and abs(provider_distance_completed - completed) <= distance_scope_tolerance
    )
    mechanism_diagnostics["pass_distance_scope_integrity"] = {
        "status": "ok" if distance_scope_closed else "error",
        "provider_distance_attempted": round(provider_distance_attempted, 6),
        "provider_distance_completed": round(provider_distance_completed, 6),
        "comparable_passes_attempted": round(attempted, 6),
        "comparable_passes_completed": round(completed, 6),
        "rounding_tolerance": round(distance_scope_tolerance, 6),
        "scope": "non-cross provider-compatible passes on both sides",
    }
    return {
        "match_count": match_count,
        "current": {key: round(value, 6) for key, value in current.items()},
        "targets": {key: round(value, 6) for key, value in targets.items()},
        "relative_gaps": {key: round(value, 6) for key, value in relative_gaps.items()},
        "mechanism_diagnostics": mechanism_diagnostics,
        "integrity": {
            "status": (
                "ok"
                if all(status == "ok" for status in integrity) and distance_scope_closed
                else "error"
            ),
            "report_statuses": integrity,
        },
        "completion": {
            "achieved": False,
            "reason": "objective requires all directly comparable EPL metrics to align; material gaps remain",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    serialized = json.dumps(aggregate_reports(reports), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
