from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import dataclass
from typing import Any

MAVLINK_V2_STX = 0xFD
MAVLINK_IFLAG_SIGNED = 0x01
MAVLINK_EPOCH_OFFSET_S = 1_420_070_400

MESSAGE_IDS = {
    "MISSION_ITEM_INT": 73,
    "COMMAND_LONG": 76,
    "COMMAND_ACK": 77,
}

CRC_EXTRA = {
    73: 38,   # MISSION_ITEM_INT, common.xml
    76: 152,  # COMMAND_LONG, common.xml
    77: 143,  # COMMAND_ACK, common.xml
}

COMMAND_IDS = {
    "MAV_CMD_NAV_WAYPOINT": 16,
    "MAV_CMD_NAV_RETURN_TO_LAUNCH": 20,
    "MAV_CMD_NAV_LAND": 21,
    "MAV_CMD_DO_SET_MODE": 176,
    "MAV_CMD_DO_PAUSE_CONTINUE": 193,
}

ACK_RESULTS = {
    0: "MAV_RESULT_ACCEPTED",
    1: "MAV_RESULT_TEMPORARILY_REJECTED",
    2: "MAV_RESULT_DENIED",
    3: "MAV_RESULT_UNSUPPORTED",
    4: "MAV_RESULT_FAILED",
    5: "MAV_RESULT_IN_PROGRESS",
}


@dataclass(frozen=True)
class OutboundMavlinkFrame:
    object_type: str
    object_id: str
    asset_id: str
    system_id: int
    component_id: int
    message_name: str
    command_id: int | None
    payload: bytes
    frame: bytes


def build_command_long_frames(
    *,
    command: dict[str, Any],
    system_id: int,
    component_id: int,
    sequence: int,
    signing_key: bytes | None = None,
    signing_link_id: int = 0,
    signing_timestamp: int | None = None,
) -> list[OutboundMavlinkFrame]:
    mavlink_command = command.get("mavlink_command", {})
    command_name = str(mavlink_command.get("command", command.get("command_type", "")))
    command_id = _command_id(command_name)
    params = _command_params(mavlink_command.get("params", command.get("params", {})))
    payload = struct.pack(
        "<fffffffHBBB",
        params[0],
        params[1],
        params[2],
        params[3],
        params[4],
        params[5],
        params[6],
        command_id,
        system_id,
        component_id,
        0,
    )
    frame = build_mavlink2_frame(
        seq=sequence,
        system_id=255,
        component_id=190,
        message_id=MESSAGE_IDS["COMMAND_LONG"],
        payload=payload,
        signing_key=signing_key,
        signing_link_id=signing_link_id,
        signing_timestamp=signing_timestamp,
    )
    return [
        OutboundMavlinkFrame(
            object_type="command",
            object_id=str(command["command_id"]),
            asset_id=str(command["asset_id"]),
            system_id=system_id,
            component_id=component_id,
            message_name="COMMAND_LONG",
            command_id=command_id,
            payload=payload,
            frame=frame,
        )
    ]


def build_mission_item_int_frames(
    *,
    upload: dict[str, Any],
    system_id: int,
    component_id: int,
    sequence_start: int,
    signing_key: bytes | None = None,
    signing_link_id: int = 0,
    signing_timestamp: int | None = None,
) -> list[OutboundMavlinkFrame]:
    frames: list[OutboundMavlinkFrame] = []
    for index, item in enumerate(upload.get("mavlink_items", [])):
        fields = item.get("fields", {})
        command_id = _command_id(str(fields.get("command", "MAV_CMD_NAV_WAYPOINT")))
        payload = struct.pack(
            "<ffffiifHHBBBBB",
            float(fields.get("param1", 0.0)),
            float(fields.get("param2", 0.0)),
            float(fields.get("param3", 0.0)),
            float(fields.get("param4", 0.0)),
            int(fields.get("x", 0)),
            int(fields.get("y", 0)),
            float(fields.get("z", 0.0)),
            int(fields.get("seq", index)),
            command_id,
            system_id,
            component_id,
            int(fields.get("frame", 6) if isinstance(fields.get("frame", 6), int) else 6),
            int(fields.get("current", 0)),
            int(fields.get("autocontinue", 1)),
            0,
        )
        frame = build_mavlink2_frame(
            seq=(sequence_start + index) % 256,
            system_id=255,
            component_id=190,
            message_id=MESSAGE_IDS["MISSION_ITEM_INT"],
            payload=payload,
            signing_key=signing_key,
            signing_link_id=signing_link_id,
            signing_timestamp=None if signing_timestamp is None else signing_timestamp + index,
        )
        frames.append(
            OutboundMavlinkFrame(
                object_type="mission_upload",
                object_id=str(upload["upload_id"]),
                asset_id=str(upload["asset_id"]),
                system_id=system_id,
                component_id=component_id,
                message_name="MISSION_ITEM_INT",
                command_id=command_id,
                payload=payload,
                frame=frame,
            )
        )
    return frames


def build_mavlink2_frame(
    *,
    seq: int,
    system_id: int,
    component_id: int,
    message_id: int,
    payload: bytes,
    signing_key: bytes | None = None,
    signing_link_id: int = 0,
    signing_timestamp: int | None = None,
) -> bytes:
    if signing_key is not None and len(signing_key) != 32:
        raise ValueError("MAVLink signing key must be 32 bytes")
    incompat_flags = MAVLINK_IFLAG_SIGNED if signing_key else 0
    header = bytes(
        [
            MAVLINK_V2_STX,
            len(payload),
            incompat_flags,
            0,
            seq % 256,
            system_id,
            component_id,
            message_id & 0xFF,
            (message_id >> 8) & 0xFF,
            (message_id >> 16) & 0xFF,
        ]
    )
    crc = x25_checksum(header[1:] + payload + bytes([CRC_EXTRA.get(message_id, 0)]))
    packet = header + payload + struct.pack("<H", crc)
    if signing_key is None:
        return packet
    timestamp = signing_timestamp if signing_timestamp is not None else mavlink_signing_timestamp()
    return packet + sign_packet(packet, signing_key=signing_key, link_id=signing_link_id, timestamp=timestamp)


def sign_packet(packet: bytes, *, signing_key: bytes, link_id: int, timestamp: int) -> bytes:
    if not 0 <= link_id <= 255:
        raise ValueError("MAVLink signing link id must fit in uint8")
    timestamp_bytes = int(timestamp).to_bytes(6, "little", signed=False)
    prefix = bytes([link_id]) + timestamp_bytes
    signature = hashlib.sha256(signing_key + packet + prefix).digest()[:6]
    return prefix + signature


def mavlink_signing_timestamp(now_s: float | None = None) -> int:
    now = time.time() if now_s is None else now_s
    return max(0, int((now - MAVLINK_EPOCH_OFFSET_S) * 100_000))


def x25_checksum(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        tmp = byte ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def _command_id(command_name: str) -> int:
    if command_name.isdigit():
        return int(command_name)
    return COMMAND_IDS.get(command_name, 0)


def _command_params(params: Any) -> list[float]:
    if not isinstance(params, dict):
        return [0.0] * 7
    values = []
    for index in range(1, 8):
        values.append(float(params.get(f"param{index}", 0.0)))
    if "x" in params:
        values[4] = float(params["x"])
    if "y" in params:
        values[5] = float(params["y"])
    if "z" in params:
        values[6] = float(params["z"])
    return values