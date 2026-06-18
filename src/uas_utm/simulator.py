from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    AirspaceZone,
    MissionSpec,
    TelemetryFrame,
    UasUtmResult,
    UasUtmScenario,
    UavSpec,
    UtmDecision,
    move_toward,
    round_position,
)
from .utm_service import UtmService


def load_scenario(path: Path) -> UasUtmScenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return UasUtmScenario(
        name=str(raw["name"]),
        duration_s=int(raw["duration_s"]),
        step_s=int(raw.get("step_s", 1)),
        conflict_distance_m=float(raw.get("conflict_distance_m", 25)),
        assets=[_parse_asset(item) for item in raw["assets"]],
        zones=[_parse_zone(item) for item in raw.get("zones", [])],
        missions=[_parse_mission(item) for item in raw.get("missions", [])],
    )


def run_environment(scenario: UasUtmScenario) -> UasUtmResult:
    decisions = UtmService(scenario).evaluate_missions()
    approved_ids = {decision.mission_id for decision in decisions if decision.approved}
    missions = {mission.id: mission for mission in scenario.missions if mission.id in approved_ids}
    assets = {asset.id: asset for asset in scenario.assets}
    positions = {asset.id: asset.start for asset in scenario.assets}
    waypoint_indexes = {mission.id: 0 for mission in missions.values()}
    battery_by_asset = {asset.id: asset.battery_capacity_wh for asset in scenario.assets}

    telemetry: list[TelemetryFrame] = []
    for time_s in range(0, scenario.duration_s + 1, scenario.step_s):
        for asset in scenario.assets:
            active_mission = _active_mission_for_asset(missions.values(), asset.id, time_s)
            if active_mission is None:
                telemetry.append(
                    TelemetryFrame(
                        time_s=time_s,
                        asset_id=asset.id,
                        mission_id=None,
                        position=round_position(positions[asset.id]),
                        next_waypoint=None,
                        status="idle",
                        battery_wh=round(battery_by_asset[asset.id], 3),
                    )
                )
                continue

            waypoint_index = waypoint_indexes[active_mission.id]
            target = active_mission.route[min(waypoint_index, len(active_mission.route) - 1)]
            new_position = move_toward(
                positions[asset.id],
                target,
                active_mission.nominal_speed_mps * scenario.step_s,
            )
            positions[asset.id] = new_position
            battery_by_asset[asset.id] = max(
                0.0,
                battery_by_asset[asset.id] - _battery_draw_wh(asset, scenario.step_s),
            )

            if new_position == target and waypoint_index < len(active_mission.route) - 1:
                waypoint_indexes[active_mission.id] += 1

            status = "completed" if waypoint_indexes[active_mission.id] >= len(active_mission.route) - 1 and new_position == target else "active"
            telemetry.append(
                TelemetryFrame(
                    time_s=time_s,
                    asset_id=asset.id,
                    mission_id=active_mission.id,
                    position=round_position(new_position),
                    next_waypoint=None if status == "completed" else round_position(target),
                    status=status,
                    battery_wh=round(battery_by_asset[asset.id], 3),
                )
            )

    return UasUtmResult(scenario=scenario, decisions=decisions, telemetry=telemetry)


def summarize_result(result: UasUtmResult) -> dict[str, Any]:
    approved = [decision for decision in result.decisions if decision.approved]
    rejected = [decision for decision in result.decisions if not decision.approved]
    completed_missions = sorted(
        {
            frame.mission_id
            for frame in result.telemetry
            if frame.mission_id is not None and frame.status == "completed"
        }
    )
    return {
        "scenario": result.scenario.name,
        "asset_count": len(result.scenario.assets),
        "mission_count": len(result.scenario.missions),
        "approved_missions": [decision.mission_id for decision in approved],
        "rejected_missions": [
            {
                "mission_id": decision.mission_id,
                "asset_id": decision.asset_id,
                "reasons": decision.reasons,
            }
            for decision in rejected
        ],
        "completed_missions": completed_missions,
        "telemetry_frames": len(result.telemetry),
        "final_positions": _final_positions(result),
    }


def _active_mission_for_asset(
    missions: Any,
    asset_id: str,
    time_s: int,
) -> MissionSpec | None:
    candidates = [
        mission
        for mission in missions
        if mission.asset_id == asset_id and mission.requested_start_s <= time_s <= mission.requested_end_s
    ]
    return min(candidates, key=lambda mission: mission.requested_start_s) if candidates else None


def _battery_draw_wh(asset: UavSpec, step_s: int) -> float:
    return max(0.1, asset.cruise_speed_mps * 0.015 * step_s)


def _final_positions(result: UasUtmResult) -> dict[str, Any]:
    final_frames: dict[str, TelemetryFrame] = {}
    for frame in result.telemetry:
        final_frames[frame.asset_id] = frame
    return {asset_id: frame.position for asset_id, frame in sorted(final_frames.items())}


def _parse_asset(raw: dict[str, Any]) -> UavSpec:
    return UavSpec(
        id=str(raw["id"]),
        callsign=str(raw["callsign"]),
        start=_parse_position(raw["start"]),
        cruise_speed_mps=float(raw["cruise_speed_mps"]),
        min_altitude_m=float(raw["min_altitude_m"]),
        max_altitude_m=float(raw["max_altitude_m"]),
        battery_capacity_wh=float(raw["battery_capacity_wh"]),
    )


def _parse_zone(raw: dict[str, Any]) -> AirspaceZone:
    return AirspaceZone(
        id=str(raw["id"]),
        kind=raw["kind"],
        x_min=float(raw["x_min"]),
        x_max=float(raw["x_max"]),
        y_min=float(raw["y_min"]),
        y_max=float(raw["y_max"]),
        min_altitude_m=float(raw["min_altitude_m"]),
        max_altitude_m=float(raw["max_altitude_m"]),
        label=str(raw.get("label", "")),
    )


def _parse_mission(raw: dict[str, Any]) -> MissionSpec:
    return MissionSpec(
        id=str(raw["id"]),
        asset_id=str(raw["asset_id"]),
        route=[_parse_position(item) for item in raw["route"]],
        requested_start_s=int(raw["requested_start_s"]),
        requested_end_s=int(raw["requested_end_s"]),
        nominal_speed_mps=float(raw["nominal_speed_mps"]),
        purpose=str(raw.get("purpose", "normal_ops")),
    )


def _parse_position(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError(f"position must be [x, y, z], got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))
