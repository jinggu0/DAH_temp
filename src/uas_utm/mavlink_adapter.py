from __future__ import annotations

from collections import Counter

from .models import MavlinkMessage, MissionSpec, Position, TelemetryFrame, UasUtmScenario, UavSpec


def build_mavlink_messages(
    *,
    scenario: UasUtmScenario,
    asset: UavSpec,
    frame: TelemetryFrame,
    mission: MissionSpec | None,
    sequence_start: int,
) -> list[MavlinkMessage]:
    lat, lon, alt_mm = local_position_to_wgs84_int(
        frame.position,
        origin_lat_e7=scenario.origin_lat_e7,
        origin_lon_e7=scenario.origin_lon_e7,
    )
    next_lat, next_lon, next_alt_mm = _next_waypoint_int(
        frame.next_waypoint,
        scenario.origin_lat_e7,
        scenario.origin_lon_e7,
    )
    vx = int(frame.velocity_mps[0] * 100)
    vy = int(frame.velocity_mps[1] * 100)
    vz = int(-frame.velocity_mps[2] * 100)
    battery_remaining = _battery_remaining_percent(asset, frame.battery_wh)
    messages = [
        MavlinkMessage(
            message_name="HEARTBEAT",
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence=sequence_start,
            fields={
                "type": _mav_type(asset),
                "autopilot": "MAV_AUTOPILOT_GENERIC",
                "base_mode": frame.status,
                "system_status": "MAV_STATE_ACTIVE" if frame.status == "active" else "MAV_STATE_STANDBY",
            },
        ),
        MavlinkMessage(
            message_name="GLOBAL_POSITION_INT",
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence=sequence_start + 1,
            fields={
                "time_boot_ms": frame.time_s * 1000,
                "lat": lat,
                "lon": lon,
                "alt": alt_mm,
                "relative_alt": alt_mm,
                "vx": vx,
                "vy": vy,
                "vz": vz,
                "hdg": int(frame.heading_deg * 100),
            },
        ),
        MavlinkMessage(
            message_name="SYS_STATUS",
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence=sequence_start + 2,
            fields={
                "battery_remaining": battery_remaining,
                "drop_rate_comm": 0 if frame.c2_node_id else 1000,
                "errors_comm": 0,
            },
        ),
        MavlinkMessage(
            message_name="UTM_GLOBAL_POSITION",
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence=sequence_start + 3,
            fields={
                "time": frame.time_s * 1_000_000,
                "uas_id": asset.id,
                "lat": lat,
                "lon": lon,
                "alt": alt_mm,
                "relative_alt": alt_mm,
                "vx": vx,
                "vy": vy,
                "vz": vz,
                "h_acc": 500,
                "v_acc": 800,
                "vel_acc": 50,
                "next_lat": next_lat,
                "next_lon": next_lon,
                "next_alt": next_alt_mm,
                "update_rate_hz": 1,
                "flight_state": frame.status,
            },
        ),
    ]
    if mission is not None:
        messages.append(
            MavlinkMessage(
                message_name="MISSION_CURRENT",
                system_id=asset.system_id,
                component_id=asset.component_id,
                sequence=sequence_start + 4,
                fields={"mission_id": mission.id, "mission_type": mission.mission_type},
            )
        )
    return messages


def mission_to_mavlink_items(
    *,
    scenario: UasUtmScenario,
    asset: UavSpec,
    mission: MissionSpec,
    sequence_start: int = 0,
) -> list[MavlinkMessage]:
    messages: list[MavlinkMessage] = []
    for index, waypoint in enumerate(mission.route):
        lat, lon, alt_mm = local_position_to_wgs84_int(
            waypoint,
            origin_lat_e7=scenario.origin_lat_e7,
            origin_lon_e7=scenario.origin_lon_e7,
        )
        messages.append(
            MavlinkMessage(
                message_name="MISSION_ITEM_INT",
                system_id=asset.system_id,
                component_id=asset.component_id,
                sequence=sequence_start + index,
                fields={
                    "seq": index,
                    "frame": "MAV_FRAME_GLOBAL_RELATIVE_ALT_INT",
                    "command": "MAV_CMD_NAV_WAYPOINT",
                    "current": 1 if index == 0 else 0,
                    "autocontinue": 1,
                    "x": lat,
                    "y": lon,
                    "z": int(alt_mm / 1000),
                    "mission_type": mission.mission_type,
                },
            )
        )
    return messages


def mavlink_message_counts(frames: list[TelemetryFrame]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for frame in frames:
        counts.update(message.message_name for message in frame.mavlink_messages)
    return dict(sorted(counts.items()))


def local_position_to_wgs84_int(
    position: Position,
    *,
    origin_lat_e7: int,
    origin_lon_e7: int,
) -> tuple[int, int, int]:
    lat_e7 = origin_lat_e7 + int(position[1] / 111_320 * 10_000_000)
    lon_e7 = origin_lon_e7 + int(position[0] / 88_800 * 10_000_000)
    alt_mm = int(position[2] * 1000)
    return lat_e7, lon_e7, alt_mm


def _next_waypoint_int(
    waypoint: Position | None,
    origin_lat_e7: int,
    origin_lon_e7: int,
) -> tuple[int | None, int | None, int | None]:
    if waypoint is None:
        return None, None, None
    return local_position_to_wgs84_int(waypoint, origin_lat_e7=origin_lat_e7, origin_lon_e7=origin_lon_e7)


def _battery_remaining_percent(asset: UavSpec, battery_wh: float) -> int:
    if asset.battery_capacity_wh <= 0:
        return -1
    return max(0, min(100, int(battery_wh / asset.battery_capacity_wh * 100)))


def _mav_type(asset: UavSpec) -> str:
    if "ugv" in asset.platform_class.lower():
        return "MAV_TYPE_GROUND_ROVER"
    if "male" in asset.platform_class.lower() or "hale" in asset.platform_class.lower():
        return "MAV_TYPE_FIXED_WING"
    return "MAV_TYPE_QUADROTOR"
