from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mavlink_adapter import build_mavlink_messages, mavlink_message_counts, mission_to_mavlink_items
from .models import (
    AirspaceZone,
    C2Node,
    MissionSpec,
    Position,
    TelemetryFrame,
    UasUtmResult,
    UasUtmScenario,
    UavSpec,
    UtmDecision,
    distance,
    heading_from_velocity,
    move_toward,
    round_position,
    velocity_between,
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
        c2_nodes=[_parse_c2_node(item) for item in raw.get("c2_nodes", [])],
        origin_lat_e7=int(raw.get("origin_lat_e7", 373500000)),
        origin_lon_e7=int(raw.get("origin_lon_e7", 1270000000)),
    )


def run_environment(scenario: UasUtmScenario) -> UasUtmResult:
    decisions = UtmService(scenario).evaluate_missions()
    approved_ids = {decision.mission_id for decision in decisions if decision.approved}
    missions = {mission.id: mission for mission in scenario.missions if mission.id in approved_ids}
    mission_by_asset = _missions_by_asset(missions.values())
    positions = {asset.id: asset.start for asset in scenario.assets}
    waypoint_indexes = {mission.id: 0 for mission in missions.values()}
    battery_by_asset = {asset.id: asset.battery_capacity_wh for asset in scenario.assets}
    sequence_by_asset = {asset.id: 0 for asset in scenario.assets}

    telemetry: list[TelemetryFrame] = []
    for time_s in range(0, scenario.duration_s + 1, scenario.step_s):
        for asset in scenario.assets:
            active_mission = _active_mission_for_asset(mission_by_asset.get(asset.id, []), time_s)
            previous_position = positions[asset.id]
            if active_mission is None:
                frame = _idle_frame(
                    scenario=scenario,
                    asset=asset,
                    time_s=time_s,
                    position=previous_position,
                    battery_wh=battery_by_asset[asset.id],
                    sequence_start=sequence_by_asset[asset.id],
                )
                sequence_by_asset[asset.id] += len(frame.mavlink_messages)
                telemetry.append(frame)
                continue

            waypoint_index = waypoint_indexes[active_mission.id]
            target = active_mission.route[min(waypoint_index, len(active_mission.route) - 1)]
            new_position = move_toward(
                previous_position,
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

            completed = waypoint_indexes[active_mission.id] >= len(active_mission.route) - 1 and new_position == target
            status = "completed" if completed else "active"
            velocity = velocity_between(previous_position, new_position, scenario.step_s)
            c2_node = _select_c2_node(scenario.c2_nodes, asset, new_position, active_mission.required_link)
            frame = TelemetryFrame(
                time_s=time_s,
                asset_id=asset.id,
                mission_id=active_mission.id,
                position=round_position(new_position),
                next_waypoint=None if completed else round_position(target),
                status=status,
                battery_wh=round(battery_by_asset[asset.id], 3),
                velocity_mps=round_position(velocity),
                heading_deg=heading_from_velocity(velocity),
                c2_node_id=c2_node.id if c2_node else None,
                link_profile=active_mission.required_link if c2_node else None,
            )
            messages = build_mavlink_messages(
                scenario=scenario,
                asset=asset,
                frame=frame,
                mission=active_mission,
                sequence_start=sequence_by_asset[asset.id],
            )
            sequence_by_asset[asset.id] += len(messages)
            telemetry.append(_replace_frame_messages(frame, messages))

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
        "c2_node_count": len(result.scenario.c2_nodes),
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
        "mavlink_message_counts": mavlink_message_counts(result.telemetry),
        "mission_plan_message_counts": _mission_plan_message_counts(result),
        "link_coverage_rate": _link_coverage_rate(result),
        "c2_utilization": _c2_utilization(result),
        "platform_classes": _platform_classes(result.scenario.assets),
        "final_positions": _final_positions(result),
    }


def _idle_frame(
    *,
    scenario: UasUtmScenario,
    asset: UavSpec,
    time_s: int,
    position: Position,
    battery_wh: float,
    sequence_start: int,
) -> TelemetryFrame:
    c2_node = _select_c2_node(scenario.c2_nodes, asset, position, asset.datalink_profiles[0])
    frame = TelemetryFrame(
        time_s=time_s,
        asset_id=asset.id,
        mission_id=None,
        position=round_position(position),
        next_waypoint=None,
        status="idle",
        battery_wh=round(battery_wh, 3),
        c2_node_id=c2_node.id if c2_node else None,
        link_profile=asset.datalink_profiles[0] if c2_node else None,
    )
    return _replace_frame_messages(
        frame,
        build_mavlink_messages(
            scenario=scenario,
            asset=asset,
            frame=frame,
            mission=None,
            sequence_start=sequence_start,
        ),
    )


def _replace_frame_messages(frame: TelemetryFrame, messages: list[Any]) -> TelemetryFrame:
    return TelemetryFrame(
        time_s=frame.time_s,
        asset_id=frame.asset_id,
        mission_id=frame.mission_id,
        position=frame.position,
        next_waypoint=frame.next_waypoint,
        status=frame.status,
        battery_wh=frame.battery_wh,
        velocity_mps=frame.velocity_mps,
        heading_deg=frame.heading_deg,
        c2_node_id=frame.c2_node_id,
        link_profile=frame.link_profile,
        mavlink_messages=messages,
    )


