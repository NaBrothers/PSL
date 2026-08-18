#!/usr/bin/env python3
"""Audit real pass/support geometry before changing engine-v2 spacing.

The two real-data scopes are deliberately separate:

* Premier League 2015/16 event data supplies pass-distance structure, but the
  StatsBomb open-data release has no 360 frames for that competition.
* Bundesliga 2023/24 supplies 360 freeze frames for support geometry. Those
  frames cover only the visible area and do not identify the intended receiver.

The script is read-only with respect to the engine. The fetch option only
downloads the exact public StatsBomb inputs into the requested data root.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from math import acos, degrees, hypot
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable
from urllib.request import Request, urlopen


STATSBOMB_RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
EPL_COMPETITION_ID = 2
EPL_SEASON_ID = 27
EPL_SEASON = "2015/2016"
EPL_ACTIVE_PLAY_SECONDS_2015_16 = 56 * 60 + 1
EPL_ACTIVE_PLAY_SOURCE_2015_16 = (
    "https://www.freebetoffers.org.uk/articles/"
    "how-long-is-the-ball-in-play-during-a-typical-football-match/"
)
THREE_SIXTY_COMPETITION_ID = 9
THREE_SIXTY_SEASON_ID = 281
THREE_SIXTY_SEASON = "2023/2024"
DEFAULT_360_MATCHES = 30
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
STATSBOMB_LENGTH = 120.0
STATSBOMB_WIDTH = 80.0
ENGINE_INTERCEPTION_REACH_M = 3.5


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def _distribution(values: list[float]) -> dict[str, Any]:
    p10 = _quantile(values, 0.10)
    p90 = _quantile(values, 0.90)
    return {
        "count": len(values),
        "mean": round(mean(values), 6) if values else None,
        "median": round(median(values), 6) if values else None,
        "p10": round(p10, 6) if p10 is not None else None,
        "p90": round(p90, 6) if p90 is not None else None,
    }


def _point_m(point: list[float]) -> tuple[float, float]:
    return (
        float(point[0]) * PITCH_LENGTH_M / STATSBOMB_LENGTH,
        float(point[1]) * PITCH_WIDTH_M / STATSBOMB_WIDTH,
    )


def _distance_m(left: list[float], right: list[float]) -> float:
    left_m = _point_m(left)
    right_m = _point_m(right)
    return hypot(left_m[0] - right_m[0], left_m[1] - right_m[1])


def _pass_distance_band(distance_m: float) -> str:
    if distance_m < 10.0:
        return "0-10m"
    if distance_m < 20.0:
        return "10-20m"
    if distance_m < 30.0:
        return "20-30m"
    return "30m+"


def _fine_pass_distance_band(distance_m: float) -> str:
    lower = int(max(distance_m, 0.0) // 4.0) * 4
    if lower >= 48:
        return "48m+"
    return f"{lower}-{lower + 4}m"


def _pressure_band(distance_m: float) -> str:
    if distance_m < 2.0:
        return "0-2m"
    if distance_m < 4.0:
        return "2-4m"
    if distance_m < 6.0:
        return "4-6m"
    if distance_m < 10.0:
        return "6-10m"
    return "10m+"


def _engine_lane_risk(
    origin: list[float], target: list[float], opponents: list[list[float]]
) -> float:
    origin_m = _point_m(origin)
    target_m = _point_m(target)
    dx = target_m[0] - origin_m[0]
    dy = target_m[1] - origin_m[1]
    length = hypot(dx, dy)
    if length < 1.0:
        return 1.0
    nx = dx / length
    ny = dy / length
    risk = 0.0
    reach = ENGINE_INTERCEPTION_REACH_M * 1.8
    for opponent in opponents:
        opponent_m = _point_m(opponent)
        rel_x = opponent_m[0] - origin_m[0]
        rel_y = opponent_m[1] - origin_m[1]
        projection = rel_x * nx + rel_y * ny
        if projection <= 1.5 or projection >= length - 1.5:
            continue
        perpendicular = abs(rel_x * ny - rel_y * nx)
        if perpendicular < reach:
            lane_share = 1.0 - perpendicular / reach
            centrality = 1.0 - abs(projection / length - 0.5) * 0.45
            risk += lane_share * centrality
    length_factor = min(1.4, length / 35.0)
    return max(0.0, min(1.0, risk * 0.28 * length_factor))


def _zone(origin: list[float]) -> str:
    if float(origin[0]) < 40.0:
        return "defensive"
    if float(origin[0]) < 80.0:
        return "middle"
    return "final"


def _eligible_pass(event: dict[str, Any]) -> bool:
    if (event.get("type") or {}).get("name") != "Pass":
        return False
    pass_data = event.get("pass") or {}
    return (
        (pass_data.get("type") or {}).get("name") != "Throw-in"
        and pass_data.get("cross") is not True
        and isinstance(event.get("location"), list)
        and isinstance(pass_data.get("end_location"), list)
    )


def _possession_team_interruption_counts(
    events: Iterable[dict[str, Any]],
) -> tuple[int, int, int]:
    """Return provider possessions, team switches, and inconsistent IDs.

    StatsBomb can start a new possession ID while the same team remains the
    possession team. Engine-v2 increments its possession ID only when the
    controlling team changes, so only adjacent possession-team changes are a
    like-for-like interruption count.
    """
    ordered: list[tuple[int, str]] = []
    team_by_possession: dict[int, str] = {}
    inconsistent_ids: set[int] = set()
    for event in events:
        possession_id = event.get("possession")
        possession_team = (event.get("possession_team") or {}).get("name")
        if not isinstance(possession_id, int) or not isinstance(possession_team, str):
            continue
        previous_team = team_by_possession.get(possession_id)
        if previous_team is not None:
            if previous_team != possession_team:
                inconsistent_ids.add(possession_id)
            continue
        team_by_possession[possession_id] = possession_team
        ordered.append((possession_id, possession_team))
    team_switches = sum(
        left_team != right_team
        for (_, left_team), (_, right_team) in zip(ordered, ordered[1:])
    )
    return len(ordered), team_switches, len(inconsistent_ids)


def _ordered_event_paths(
    events_dir: Path, matches_manifest: Path | None = None, limit: int | None = None
) -> list[Path]:
    if matches_manifest is None:
        paths = sorted(events_dir.glob("*.json"), key=lambda path: int(path.stem))
    else:
        matches = _read_json(matches_manifest)
        paths = [events_dir / f"{match['match_id']}.json" for match in matches]
    if limit is not None:
        paths = paths[:limit]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        preview = ", ".join(missing[:3])
        raise FileNotFoundError(f"missing StatsBomb event inputs: {preview}")
    return paths


def audit_epl_events(event_paths: Iterable[Path]) -> dict[str, Any]:
    paths = list(event_paths)
    pass_distances: list[float] = []
    carry_distances: list[float] = []
    completed = 0
    distance_bands: Counter[str] = Counter()
    fine_distance: dict[str, Counter[str]] = defaultdict(Counter)
    fine_distance_by_height: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    distance_direction: dict[str, Counter[str]] = defaultdict(Counter)
    distance_zone: dict[str, Counter[str]] = defaultdict(Counter)
    provider_possessions = 0
    possession_team_interruptions = 0
    inconsistent_possession_team_ids = 0
    for path in paths:
        events = _read_json(path)
        if not isinstance(events, list):
            raise ValueError(f"expected event list in {path}")
        possessions, interruptions, inconsistent_ids = (
            _possession_team_interruption_counts(events)
        )
        provider_possessions += possessions
        possession_team_interruptions += interruptions
        inconsistent_possession_team_ids += inconsistent_ids
        for event in events:
            if _eligible_pass(event):
                pass_data = event["pass"]
                distance_m = _distance_m(event["location"], pass_data["end_location"])
                pass_distances.append(distance_m)
                distance_bands[_pass_distance_band(distance_m)] += 1
                is_completed = not pass_data.get("outcome")
                completed += int(is_completed)
                fine_band = _fine_pass_distance_band(distance_m)
                height = str((pass_data.get("height") or {}).get("name") or "Unknown")
                fine_distance[fine_band]["attempted"] += 1
                fine_distance[fine_band]["completed"] += int(is_completed)
                fine_distance_by_height[height][fine_band]["attempted"] += 1
                fine_distance_by_height[height][fine_band]["completed"] += int(
                    is_completed
                )
                dx_m = (
                    float(pass_data["end_location"][0]) - float(event["location"][0])
                ) * PITCH_LENGTH_M / STATSBOMB_LENGTH
                dy_m = (
                    float(pass_data["end_location"][1]) - float(event["location"][1])
                ) * PITCH_WIDTH_M / STATSBOMB_WIDTH
                direction = (
                    "forward"
                    if abs(dx_m) >= abs(dy_m) and dx_m > 0.0
                    else "backward"
                    if abs(dx_m) >= abs(dy_m)
                    else "lateral"
                )
                broad_band = _pass_distance_band(distance_m)
                distance_direction[broad_band][direction] += 1
                distance_zone[broad_band][_zone(event["location"])] += 1
            elif (event.get("type") or {}).get("name") == "Carry":
                end = (event.get("carry") or {}).get("end_location")
                if isinstance(event.get("location"), list) and isinstance(end, list):
                    carry_distances.append(_distance_m(event["location"], end))
    attempted = len(pass_distances)
    return {
        "source": {
            "provider": "StatsBomb open-data",
            "competition": "Premier League",
            "season": EPL_SEASON,
            "competition_id": EPL_COMPETITION_ID,
            "season_id": EPL_SEASON_ID,
            "matches_url": f"{STATSBOMB_RAW}/matches/{EPL_COMPETITION_ID}/{EPL_SEASON_ID}.json",
            "event_url_template": f"{STATSBOMB_RAW}/events/{{match_id}}.json",
        },
        "scope": (
            "all StatsBomb Pass events with a start/end location, excluding crosses and "
            "throw-ins; distances convert the 120x80 provider pitch to 105x68 metres"
        ),
        "match_count": len(paths),
        "pass_count": attempted,
        "passes_per_match": round(attempted / len(paths), 6) if paths else None,
        "completion_rate": round(completed / attempted, 6) if attempted else None,
        "pass_distance_m": _distribution(pass_distances),
        "carry_distance_m": _distribution(carry_distances),
        "long_32m_share": round(
            sum(distance >= 32.0 for distance in pass_distances) / attempted, 6
        ) if attempted else None,
        "possession_interruption_hazard": {
            "scope": (
                "adjacent StatsBomb possession IDs whose possession_team changes; "
                "same-team provider possession splits are excluded to match engine-v2, "
                "whose possession_id increments only when the controlling team changes"
            ),
            "provider_possessions": provider_possessions,
            "provider_possessions_per_match": round(
                provider_possessions / len(paths), 6
            ) if paths else None,
            "team_control_interruptions": possession_team_interruptions,
            "team_control_interruptions_per_match": round(
                possession_team_interruptions / len(paths), 6
            ) if paths else None,
            "inconsistent_possession_team_ids": inconsistent_possession_team_ids,
            "active_play_seconds_per_match": EPL_ACTIVE_PLAY_SECONDS_2015_16,
            "active_play_source": EPL_ACTIVE_PLAY_SOURCE_2015_16,
            "active_play_source_quality": (
                "secondary historical compilation; season-matched but independent "
                "of the StatsBomb event feed"
            ),
            "hazard_per_active_second": round(
                possession_team_interruptions
                / max(len(paths) * EPL_ACTIVE_PLAY_SECONDS_2015_16, 1),
                9,
            ),
            "mean_team_control_survival_seconds": round(
                len(paths)
                * EPL_ACTIVE_PLAY_SECONDS_2015_16
                / max(possession_team_interruptions, 1),
                6,
            ),
            "interpretation": (
                "empirical constant-hazard calibration for the lifetime of team control; "
                "it is not an action-specific pass-failure probability and does not by "
                "itself authorize a production scoring change"
            ),
        },
        "distance_bands": {
            band: {
                "attempted": distance_bands[band],
                "attempt_share": round(distance_bands[band] / attempted, 6)
                if attempted else None,
            }
            for band in ("0-10m", "10-20m", "20-30m", "30m+")
        },
        "fine_distance_completion": {
            band: {
                "attempted": values["attempted"],
                "completed": values["completed"],
                "completion_rate": round(
                    values["completed"] / values["attempted"], 6
                ),
            }
            for band, values in sorted(
                fine_distance.items(),
                key=lambda item: int(item[0].split("-", 1)[0].removesuffix("m+")),
            )
        },
        "fine_distance_completion_by_height": {
            height: {
                band: {
                    "attempted": values["attempted"],
                    "completed": values["completed"],
                    "completion_rate": round(
                        values["completed"] / values["attempted"], 6
                    ),
                }
                for band, values in sorted(
                    bands.items(),
                    key=lambda item: int(
                        item[0].split("-", 1)[0].removesuffix("m+")
                    ),
                )
            }
            for height, bands in sorted(fine_distance_by_height.items())
        },
        "distance_band_direction": {
            band: {
                direction: {
                    "attempted": values[direction],
                    "attempt_share": round(
                        values[direction] / sum(values.values()), 6
                    ),
                }
                for direction in ("backward", "forward", "lateral")
            }
            for band, values in sorted(distance_direction.items())
        },
        "distance_band_zone": {
            band: {
                zone: {
                    "attempted": values[zone],
                    "attempt_share": round(values[zone] / sum(values.values()), 6),
                }
                for zone in ("defensive", "middle", "final")
            }
            for band, values in sorted(distance_zone.items())
        },
    }


def _frame_players(
    frame: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[list[float]], list[list[float]]]:
    actor = None
    teammates: list[list[float]] = []
    opponents: list[list[float]] = []
    for player in frame.get("freeze_frame", []):
        location = player.get("location")
        if not isinstance(location, list):
            continue
        if player.get("actor"):
            actor = player
        elif player.get("teammate"):
            teammates.append(location)
        else:
            opponents.append(location)
    return actor, teammates, opponents


def _visible_area_dimensions(frame: dict[str, Any]) -> tuple[float, float] | None:
    visible = frame.get("visible_area") or []
    if len(visible) < 6 or len(visible) % 2:
        return None
    points = [_point_m(visible[index:index + 2]) for index in range(0, len(visible), 2)]
    return (
        max(point[0] for point in points) - min(point[0] for point in points),
        max(point[1] for point in points) - min(point[1] for point in points),
    )


def audit_360_geometry(
    event_paths: Iterable[Path], frames_dir: Path
) -> dict[str, Any]:
    paths = list(event_paths)
    nearest_teammate: list[float] = []
    pass_distances: list[float] = []
    teammate_counts: dict[str, list[float]] = defaultdict(list)
    endpoint_proxy: list[float] = []
    endpoint_opponent_proxy: list[float] = []
    endpoint_opponent_by_pass_distance: dict[str, list[float]] = defaultdict(list)
    pressure_support: dict[str, list[float]] = defaultdict(list)
    pressure_pass_distance: dict[str, list[float]] = defaultdict(list)
    pressure_pass_distance_bands: dict[str, Counter[str]] = defaultdict(Counter)
    zone_pressure_support: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    matched_pass_frames = 0
    high_coverage: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    lane_risk_by_distance_height: dict[str, list[float]] = defaultdict(list)
    for event_path in paths:
        frame_path = frames_dir / event_path.name
        if not frame_path.is_file():
            raise FileNotFoundError(f"missing StatsBomb 360 input: {frame_path}")
        events = _read_json(event_path)
        frames = _read_json(frame_path)
        frame_by_event = {frame["event_uuid"]: frame for frame in frames}
        for event in events:
            if not _eligible_pass(event):
                continue
            frame = frame_by_event.get(event.get("id"))
            if frame is None:
                continue
            _, teammates, opponents = _frame_players(frame)
            if not teammates:
                continue
            origin = event["location"]
            end = event["pass"]["end_location"]
            teammate_distances = [_distance_m(origin, location) for location in teammates]
            nearest = min(teammate_distances)
            nearest_teammate.append(nearest)
            pass_distance = _distance_m(origin, end)
            pass_distances.append(pass_distance)
            endpoint_proxy.append(min(_distance_m(end, location) for location in teammates))
            for radius in (10, 15, 20):
                teammate_counts[f"within_{radius}m"].append(
                    float(sum(distance < radius for distance in teammate_distances))
                )
            if opponents:
                pressure = min(_distance_m(origin, location) for location in opponents)
                endpoint_opponent_distance = min(
                    _distance_m(end, location) for location in opponents
                )
                endpoint_opponent_proxy.append(endpoint_opponent_distance)
                endpoint_opponent_by_pass_distance[
                    _pass_distance_band(pass_distance)
                ].append(endpoint_opponent_distance)
                band = _pressure_band(pressure)
                pressure_support[band].append(nearest)
                pressure_pass_distance[band].append(pass_distance)
                pressure_pass_distance_bands[band][
                    _pass_distance_band(pass_distance)
                ] += 1
                zone_pressure_support[_zone(origin)][band].append(nearest)
                height = str((event["pass"].get("height") or {}).get("name") or "Unknown")
                lane_risk_by_distance_height[
                    f"{_pass_distance_band(pass_distance)}:{height}"
                ].append(_engine_lane_risk(origin, end, opponents))
            matched_pass_frames += 1
        for frame in frames:
            actor, _, _ = _frame_players(frame)
            teammates = [
                player["location"]
                for player in frame.get("freeze_frame", [])
                if player.get("teammate") is True
                and player.get("actor") is not True
                and player.get("keeper") is not True
                and isinstance(player.get("location"), list)
            ]
            dimensions = _visible_area_dimensions(frame)
            if (
                actor is None
                or actor.get("teammate") is not True
                or actor.get("keeper") is True
                or not isinstance(actor.get("location"), list)
                or len(teammates) < 7
                or dimensions is None
                or dimensions[0] < 70.0
                or dimensions[1] < 55.0
            ):
                continue
            actor_location = actor["location"]
            ordered = sorted(
                (_distance_m(actor_location, location), _point_m(location))
                for location in teammates
            )
            first_distance, first = ordered[0]
            second_distance, second = ordered[1]
            actor_m = _point_m(actor_location)
            first_vector = (first[0] - actor_m[0], first[1] - actor_m[1])
            second_vector = (second[0] - actor_m[0], second[1] - actor_m[1])
            denominator = first_distance * second_distance
            angle = 0.0 if denominator <= 1e-9 else degrees(acos(max(-1.0, min(
                1.0,
                (first_vector[0] * second_vector[0] + first_vector[1] * second_vector[1])
                / denominator,
            ))))
            zone = _zone(actor_location)
            for key in ("all", zone):
                high_coverage[key]["nearest_m"].append(first_distance)
                high_coverage[key]["second_nearest_m"].append(second_distance)
                high_coverage[key]["nearest_pair_angle_deg"].append(angle)
                high_coverage[key]["triangle_45_135_within15"].append(
                    float(second_distance <= 15.0 and 45.0 <= angle <= 135.0)
                )
    return {
        "source": {
            "provider": "StatsBomb open-data 360",
            "competition": "1. Bundesliga",
            "season": THREE_SIXTY_SEASON,
            "competition_id": THREE_SIXTY_COMPETITION_ID,
            "season_id": THREE_SIXTY_SEASON_ID,
            "selection": f"first {len(paths)} matches in the provider matches manifest",
            "matches_url": (
                f"{STATSBOMB_RAW}/matches/{THREE_SIXTY_COMPETITION_ID}/"
                f"{THREE_SIXTY_SEASON_ID}.json"
            ),
            "frame_url_template": f"{STATSBOMB_RAW}/three-sixty/{{match_id}}.json",
        },
        "scope": (
            "matched non-cross, non-throw-in Pass frames; teammate/opponent geometry is "
            "limited to the provider visible area at release"
        ),
        "limitations": [
            "this is Bundesliga rather than Premier League because open EPL data has no 360 frames",
            "freeze_frame is a visible-area sample, not all 22 players",
            "open 360 players have no identity, so intended-receiver endpoint offset is unavailable",
            "pass_end_to_nearest_visible_teammate_at_release_m is only a spatial proxy",
            "pass_end_to_nearest_visible_opponent_at_release_m is a release-frame endpoint proxy, not arrival pressure",
        ],
        "match_count": len(paths),
        "matched_pass_frames": matched_pass_frames,
        "nearest_visible_teammate_m": _distribution(nearest_teammate),
        "pass_distance_m": _distribution(pass_distances),
        "visible_teammate_counts": {
            key: {
                **_distribution(values),
                "zero_share": round(sum(value == 0 for value in values) / len(values), 6)
                if values else None,
            }
            for key, values in sorted(teammate_counts.items())
        },
        "pass_end_to_nearest_visible_teammate_at_release_m": {
            **_distribution(endpoint_proxy),
            "share_4_to_9m": round(
                sum(4.0 <= value <= 9.0 for value in endpoint_proxy) / len(endpoint_proxy), 6
            ) if endpoint_proxy else None,
            "interpretation": "proxy only; not an intended-receiver measurement",
        },
        "pass_end_to_nearest_visible_opponent_at_release_m": {
            **_distribution(endpoint_opponent_proxy),
            "under_2m_share": round(
                sum(value < 2.0 for value in endpoint_opponent_proxy)
                / len(endpoint_opponent_proxy),
                6,
            ) if endpoint_opponent_proxy else None,
            "under_4m_share": round(
                sum(value < 4.0 for value in endpoint_opponent_proxy)
                / len(endpoint_opponent_proxy),
                6,
            ) if endpoint_opponent_proxy else None,
            "under_10m_share": round(
                sum(value < 10.0 for value in endpoint_opponent_proxy)
                / len(endpoint_opponent_proxy),
                6,
            ) if endpoint_opponent_proxy else None,
            "interpretation": (
                "release-frame distance from the pass endpoint to the nearest visible "
                "opponent; visible-area proxy only, not arrival pressure"
            ),
        },
        "pass_end_to_nearest_visible_opponent_by_pass_distance": {
            band: {
                **_distribution(values),
                "under_4m_share": round(
                    sum(value < 4.0 for value in values) / len(values), 6
                ),
                "under_10m_share": round(
                    sum(value < 10.0 for value in values) / len(values), 6
                ),
            }
            for band in ("0-10m", "10-20m", "20-30m", "30m+")
            if (values := endpoint_opponent_by_pass_distance.get(band, []))
        },
        "engine_lane_risk_on_selected_passes": {
            "scope": (
                "the current engine static release-frame lane-risk formula with "
                f"interception_reach={ENGINE_INTERCEPTION_REACH_M}m applied to visible "
                "opponents in selected real 360 pass frames; this is a model projection, "
                "not provider intent or arrival pressure"
            ),
            "by_distance_and_height": {
                key: {
                    **_distribution(values),
                    "zero_risk_share": round(
                        sum(value <= 1e-12 for value in values) / len(values), 6
                    ),
                    "under_0_05_share": round(
                        sum(value < 0.05 for value in values) / len(values), 6
                    ),
                }
                for key, values in sorted(lane_risk_by_distance_height.items())
                if values
            },
        },
        "nearest_visible_teammate_by_nearest_opponent": {
            band: {
                **_distribution(values),
                "under_10m_share": round(sum(value < 10.0 for value in values) / len(values), 6)
                if values else None,
            }
            for band in ("0-2m", "2-4m", "4-6m", "6-10m", "10m+")
            if (values := pressure_support.get(band, []))
        },
        "pass_distance_by_nearest_opponent": {
            band: {
                **_distribution(values),
                "distance_bands": {
                    distance_band: {
                        "attempted": pressure_pass_distance_bands[band][distance_band],
                        "attempt_share": round(
                            pressure_pass_distance_bands[band][distance_band]
                            / len(values),
                            6,
                        ),
                    }
                    for distance_band in ("0-10m", "10-20m", "20-30m", "30m+")
                },
            }
            for band in ("0-2m", "2-4m", "4-6m", "6-10m", "10m+")
            if (values := pressure_pass_distance.get(band, []))
        },
        "nearest_visible_teammate_by_zone_and_nearest_opponent": {
            zone: {
                band: {
                    **_distribution(values),
                    "under_10m_share": round(
                        sum(value < 10.0 for value in values) / len(values), 6
                    ),
                }
                for band in ("0-2m", "2-4m", "4-6m", "6-10m", "10m+")
                if (values := zone_pressure_support[zone].get(band, []))
            }
            for zone in ("defensive", "middle", "final")
        },
        "high_visible_coverage_support_density": {
            zone: {field: _distribution(values) for field, values in sorted(fields.items())}
            for zone, fields in sorted(high_coverage.items())
        },
    }


def _engine_evidence(audit_path: Path | None, trace_path: Path | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    if audit_path is not None:
        audit = _read_json(audit_path)
        evidence["aggregate_real_squads"] = {
            "source_path": str(audit_path),
            "match_count": audit.get("match_count"),
            "current": audit.get("current"),
            "pass_distance_bands": (audit.get("mechanism_diagnostics") or {}).get(
                "pass_distance_bands"
            ),
            "completion": audit.get("completion"),
        }
    if trace_path is not None:
        trace = _read_json(trace_path)
        match = (trace.get("matches") or [{}])[0]
        pace = match.get("action_pace") or {}
        selection = pace.get("pass_candidate_selection") or {}
        support = pace.get("off_ball_support_selection") or {}
        evidence["full_trace"] = {
            "source_path": str(trace_path),
            "match_count": trace.get("match_count"),
            "seed": match.get("seed"),
            "chosen_pass_support_geometry": (
                selection.get("support_geometry_by_chosen_action") or {}
            ).get("pass"),
            "support_by_nearest_opponent": selection.get(
                "spacing_by_nearest_opponent_distance"
            ),
            "support_density_by_zone": support.get("support_density_by_zone"),
        }
    return evidence


def _comparison(
    epl: dict[str, Any] | None,
    geometry: dict[str, Any] | None,
    engine: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "insufficient_evidence",
        "production_change_authorized": False,
        "caveats": [
            "EPL event distance and Bundesliga 360 geometry are independent evidence scopes",
            "a single engine full trace is diagnostic evidence, not a 30-match geometry estimate",
        ],
    }
    aggregate = engine.get("aggregate_real_squads") or {}
    if epl and aggregate.get("pass_distance_bands"):
        engine_bands = aggregate["pass_distance_bands"]
        result["pass_distance_attempt_share"] = {
            band: {
                "epl_2015_16_event": epl["distance_bands"][band]["attempt_share"],
                "engine_real_squads": round(
                    float(engine_bands[band]["attempt_share"]) / 100.0, 6
                ),
            }
            for band in ("0-10m", "10-20m", "20-30m", "30m+")
        }
    trace = engine.get("full_trace") or {}
    real_pressure = (geometry or {}).get("nearest_visible_teammate_by_nearest_opponent") or {}
    engine_pressure = trace.get("support_by_nearest_opponent") or {}
    high_real = real_pressure.get("0-2m")
    high_engine = engine_pressure.get("0_2m")
    if high_real and high_engine:
        result["high_pressure_support"] = {
            "bundesliga_360": {
                "count": high_real.get("count"),
                "median_nearest_visible_teammate_m": high_real.get("median"),
                "under_10m_share": high_real.get("under_10m_share"),
            },
            "engine_full_trace": {
                "count": high_engine.get("count"),
                "median_nearest_teammate_m": high_engine.get("median"),
                "under_10m_share": high_engine.get("under_10m_share"),
            },
        }
        result["status"] = "support_gap_supported_not_causal"
        result["reason"] = (
            "real 360 frames support a pressure-responsive near-outlet gap, but competition, "
            "visibility, and engine sample-size differences do not yet identify a safe mechanism change"
        )
    return result


def _fetch(url: str, path: Path) -> None:
    if path.is_file() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "PSL-engine-v2-realism-audit"})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    path.write_bytes(payload)


def fetch_missing_inputs(data_root: Path, max_360_matches: int) -> None:
    epl_root = data_root / "epl_2015_16"
    geometry_root = data_root / "bundesliga_2023_24_360"
    epl_matches = epl_root / "matches.json"
    geometry_matches = geometry_root / "matches.json"
    _fetch(
        f"{STATSBOMB_RAW}/matches/{EPL_COMPETITION_ID}/{EPL_SEASON_ID}.json",
        epl_matches,
    )
    _fetch(
        f"{STATSBOMB_RAW}/matches/{THREE_SIXTY_COMPETITION_ID}/{THREE_SIXTY_SEASON_ID}.json",
        geometry_matches,
    )
    downloads: list[tuple[str, Path]] = []
    for match in _read_json(epl_matches):
        match_id = match["match_id"]
        downloads.append((
            f"{STATSBOMB_RAW}/events/{match_id}.json",
            epl_root / "events" / f"{match_id}.json",
        ))
    for match in _read_json(geometry_matches)[:max_360_matches]:
        match_id = match["match_id"]
        downloads.extend([
            (
                f"{STATSBOMB_RAW}/events/{match_id}.json",
                geometry_root / "events" / f"{match_id}.json",
            ),
            (
                f"{STATSBOMB_RAW}/three-sixty/{match_id}.json",
                geometry_root / "frames" / f"{match_id}.json",
            ),
        ])
    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(lambda item: _fetch(*item), downloads))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--max-360-matches", type=int, default=DEFAULT_360_MATCHES)
    parser.add_argument("--engine-audit", type=Path)
    parser.add_argument("--engine-trace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.fetch_missing:
        fetch_missing_inputs(args.data_root, args.max_360_matches)
    epl_root = args.data_root / "epl_2015_16"
    geometry_root = args.data_root / "bundesliga_2023_24_360"
    epl = audit_epl_events(_ordered_event_paths(
        epl_root / "events", epl_root / "matches.json"
    ))
    geometry = audit_360_geometry(
        _ordered_event_paths(
            geometry_root / "events",
            geometry_root / "matches.json",
            args.max_360_matches,
        ),
        geometry_root / "frames",
    )
    engine = _engine_evidence(args.engine_audit, args.engine_trace)
    report = {
        "schema_version": 1,
        "epl_event_pass_structure": epl,
        "three_sixty_support_geometry": geometry,
        "engine_evidence": engine,
        "comparison": _comparison(epl, geometry, engine),
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
