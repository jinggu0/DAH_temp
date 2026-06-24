from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

EDGE_DEVICE_TYPES = {"uav_edge", "ugv_edge", "payload_edge", "c2_gateway", "test_harness"}


class EdgeRegistry:
    def __init__(self, state: Any):
        self.state = state
        self.devices: dict[str, dict[str, Any]] = {}
        self.ack_log: list[dict[str, Any]] = []

    def register(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        if not isinstance(payload, dict):
            raise ValueError("edge device payload must be an object")
        edge_id = _required_str(payload, "edge_id")
        device_type = _required_str(payload, "device_type")
        if device_type not in EDGE_DEVICE_TYPES:
            raise ValueError(f"unsupported device_type:{device_type}")
        asset_ids = _string_list(payload.get("asset_ids", []))
        known_assets = self.state._known_asset_ids()
        for asset_id in asset_ids:
            if asset_id not in known_assets:
                raise ValueError(f"unknown asset_id:{asset_id}")
        device = {
            "edge_id": edge_id,
            "device_type": device_type,
            "role": str(payload.get("role", "edge_gateway")),
            "asset_ids": asset_ids,
            "capabilities": _string_list(payload.get("capabilities", [])),
            "link_profiles": _string_list(payload.get("link_profiles", [])),
            "authority": str(payload.get("authority", "External Edge Cell")),
            "software_version": str(payload.get("software_version", "dev")),
            "public_key_fingerprint": str(payload.get("public_key_fingerprint", "")),
            "status": "registered",
            "registered_at": _now(),
            "last_seen_utc": None,
            "health": {},
            "egress_policy": "approved_queue_only",
        }
        self.devices[edge_id] = device
        self.state._audit("edge_device.registered", device)
        return dict(device)

    def heartbeat(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        edge_id = _required_str(payload, "edge_id")
        device = self._get_device(edge_id)
        device["status"] = str(payload.get("status", "online"))
        device["last_seen_utc"] = _now()
        device["health"] = {
            "cpu_load": float(payload.get("cpu_load", 0.0)),
            "battery_wh": float(payload.get("battery_wh", 0.0)),
            "link_quality": float(payload.get("link_quality", 1.0)),
            "temperature_c": float(payload.get("temperature_c", 0.0)),
        }
        self.state._audit("edge_device.heartbeat", device)
        return dict(device)

    def devices_payload(self) -> dict[str, Any]:
        rows = [dict(device) for device in self.devices.values()]
        return {"edge_devices": rows, "count": len(rows)}

    def work_payload(self, edge_id: str) -> dict[str, Any]:
        device = self._get_device(edge_id)
        asset_ids = set(device["asset_ids"])
        commands = [
            dict(command)
            for command in self.state.command_queue.values()
            if command["status"] == "approved_for_gateway" and command["asset_id"] in asset_ids
        ]
        mission_uploads = [
            dict(upload)
            for upload in self.state.mission_upload_queue.values()
            if upload["status"] == "approved_for_gateway" and upload["asset_id"] in asset_ids
        ]
        return {
            "edge_id": edge_id,
            "device_type": device["device_type"],
            "asset_ids": sorted(asset_ids),
            "egress_policy": device["egress_policy"],
            "safety_interlock": "local_edge_must_validate_before_actuation",
            "commands": commands,
            "mission_uploads": mission_uploads,
        }

    def acknowledge(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        edge_id = _required_str(payload, "edge_id")
        object_type = _required_str(payload, "object_type")
        object_id = _required_str(payload, "object_id")
        result = str(payload.get("result", "received"))
        device = self._get_device(edge_id)
        asset_ids = set(device["asset_ids"])
        if object_type == "command":
            item = self.state._get_command(object_id)
            if item["asset_id"] not in asset_ids:
                raise ValueError(f"edge device is not assigned to asset:{item['asset_id']}")
            item["edge_ack"] = {"edge_id": edge_id, "result": result, "timestamp_utc": _now()}
        elif object_type == "mission_upload":
            item = self.state._get_mission_upload(object_id)
            if item["asset_id"] not in asset_ids:
                raise ValueError(f"edge device is not assigned to asset:{item['asset_id']}")
            item["edge_ack"] = {"edge_id": edge_id, "result": result, "timestamp_utc": _now()}
        else:
            raise ValueError(f"unsupported object_type:{object_type}")
        ack = {
            "ack_id": str(uuid4()),
            "edge_id": edge_id,
            "object_type": object_type,
            "object_id": object_id,
            "result": result,
            "timestamp_utc": _now(),
        }
        self.ack_log.append(ack)
        self.state._audit("edge_work.acknowledged", ack)
        return ack

    def _get_device(self, edge_id: str) -> dict[str, Any]:
        device = self.devices.get(edge_id)
        if device is None:
            raise ValueError(f"unknown edge_id:{edge_id}")
        return device


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list of strings")
    return [str(item) for item in value]


def _now() -> str:
    return datetime.now(UTC).isoformat()