def _missions_by_asset(missions: Any) -> dict[str, list[MissionSpec]]:
    grouped: dict[str, list[MissionSpec]] = {}
    for mission in missions:
        grouped.setdefault(mission.asset_id, []).append(mission)
    for asset_missions in grouped.values():
        asset_missions.sort(key=lambda mission: mission.requested_start_s)
    return grouped


def _active_mission_for_asset(missions: list[MissionSpec], time_s: int) -> MissionSpec | None:
    candidates = [
        mission for mission in missions if mission.requested_start_s <= time_s <= mission.requested_end_s
    ]
    return min(candidates, key=lambda mission: mission.requested_start_s) if candidates else None


def _select_c2_node(
    nodes: list[C2Node],
    asset: UavSpec,
    position: Position,
    required_link: str,
) -> C2Node | None:
    candidates = [
        node
        for node in nodes
        if required_link in node.supported_links
        and required_link in asset.datalink_profiles
        and distance(position, node.location) <= node.coverage_radius_m
    ]
    return min(candidates, key=lambda node: (node.latency_ms, distance(position, node.location))) if candidates else None


def _battery_draw_wh(asset: UavSpec, step_s: int) -> float:
    platform_factor = 0.035 if asset.platform_class in {"male_isr", "hale_isr"} else 0.015
    return max(0.1, asset.cruise_speed_mps * platform_factor * step_s)


def _final_positions(result: UasUtmResult) -> dict[str, Any]:
    final_frames: dict[str, TelemetryFrame] = {}
    for frame in result.telemetry:
        final_frames[frame.asset_id] = frame
    return {asset_id: frame.position for asset_id, frame in sorted(final_frames.items())}


def _link_coverage_rate(result: UasUtmResult) -> float:
    if not result.telemetry:
        return 1.0
    covered = sum(1 for frame in result.telemetry if frame.c2_node_id is not None)
    return round(covered / len(result.telemetry), 4)


def _c2_utilization(result: UasUtmResult) -> dict[str, int]:
    utilization: dict[str, int] = {}
    for frame in result.telemetry:
        if frame.c2_node_id is None:
            continue
        utilization[frame.c2_node_id] = utilization.get(frame.c2_node_id, 0) + 1
    return dict(sorted(utilization.items()))


def _platform_classes(assets: list[UavSpec]) -> dict[str, int]:
    classes: dict[str, int] = {}
    for asset in assets:
        classes[asset.platform_class] = classes.get(asset.platform_class, 0) + 1
    return dict(sorted(classes.items()))


def _mission_plan_message_counts(result: UasUtmResult) -> dict[str, int]:
    assets = {asset.id: asset for asset in result.scenario.assets}
    counts: dict[str, int] = {}
    for decision in result.decisions:
        if not decision.approved:
            continue
        mission = next(item for item in result.scenario.missions if item.id == decision.mission_id)
        counts[mission.id] = len(
            mission_to_mavlink_items(
                scenario=result.scenario,
                asset=assets[mission.asset_id],
                mission=mission,
            )
        )
    return counts


def _parse_asset(raw: dict[str, Any]) -> UavSpec:
    return UavSpec(
        id=str(raw["id"]),
        callsign=str(raw["callsign"]),
        start=_parse_position(raw["start"]),
        cruise_speed_mps=float(raw["cruise_speed_mps"]),
        min_altitude_m=float(raw["min_altitude_m"]),
        max_altitude_m=float(raw["max_altitude_m"]),
        battery_capacity_wh=float(raw["battery_capacity_wh"]),
        service_branch=str(raw.get("service_branch", "generic")),
        platform_class=str(raw.get("platform_class", "small_uas")),
        role=str(raw.get("role", "normal_ops")),
        datalink_profiles=tuple(raw.get("datalink_profiles", ["mavlink_udp"])),
        sensor_payloads=tuple(raw.get("sensor_payloads", [])),
        endurance_s=int(raw["endurance_s"]) if raw.get("endurance_s") is not None else None,
        system_id=int(raw.get("system_id", 1)),
        component_id=int(raw.get("component_id", 1)),
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
        controlling_authority=str(raw.get("controlling_authority", "UTM")),
    )


def _parse_c2_node(raw: dict[str, Any]) -> C2Node:
    return C2Node(
        id=str(raw["id"]),
        kind=str(raw["kind"]),
        location=_parse_position(raw["location"]),
        coverage_radius_m=float(raw["coverage_radius_m"]),
        supported_links=tuple(raw.get("supported_links", ["mavlink_udp"])),
        latency_ms=int(raw.get("latency_ms", 50)),
        authority=str(raw.get("authority", "UTM")),
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
        mission_type=str(raw.get("mission_type", "transit")),
        priority=int(raw.get("priority", 3)),
        control_mode=str(raw.get("control_mode", "auto")),
        required_payloads=tuple(raw.get("required_payloads", [])),
        required_link=str(raw.get("required_link", "mavlink_udp")),
        corridor_width_m=float(raw.get("corridor_width_m", 60)),
    )


def _parse_position(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError(f"position must be [x, y, z], got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))
