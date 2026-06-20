from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from uas_utm.mavlink_adapter import mission_to_mavlink_items
from uas_utm.models import TelemetryFrame
from uas_utm.simulator import load_scenario, run_environment, summarize_result


class ServiceState:
    def __init__(self, scenario_path: Path):
        self.scenario_path = scenario_path
        self._lock = Lock()
        self.external_frames: dict[str, dict[str, Any]] = {}
        self.command_queue: dict[str, dict[str, Any]] = {}
        self.mission_upload_queue: dict[str, dict[str, Any]] = {}
        self.audit_log: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self.scenario = load_scenario(self.scenario_path)
            self.result = run_environment(self.scenario)
            self.summary = summarize_result(self.result)
            self.frames_by_time: dict[int, list[TelemetryFrame]] = {}
            for frame in self.result.telemetry:
                self.frames_by_time.setdefault(frame.time_s, []).append(frame)
            self.timeline = sorted(self.frames_by_time)

    def scenario_payload(self) -> dict[str, Any]:
        return {
            "name": self.scenario.name,
            "duration_s": self.scenario.duration_s,
            "step_s": self.scenario.step_s,
            "conflict_distance_m": self.scenario.conflict_distance_m,
            "origin_lat_e7": self.scenario.origin_lat_e7,
            "origin_lon_e7": self.scenario.origin_lon_e7,
            "assets": [asdict(asset) for asset in self.scenario.assets],
            "zones": [asdict(zone) for zone in self.scenario.zones],
            "c2_nodes": [asdict(node) for node in self.scenario.c2_nodes],
            "missions": [asdict(mission) for mission in self.scenario.missions],
        }

    def decisions_payload(self) -> list[dict[str, Any]]:
        return [asdict(decision) for decision in self.result.decisions]

    def telemetry_snapshot(self, requested_time_s: int | None = None) -> dict[str, Any]:
        time_s = self._nearest_time(requested_time_s)
        frames = self.frames_by_time.get(time_s, [])
        return {
            "time_s": time_s,
            "frames": [asdict(frame) for frame in frames],
        }

    def live_snapshot(self, requested_time_s: int | None = None) -> dict[str, Any]:
        snapshot = self.telemetry_snapshot(requested_time_s)
        with self._lock:
            external_frames = list(self.external_frames.values())
        snapshot["external_frames"] = external_frames
        snapshot["mode"] = "hybrid" if external_frames else "simulation"
        return snapshot

    def ingest_telemetry(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        if not isinstance(payload, dict):
            raise ValueError("telemetry payload must be an object")
        asset_id = str(payload.get("asset_id", "")).strip()
        position = payload.get("position")
        if not asset_id:
            raise ValueError("asset_id is required")
        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("position must be [x, y, z]")

        normalized = {
            "time_s": int(payload.get("time_s", self.timeline[-1] if self.timeline else 0)),
            "asset_id": asset_id,
            "mission_id": payload.get("mission_id"),
            "position": [float(position[0]), float(position[1]), float(position[2])],
            "status": str(payload.get("status", "external")),
            "battery_wh": float(payload.get("battery_wh", 0.0)),
            "velocity_mps": payload.get("velocity_mps", [0.0, 0.0, 0.0]),
            "heading_deg": float(payload.get("heading_deg", 0.0)),
            "c2_node_id": payload.get("c2_node_id"),
            "link_profile": payload.get("link_profile"),
            "source": str(payload.get("source", "external")),
        }
        with self._lock:
            self.external_frames[asset_id] = normalized
        return {
            "accepted": True,
            "asset_id": asset_id,
            "external_asset_count": len(self.external_frames),
        }

    def request_command(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        if not isinstance(payload, dict):
            raise ValueError("command payload must be an object")
        asset_id = _required_str(payload, "asset_id")
        command_type = _required_str(payload, "command_type")
        if asset_id not in self._known_asset_ids():
            raise ValueError(f"unknown asset_id:{asset_id}")
        command_id = str(uuid4())
        command = {
            "command_id": command_id,
            "asset_id": asset_id,
            "command_type": command_type,
            "params": payload.get("params", {}),
            "requested_by": str(payload.get("requested_by", "operator")),
            "priority": int(payload.get("priority", 3)),
            "status": "pending_approval",
            "created_at": _now(),
            "approved_by": None,
            "approved_at": None,
            "rejected_by": None,
            "rejected_at": None,
            "rejection_reason": None,
            "mavlink_command": _command_to_mavlink(command_type, payload.get("params", {})),
        }
        with self._lock:
            self.command_queue[command_id] = command
            self._audit("command.requested", command)
        return dict(command)

    def approve_command(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        command_id = _required_str(payload, "command_id")
        approver = str(payload.get("approver", "approver"))
        with self._lock:
            command = self._get_command(command_id)
            if command["status"] != "pending_approval":
                raise ValueError(f"command is not pending:{command_id}")
            command["status"] = "approved_for_gateway"
            command["approved_by"] = approver
            command["approved_at"] = _now()
            self._audit("command.approved", command)
            return dict(command)

    def reject_command(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        command_id = _required_str(payload, "command_id")
        rejector = str(payload.get("rejector", "approver"))
        reason = str(payload.get("reason", "rejected by operator"))
        with self._lock:
            command = self._get_command(command_id)
            if command["status"] != "pending_approval":
                raise ValueError(f"command is not pending:{command_id}")
            command["status"] = "rejected"
            command["rejected_by"] = rejector
            command["rejected_at"] = _now()
            command["rejection_reason"] = reason
            self._audit("command.rejected", command)
            return dict(command)

    def commands_payload(self, status: str | None = None) -> dict[str, Any]:
        with self._lock:
            commands = list(self.command_queue.values())
        if status:
            commands = [command for command in commands if command["status"] == status]
        return {"commands": commands}

    def request_mission_upload(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        mission_id = _required_str(payload, "mission_id")
        requested_by = str(payload.get("requested_by", "operator"))
        mission = self._mission_by_id(mission_id)
        if mission is None:
            raise ValueError(f"unknown mission_id:{mission_id}")
        if mission_id not in self.summary.get("approved_missions", []):
            raise ValueError(f"mission is not UTM-approved:{mission_id}")
        asset = self._asset_by_id(mission.asset_id)
        upload_id = str(uuid4())
        mavlink_items = mission_to_mavlink_items(scenario=self.scenario, asset=asset, mission=mission)
        upload = {
            "upload_id": upload_id,
            "mission_id": mission_id,
            "asset_id": mission.asset_id,
            "requested_by": requested_by,
            "status": "pending_approval",
            "created_at": _now(),
            "approved_by": None,
            "approved_at": None,
            "rejected_by": None,
            "rejected_at": None,
            "rejection_reason": None,
            "mavlink_items": [asdict(item) for item in mavlink_items],
        }
        with self._lock:
            self.mission_upload_queue[upload_id] = upload
            self._audit("mission_upload.requested", upload)
        return dict(upload)

    def approve_mission_upload(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        upload_id = _required_str(payload, "upload_id")
        approver = str(payload.get("approver", "approver"))
        with self._lock:
            upload = self._get_mission_upload(upload_id)
            if upload["status"] != "pending_approval":
                raise ValueError(f"mission upload is not pending:{upload_id}")
            upload["status"] = "approved_for_gateway"
            upload["approved_by"] = approver
            upload["approved_at"] = _now()
            self._audit("mission_upload.approved", upload)
            return dict(upload)

    def mission_uploads_payload(self, status: str | None = None) -> dict[str, Any]:
        with self._lock:
            uploads = list(self.mission_upload_queue.values())
        if status:
            uploads = [upload for upload in uploads if upload["status"] == status]
        return {"mission_uploads": uploads}

    def audit_payload(self, limit: int = 100) -> dict[str, Any]:
        with self._lock:
            rows = self.audit_log[-limit:]
        return {"audit": rows, "limit": limit}

    def timeline_payload(self) -> dict[str, Any]:
        return {
            "start_s": self.timeline[0] if self.timeline else 0,
            "end_s": self.timeline[-1] if self.timeline else 0,
            "step_s": self.scenario.step_s,
            "ticks": self.timeline,
        }

    def mavlink_payload(self, asset_id: str | None = None, limit: int = 80) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for frame in self.result.telemetry:
            if asset_id and frame.asset_id != asset_id:
                continue
            for message in frame.mavlink_messages:
                rows.append(
                    {
                        "time_s": frame.time_s,
                        "asset_id": frame.asset_id,
                        "mission_id": frame.mission_id,
                        "message": asdict(message),
                    }
                )
        return {
            "asset_id": asset_id,
            "limit": limit,
            "messages": rows[-limit:],
        }

    def _audit(self, event_type: str, data: dict[str, Any]) -> None:
        self.audit_log.append(
            {
                "event_id": str(uuid4()),
                "event_type": event_type,
                "timestamp_utc": _now(),
                "object_id": data.get("command_id") or data.get("upload_id") or data.get("mission_id"),
                "status": data.get("status"),
            }
        )

    def _known_asset_ids(self) -> set[str]:
        asset_ids = {asset.id for asset in self.scenario.assets}
        asset_ids.update(self.external_frames)
        return asset_ids

    def _asset_by_id(self, asset_id: str):
        for asset in self.scenario.assets:
            if asset.id == asset_id:
                return asset
        raise ValueError(f"unknown asset_id:{asset_id}")

    def _mission_by_id(self, mission_id: str):
        for mission in self.scenario.missions:
            if mission.id == mission_id:
                return mission
        return None

    def _get_command(self, command_id: str) -> dict[str, Any]:
        command = self.command_queue.get(command_id)
        if command is None:
            raise ValueError(f"unknown command_id:{command_id}")
        return command

    def _get_mission_upload(self, upload_id: str) -> dict[str, Any]:
        upload = self.mission_upload_queue.get(upload_id)
        if upload is None:
            raise ValueError(f"unknown upload_id:{upload_id}")
        return upload

    def _nearest_time(self, requested_time_s: int | None) -> int:
        if not self.timeline:
            return 0
        if requested_time_s is None:
            return self.timeline[-1]
        return min(self.timeline, key=lambda item: abs(item - requested_time_s))


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _command_to_mavlink(command_type: str, params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        params = {}
    mapping = {
        "hold_position": "MAV_CMD_DO_PAUSE_CONTINUE",
        "return_to_launch": "MAV_CMD_NAV_RETURN_TO_LAUNCH",
        "set_mode": "MAV_CMD_DO_SET_MODE",
        "goto": "MAV_CMD_NAV_WAYPOINT",
        "land": "MAV_CMD_NAV_LAND",
    }
    return {
        "message_name": "COMMAND_LONG",
        "command": mapping.get(command_type, command_type),
        "params": params,
        "transmission_state": "queued_not_transmitted",
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
