from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_statsbomb_support_geometry import (
    _comparison,
    _possession_team_interruption_counts,
    audit_360_geometry,
    audit_epl_events,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_point(x_m: float, y_m: float) -> list[float]:
    return [x_m * 120.0 / 105.0, y_m * 80.0 / 68.0]


def test_epl_pass_structure_uses_metric_distance_and_excludes_crosses_and_throw_ins(
    tmp_path: Path,
) -> None:
    path = tmp_path / "1.json"
    events = [
        {
            "possession": 1,
            "possession_team": {"name": "Alpha"},
            "type": {"name": "Pass"},
            "location": _provider_point(0, 0),
            "pass": {"end_location": _provider_point(5, 0)},
        },
        {
            "possession": 2,
            "possession_team": {"name": "Alpha"},
            "type": {"name": "Pass"},
            "location": _provider_point(0, 0),
            "pass": {
                "end_location": _provider_point(15, 0),
                "outcome": {"name": "Incomplete"},
            },
        },
        {
            "possession": 3,
            "possession_team": {"name": "Beta"},
            "type": {"name": "Pass"},
            "location": _provider_point(0, 0),
            "pass": {"end_location": _provider_point(40, 0), "cross": True},
        },
        {
            "possession": 4,
            "possession_team": {"name": "Beta"},
            "type": {"name": "Pass"},
            "location": _provider_point(0, 0),
            "pass": {
                "end_location": _provider_point(8, 0),
                "type": {"name": "Throw-in"},
            },
        },
    ]
    _write(path, events)

    audit = audit_epl_events([path])

    assert audit["pass_count"] == 2
    assert audit["pass_distance_m"]["median"] == 10.0
    assert audit["completion_rate"] == 0.5
    assert audit["distance_bands"]["0-10m"]["attempt_share"] == 0.5
    assert audit["distance_bands"]["10-20m"]["attempt_share"] == 0.5
    assert audit["fine_distance_completion"] == {
        "4-8m": {"attempted": 1, "completed": 1, "completion_rate": 1.0},
        "12-16m": {"attempted": 1, "completed": 0, "completion_rate": 0.0},
    }
    interruption = audit["possession_interruption_hazard"]
    assert interruption["provider_possessions"] == 4
    assert interruption["team_control_interruptions"] == 1
    assert interruption["hazard_per_active_second"] == round(1 / 3361, 9)


def test_possession_interruption_ignores_same_team_provider_splits() -> None:
    events = [
        {"possession": 1, "possession_team": {"name": "Alpha"}},
        {"possession": 2, "possession_team": {"name": "Alpha"}},
        {"possession": 3, "possession_team": {"name": "Beta"}},
        {"possession": 3, "possession_team": {"name": "Beta"}},
        {"possession": 4, "possession_team": {"name": "Alpha"}},
    ]

    assert _possession_team_interruption_counts(events) == (4, 2, 0)


def test_360_audit_separates_support_geometry_from_endpoint_proxy(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    frames_dir = tmp_path / "frames"
    event_path = events_dir / "1.json"
    actor = _provider_point(52.5, 34.0)
    teammate_locations = [
        _provider_point(58.5, 34.0),
        _provider_point(52.5, 46.0),
        _provider_point(40.0, 34.0),
        _provider_point(65.0, 34.0),
        _provider_point(52.5, 20.0),
        _provider_point(35.0, 20.0),
        _provider_point(70.0, 48.0),
    ]
    events = [{
        "id": "pass-1",
        "type": {"name": "Pass"},
        "location": actor,
        "pass": {"end_location": _provider_point(62.5, 34.0)},
    }]
    frame = {
        "event_uuid": "pass-1",
        "visible_area": [0, 0, 120, 0, 120, 80, 0, 80],
        "freeze_frame": [
            {"actor": True, "teammate": True, "location": actor},
            *[
                {"actor": False, "teammate": True, "location": location}
                for location in teammate_locations
            ],
            {
                "actor": False,
                "teammate": False,
                "location": _provider_point(54.0, 34.0),
            },
        ],
    }
    _write(event_path, events)
    _write(frames_dir / "1.json", [frame])

    audit = audit_360_geometry([event_path], frames_dir)

    assert audit["matched_pass_frames"] == 1
    assert audit["nearest_visible_teammate_m"]["median"] == 6.0
    high_pressure = audit["nearest_visible_teammate_by_nearest_opponent"]["0-2m"]
    assert high_pressure["under_10m_share"] == 1.0
    high_pressure_passes = audit["pass_distance_by_nearest_opponent"]["0-2m"]
    assert high_pressure_passes["median"] == 10.0
    assert high_pressure_passes["distance_bands"]["10-20m"] == {
        "attempted": 1,
        "attempt_share": 1.0,
    }
    proxy = audit["pass_end_to_nearest_visible_teammate_at_release_m"]
    assert proxy["median"] == 2.5
    assert proxy["interpretation"] == "proxy only; not an intended-receiver measurement"
    opponent_proxy = audit[
        "pass_end_to_nearest_visible_opponent_at_release_m"
    ]
    assert opponent_proxy["median"] == 8.5
    assert opponent_proxy["under_10m_share"] == 1.0
    assert "not arrival pressure" in opponent_proxy["interpretation"]
    assert audit[
        "pass_end_to_nearest_visible_opponent_by_pass_distance"
    ]["10-20m"]["median"] == 8.5
    assert "intended-receiver endpoint offset is unavailable" in " ".join(audit["limitations"])
    assert audit["high_visible_coverage_support_density"]["middle"][
        "nearest_m"
    ]["median"] == 6.0


def test_comparison_does_not_authorize_a_production_change_from_one_trace() -> None:
    geometry = {
        "nearest_visible_teammate_by_nearest_opponent": {
            "0-2m": {"count": 100, "median": 7.0, "under_10m_share": 0.8}
        }
    }
    engine = {
        "full_trace": {
            "support_by_nearest_opponent": {
                "0_2m": {"count": 20, "median": 12.0, "under_10m_share": 0.3}
            }
        }
    }

    comparison = _comparison(None, geometry, engine)

    assert comparison["status"] == "support_gap_supported_not_causal"
    assert comparison["production_change_authorized"] is False
