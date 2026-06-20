from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any


MAVLINK_V1_STX = 0xFE
MAVLINK_V2_STX = 0xFD

MESSAGE_NAMES = {
    0: "HEARTBEAT",
    1: "SYS_STATUS",
    33: "GLOBAL_POSITION_INT",
    42: "MISSION_CURRENT",
    340: "UTM_GLOBAL_POSITION",
}


@dataclass(frozen=True)
class ParsedMavlinkFrame:
    version: int
    sequence: int
    system_id: int
    component_id: int
    message_id: int
    message_name: str
    fields: dict[str, Any]


def parse_datagram(datagram: bytes) -> list[ParsedMavlinkFrame | dict[str, Any]]:
    stripped = datagram.strip()
    if stripped.startswith(b"{"):
        return [_parse_json_datagram(stripped)]
    frames: list[ParsedMavlinkFrame | dict[str, Any]] = []
    index = 0
    while index < len(datagram):
        marker = datagram[index]
        if marker == MAVLINK_V2_STX:
            frame, next_index = _parse_v2(datagram, index)
            frames.append(frame)
            index = next_index
        elif marker == MAVLINK_V1_STX:
            frame, next_index = _parse_v1(datagram, index)
            frames.append(frame)
            index = next_index
        else:
            index += 1
    return frames


def _parse_json_datagram(data: bytes) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON telemetry datagram must be an object")
    return value


def _parse_v1(data: bytes, index: int) -> tuple[ParsedMavlinkFrame, int]:
    if index + 8 > len(data):
        raise ValueError("truncated MAVLink v1 header")
    payload_len = data[index + 1]
    frame_len = 6 + payload_len + 2
    if index + frame_len > len(data):
        raise ValueError("truncated MAVLink v1 frame")
    sequence = data[index + 2]
    system_id = data[index + 3]
    component_id = data[index + 4]
    message_id = data[index + 5]
    payload = data[index + 6 : index + 6 + payload_len]
    return (
        ParsedMavlinkFrame(
            version=1,
            sequence=sequence,
            system_id=system_id,
            component_id=component_id,
            message_id=message_id,
            message_name=MESSAGE_NAMES.get(message_id, f"MSG_{message_id}"),
            fields=_parse_payload(message_id, payload),
        ),
        index + frame_len,
    )


def _parse_v2(data: bytes, index: int) -> tuple[ParsedMavlinkFrame, int]:
    if index + 12 > len(data):
        raise ValueError("truncated MAVLink v2 header")
    payload_len = data[index + 1]
    incompat_flags = data[index + 2]
    sequence = data[index + 4]
    system_id = data[index + 5]
    component_id = data[index + 6]
    message_id = data[index + 7] | (data[index + 8] << 8) | (data[index + 9] << 16)
    signature_len = 13 if incompat_flags & 0x01 else 0
    frame_len = 10 + payload_len + 2 + signature_len
    if index + frame_len > len(data):
        raise ValueError("truncated MAVLink v2 frame")
    payload = data[index + 10 : index + 10 + payload_len]
    return (
        ParsedMavlinkFrame(
            version=2,
            sequence=sequence,
            system_id=system_id,
            component_id=component_id,
            message_id=message_id,
            message_name=MESSAGE_NAMES.get(message_id, f"MSG_{message_id}"),
            fields=_parse_payload(message_id, payload),
        ),
        index + frame_len,
    )


def _parse_payload(message_id: int, payload: bytes) -> dict[str, Any]:
    if message_id == 0:
        return _parse_heartbeat(payload)
    if message_id == 1:
        return _parse_sys_status(payload)
    if message_id == 33:
        return _parse_global_position_int(payload)
    if message_id == 42:
        return _parse_mission_current(payload)
    if message_id == 340:
        return _parse_utm_global_position(payload)
    return {"raw_payload_len": len(payload)}


def _parse_heartbeat(payload: bytes) -> dict[str, Any]:
    if len(payload) < 9:
        raise ValueError("HEARTBEAT payload too short")
    custom_mode, mav_type, autopilot, base_mode, system_status, mavlink_version = struct.unpack_from("<IBBBBB", payload)
    return {
        "custom_mode": custom_mode,
        "type": mav_type,
        "autopilot": autopilot,
        "base_mode": base_mode,
        "system_status": system_status,
        "mavlink_version": mavlink_version,
    }


def _parse_sys_status(payload: bytes) -> dict[str, Any]:
    if len(payload) < 31:
        raise ValueError("SYS_STATUS payload too short")
    battery_remaining = struct.unpack_from("<b", payload, 30)[0]
    drop_rate_comm = struct.unpack_from("<H", payload, 18)[0]
    errors_comm = struct.unpack_from("<H", payload, 20)[0]
    return {
        "battery_remaining": battery_remaining,
        "drop_rate_comm": drop_rate_comm,
        "errors_comm": errors_comm,
    }


def _parse_global_position_int(payload: bytes) -> dict[str, Any]:
    if len(payload) < 28:
        raise ValueError("GLOBAL_POSITION_INT payload too short")
    time_boot_ms, lat, lon, alt, relative_alt, vx, vy, vz, hdg = struct.unpack_from("<IiiiihhhH", payload)
    return {
        "time_boot_ms": time_boot_ms,
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "relative_alt": relative_alt,
        "vx": vx,
        "vy": vy,
        "vz": vz,
        "hdg": hdg,
    }


def _parse_mission_current(payload: bytes) -> dict[str, Any]:
    if len(payload) < 2:
        raise ValueError("MISSION_CURRENT payload too short")
    seq = struct.unpack_from("<H", payload)[0]
    return {"seq": seq}


def _parse_utm_global_position(payload: bytes) -> dict[str, Any]:
    if len(payload) < 44:
        raise ValueError("UTM_GLOBAL_POSITION payload too short")
    time_usec, lat, lon, alt, relative_alt, vx, vy, vz = struct.unpack_from("<Qiiiihhh", payload)
    return {
        "time": time_usec,
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "relative_alt": relative_alt,
        "vx": vx,
        "vy": vy,
        "vz": vz,
    }
