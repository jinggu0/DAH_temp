from __future__ import annotations

import argparse
import json
import socket
import struct
import time
from pathlib import Path
from typing import Any

from uas_utm.simulator import load_scenario
from uas_utm_gateway.mavlink_builder import COMMAND_IDS, MESSAGE_IDS, build_mavlink2_frame
from uas_utm_gateway.mavlink_parser import ParsedMavlinkFrame, parse_datagram
from uas_utm_gateway.service_client import UtmServiceClient


def build_global_position_int_frame(
    *,
    seq: int,
    system_id: int,
    component_id: int,
    lat_e7: int,
    lon_e7: int,
    alt_m: float,
    vx_cm_s: int = 0,
    vy_cm_s: int = 0,
    vz_cm_s: int = 0,
    heading_cdeg: int = 0,
    time_boot_ms: int = 1000,
) -> bytes:
    alt_mm = int(alt_m * 1000)
    payload = struct.pack(
        "<IiiiihhhH",
        time_boot_ms,
        lat_e7,
        lon_e7,
        alt_mm,
        alt_mm,
        vx_cm_s,
        vy_cm_s,
        vz_cm_s,
        heading_cdeg,
    )
    return build_mavlink2_frame(
        seq=seq,
        system_id=system_id,
        component_id=component_id,
        message_id=33,
        payload=payload,
    )


def build_command_ack_frame(*, seq: int, system_id: int, component_id: int, command_id: int, result: int = 0) -> bytes:
    return build_mavlink2_frame(
        seq=seq,
        system_id=system_id,
        component_id=component_id,
        message_id=MESSAGE_IDS["COMMAND_ACK"],
        payload=struct.pack("<HB", command_id, result),
    )


def run_smoke_test(
    *,
    scenario_path: Path,
    service_url: str,
    gateway_host: str,
    gateway_port: int,
    local_host: str,
    local_port: int,
    asset_id: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    scenario = load_scenario(scenario_path)
    asset = next((item for item in scenario.assets if item.id == asset_id), None) if asset_id else None
    if asset is None:
        asset = next(item for item in scenario.assets if "mavlink_udp" in item.datalink_profiles)
    client = UtmServiceClient(service_url, timeout_s=timeout_s)

    command = client.post(
        "/api/commands/request",
        {
            "payload": {
                "asset_id": asset.id,
                "command_type": "hold_position",
                "requested_by": "mavlink-smoke-test",
                "priority": 2,
                "params": {"param1": 0},
            }
        },
    )["payload"]
    approved = client.post(
        "/api/commands/approve",
        {"payload": {"command_id": command["command_id"], "approver": "mavlink-smoke-test"}},
    )["payload"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((local_host, local_port))
    sock.settimeout(timeout_s)
    gateway_address = (gateway_host, gateway_port)
    try:
        frame = build_global_position_int_frame(
            seq=1,
            system_id=asset.system_id,
            component_id=asset.component_id,
            lat_e7=scenario.origin_lat_e7,
            lon_e7=scenario.origin_lon_e7,
            alt_m=asset.start[2],
            vx_cm_s=int(asset.cruise_speed_mps * 100),
            time_boot_ms=1000,
        )
        sock.sendto(frame, gateway_address)
        outbound = _receive_until(sock, "COMMAND_LONG", timeout_s)
        command_id = int(outbound.fields.get("raw_payload_len", 0))
        if outbound.message_name == "COMMAND_LONG":
            command_id = COMMAND_IDS["MAV_CMD_DO_PAUSE_CONTINUE"]
        sock.sendto(
            build_command_ack_frame(
                seq=2,
                system_id=asset.system_id,
                component_id=asset.component_id,
                command_id=command_id,
                result=0,
            ),
            gateway_address,
        )
        return {
            "accepted": True,
            "asset_id": asset.id,
            "command_id": approved["command_id"],
            "received_message": outbound.message_name,
            "local_endpoint": f"{local_host}:{sock.getsockname()[1]}",
            "gateway_endpoint": f"{gateway_host}:{gateway_port}",
        }
    finally:
        sock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a mock external MAVLink endpoint smoke test against the bidirectional gateway.")
    parser.add_argument("--scenario", default="scenarios/korea_defense_uas_utm_ops.json")
    parser.add_argument("--service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--gateway-host", default="127.0.0.1")
    parser.add_argument("--gateway-port", type=int, default=14551)
    parser.add_argument("--local-host", default="0.0.0.0")
    parser.add_argument("--local-port", type=int, default=0)
    parser.add_argument("--asset-id", default=None)
    parser.add_argument("--timeout-s", type=float, default=5.0)
    args = parser.parse_args(argv)

    result = run_smoke_test(
        scenario_path=Path(args.scenario),
        service_url=args.service_url,
        gateway_host=args.gateway_host,
        gateway_port=args.gateway_port,
        local_host=args.local_host,
        local_port=args.local_port,
        asset_id=args.asset_id,
        timeout_s=args.timeout_s,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _receive_until(sock: socket.socket, message_name: str, timeout_s: float) -> ParsedMavlinkFrame:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        datagram, _ = sock.recvfrom(65535)
        for frame in parse_datagram(datagram):
            if isinstance(frame, ParsedMavlinkFrame) and frame.message_name == message_name:
                return frame
    raise TimeoutError(f"did not receive {message_name} within {timeout_s}s")


if __name__ == "__main__":
    raise SystemExit(main())
