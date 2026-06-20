from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uas_utm.simulator import load_scenario

from .mavlink_parser import ParsedMavlinkFrame


@dataclass
class AssetTrackState:
    asset_id: str
    battery_remaining: int | None = None
    mission_seq: int | None = None
    status: str = "mavlink-live"


class MavlinkTelemetryTranslator:
    def __init__(self, scenario_path: Path):
        self.scenario = load_scenario(scenario_path)
        self.asset_by_system_id = {asset.system_id: asset for asset in self.scenario.assets}
        self.track_state: dict[int, AssetTrackState] = {
            asset.system_id: AssetTrackState(asset_id=asset.id) for asset in self.scenario.assets
        }

    def translate(self, item: ParsedMavlinkFrame | dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(item, dict):
            return self._translate_json(item)
        state = self.track_state.get(item.system_id)
        if state is None:
            return None
        if item.message_name == "HEARTBEAT":
            state.status = _heartbeat_status(item.fields.get("system_status"))
            return None
        if item.message_name == "SYS_STATUS":
            battery = item.fields.get("battery_remaining")
            state.battery_remaining = int(battery) if battery is not None else None
            return None
        if item.message_name == "MISSION_CURRENT":
            seq = item.fields.get("seq")
            state.mission_seq = int(seq) if seq is not None else None
            return None
        if item.message_name in {"GLOBAL_POSITION_INT", "UTM_GLOBAL_POSITION"}:
            return self._position_payload(item, state)
        return None

    def _translate_json(self, item: dict[str, Any]) -> dict[str, Any] | None:
        payload = item.get("payload", item)
        if not isinstance(payload, dict):
            return None
        if "asset_id" not in payload or "position" not in payload:
            return None
        return {"payload": {**payload, "source": payload.get("source", "mavlink-json-udp")}}

    def _position_payload(self, frame: ParsedMavlinkFrame, state: AssetTrackState) -> dict[str, Any]:
        fields = frame.fields
        position = local_position_from_wgs84_int(
            lat=int(fields["lat"]),
            lon=int(fields["lon"]),
            alt_mm=int(fields.get("relative_alt", fields.get("alt", 0))),
            origin_lat_e7=self.scenario.origin_lat_e7,
            origin_lon_e7=self.scenario.origin_lon_e7,
        )
        return {
            "payload": {
                "asset_id": state.asset_id,
                "time_s": int(fields.get("time_boot_ms", fields.get("time", 0)) / 1000),
                "position": [round(position[0], 3), round(position[1], 3), round(position[2], 3)],
                "velocity_mps": [
                    round(float(fields.get("vx", 0)) / 100.0, 3),
                    round(float(fields.get("vy", 0)) / 100.0, 3),
                    round(-float(fields.get("vz", 0)) / 100.0, 3),
                ],
                "heading_deg": round(float(fields.get("hdg", 0)) / 100.0, 2),
                "status": state.status,
                "battery_wh": float(state.battery_remaining or 0),
                "link_profile": "mavlink_udp",
                "source": "mavlink-udp-gateway",
            }
        }


def local_position_from_wgs84_int(
    *,
    lat: int,
    lon: int,
    alt_mm: int,
    origin_lat_e7: int,
    origin_lon_e7: int,
) -> tuple[float, float, float]:
    y_m = (lat - origin_lat_e7) / 10_000_000 * 111_320
    x_m = (lon - origin_lon_e7) / 10_000_000 * 88_800
    z_m = alt_mm / 1000
    return x_m, y_m, z_m


def _heartbeat_status(system_status: Any) -> str:
    if system_status == 4:
        return "active"
    if system_status in {3, 5}:
        return "standby"
    return "mavlink-live"
