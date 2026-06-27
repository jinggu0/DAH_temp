from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from uas_utm.mavlink_adapter import mission_to_mavlink_items
from uas_utm_edge import EdgeRegistry
from uas_utm.models import TelemetryFrame
from uas_utm.simulator import load_scenario, run_environment, summarize_result

from .log_store import JsonlAuditStore, agent_observation


class ServiceState:
    def __init__(self, scenario_path: Path, log_dir: Path | None = None):
        self.scenario_path = scenario_path
        self._lock = Lock()
        self.external_frames: dict[str, dict[str, Any]] = {}
        self.command_queue: dict[str, dict[str, Any]] = {}
        self.mission_upload_queue: dict[str, dict[str, Any]] = {}
        self.audit_log: list[dict[str, Any]] = []
        self.runtime_log: list[dict[str, Any]] = []
        self.audit_store = JsonlAuditStore(log_dir or Path("logs/uas_utm"))
        self.edge_registry = EdgeRegistry(self)
        self.source_registry: dict[str, dict[str, Any]] = {
            "simulation": {
                "source_id": "simulation",
                "source_type": "scenario_replay",
                "authority": "Joint UTM Cell",
                "domain": "operation_support",
                "base_confidence": 0.82,
            },
            "mavlink-udp-adapter": {
                "source_id": "mavlink-udp-adapter",
                "source_type": "mavlink_gateway",
                "authority": "C2 / Ground Control",
                "domain": "datalink",
                "base_confidence": 0.92,
            },
            "manual-operator": {
                "source_id": "manual-operator",
                "source_type": "operator_entry",
                "authority": "C2 / Ground Control",
                "domain": "operation_support",
                "base_confidence": 0.55,
            },
        }
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

    def operation_profile(self) -> dict[str, Any]:
        return {
            "alignment_note": (
                "Public Korean defense-contractor structures are modeled as generic platform, payload, C2, "
                "datalink, and operation-support domains. This simulator does not copy non-public systems."
            ),
            "domains": [
                {
                    "domain": "platform",
                    "service_fields": ["asset_id", "platform_class", "service_branch", "endurance_s"],
                },
                {
                    "domain": "mission_payload",
                    "service_fields": ["sensor_payloads", "required_payloads", "mission_type"],
                },
                {
                    "domain": "c2_ground_control",
                    "service_fields": ["c2_node_id", "authority", "operator", "approver"],
                },
                {
                    "domain": "datalink",
                    "service_fields": ["link_profile", "source_id", "mavlink_command", "mavlink_items"],
                },
                {
                    "domain": "operation_support",
                    "service_fields": ["audit_log", "track_confidence", "gateway_queue", "docker_profile"],
                },
            ],
            "roles": [
                {"role": "viewer", "can": ["read_scenario", "read_tracks", "read_audit"]},
                {"role": "operator", "can": ["request_command", "request_mission_upload", "ingest_manual_telemetry"]},
                {"role": "approver", "can": ["approve_command", "reject_command", "approve_mission_upload"]},
                {"role": "gateway", "can": ["read_approved_commands", "read_approved_mission_uploads", "ingest_mavlink"]},
                {"role": "edge_gateway", "can": ["register_device", "send_heartbeat", "ingest_edge_telemetry", "poll_approved_work", "ack_work"]},
                {"role": "maintainer", "can": ["read_device_health", "read_audit", "rotate_device_profile"]},
                {"role": "admin", "can": ["operate_service", "configure_sources"]},
            ],
            "source_registry": list(self.source_registry.values()),
            "edge_boundary": {
                "purpose": "UAV/UGV edge devices communicate with UTM through approved telemetry and work queues.",
                "safety": "Approved work is queued for a local safety interlock; this simulator does not drive real actuators.",
                "device_types": ["uav_edge", "ugv_edge", "payload_edge", "c2_gateway", "test_harness"],
            },
        }


    def register_edge_device(self, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.register(message)

    def heartbeat_edge_device(self, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.heartbeat(message)

    def edge_devices_payload(self) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.devices_payload()

    def edge_work_payload(self, edge_id: str) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.work_payload(edge_id)

    def ack_edge_work(self, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.acknowledge(message)

    def tracks_payload(self, requested_time_s: int | None = None) -> dict[str, Any]:
        time_s = self._nearest_time(requested_time_s)
        frames = self.frames_by_time.get(time_s, [])
        sources_by_asset: dict[str, list[dict[str, Any]]] = {}

        for frame in frames:
            source = self._source_sample_from_frame(frame, time_s)
            sources_by_asset.setdefault(frame.asset_id, []).append(source)

        with self._lock:
            external_frames = list(self.external_frames.values())
        for frame in external_frames:
            source = self._source_sample_from_external(frame, time_s)
            sources_by_asset.setdefault(source["asset_id"], []).append(source)

        tracks = []
        for asset_id, sources in sorted(sources_by_asset.items()):
            sources.sort(key=lambda item: (item["stale"], -item["confidence"], item["source_id"]))
            primary = sources[0]
            asset = self._asset_metadata(asset_id)
            confidence = min(1.0, primary["confidence"] + max(0, len(sources) - 1) * 0.03)
            tracks.append(
                {
                    "asset_id": asset_id,
                    "callsign": asset.get("callsign"),
                    "platform_class": asset.get("platform_class", "external"),
                    "service_branch": asset.get("service_branch", "external"),
                    "status": primary["status"],
                    "mission_id": primary.get("mission_id"),
                    "c2_node_id": primary.get("c2_node_id"),
                    "link_profile": primary.get("link_profile"),
                    "fused_position": primary["position"],
                    "fused_velocity_mps": primary["velocity_mps"],
                    "heading_deg": primary["heading_deg"],
                    "battery_wh": primary["battery_wh"],
                    "confidence": round(confidence, 3),
                    "source_count": len(sources),
                    "stale": all(source["stale"] for source in sources),
                    "primary_source_id": primary["source_id"],
                    "authority": primary["authority"],
                    "sources": sources,
                }
            )
        return {
            "time_s": time_s,
            "track_count": len(tracks),
            "mode": "fused" if any(track["source_count"] > 1 for track in tracks) else "single_source",
            "tracks": tracks,
        }

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
            "source_id": str(payload.get("source_id", payload.get("source", "external"))),
            "source_type": str(payload.get("source_type", "telemetry_adapter")),
            "source_authority": str(payload.get("source_authority", "External Adapter")),
            "track_confidence": float(payload.get("track_confidence", 0.0)),
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

    def audit_payload(self, limit: int = 100, event_type: str | None = None) -> dict[str, Any]:
        with self._lock:
            memory_rows = self.audit_log[-limit:]
            persisted_rows = self.audit_store.tail(limit=limit, event_type=event_type)
        rows = persisted_rows or memory_rows
        if event_type and not persisted_rows:
            rows = [row for row in rows if row.get("event_type") == event_type]
        return {
            "audit": rows[-max(1, limit) :],
            "limit": limit,
            "event_type": event_type,
            "storage": self.audit_store.status(),
        }


    def protocol_logs_payload(self, limit: int = 100, include_heartbeat: bool = True) -> dict[str, Any]:
        audit = self.audit_payload(limit=max(limit * 5, limit)).get("audit", [])
        rows = []
        for row in audit:
            if not include_heartbeat and row.get("event_type") == "edge_device.heartbeat":
                continue
            rows.append(_protocol_log_row(row))
        rows = rows[-max(1, limit) :]
        return {
            "schema_version": "uas-utm-protocol-log.v1",
            "limit": limit,
            "include_heartbeat": include_heartbeat,
            "count": len(rows),
            "protocol_logs": rows,
        }
    def agent_logs_payload(
        self,
        limit: int = 100,
        event_type: str | None = None,
        phase: str | None = None,
        include_heartbeat: bool = True,
    ) -> dict[str, Any]:
        audit = self.audit_payload(limit=max(limit * 5, limit), event_type=event_type)
        observations = [row.get("agent_view") or agent_observation(row) for row in audit["audit"]]
        if phase:
            observations = [item for item in observations if item.get("phase") == phase]
        if not include_heartbeat:
            observations = [item for item in observations if item.get("event_type") != "edge_device.heartbeat"]
        observations = observations[-max(1, limit) :]
        return {
            "schema_version": "uas-utm-agent-observation.v1",
            "limit": limit,
            "event_type": event_type,
            "phase": phase,
            "include_heartbeat": include_heartbeat,
            "observation_count": len(observations),
            "observations": observations,
            "safety_scope": "competition simulation planning and defensive analysis only",
        }

    def record_runtime_log(self, *, source: str, message: str, level: str = "info", data: dict[str, Any] | None = None) -> None:
        row = {
            "timestamp_utc": _now(),
            "source": source,
            "level": level,
            "message": message,
            "data": data or {},
        }
        with self._lock:
            self.runtime_log.append(row)
            if len(self.runtime_log) > 500:
                self.runtime_log = self.runtime_log[-500:]

    def runtime_logs_payload(self, limit: int = 100) -> dict[str, Any]:
        with self._lock:
            rows = list(self.runtime_log[-max(1, limit) :])
        return {
            "schema_version": "uas-utm-runtime-log.v1",
            "limit": limit,
            "count": len(rows),
            "runtime_logs": rows,
        }
    def logs_status_payload(self) -> dict[str, Any]:
        with self._lock:
            return self.audit_store.status()

    def verify_logs_payload(self) -> dict[str, Any]:
        with self._lock:
            return self.audit_store.verify()

    def baseline_export_payload(self, limit: int = 500) -> dict[str, Any]:
        final_time_s = self.timeline[-1] if self.timeline else 0
        telemetry_rows = []
        for frame in self.result.telemetry[: max(0, limit)]:
            telemetry_rows.append(
                {
                    "type": "telemetry_frame",
                    "time_s": frame.time_s,
                    "asset_id": frame.asset_id,
                    "mission_id": frame.mission_id,
                    "status": frame.status,
                    "position": list(frame.position),
                    "velocity_mps": list(frame.velocity_mps),
                    "c2_node_id": frame.c2_node_id,
                    "link_profile": frame.link_profile,
                }
            )
        return {
            "generated_at_utc": _now(),
            "scenario": self.scenario_payload(),
            "summary": self.summary,
            "decisions": self.decisions_payload(),
            "final_tracks": self.tracks_payload(final_time_s),
            "edge_devices": self.edge_devices_payload(),
            "audit": self.audit_payload(limit).get("audit", []),
            "log_storage": self.logs_status_payload(),
            "log_integrity": self.verify_logs_payload(),
            "agent_observations": self.agent_logs_payload(limit).get("observations", []),
            "telemetry_jsonl": telemetry_rows,
            "mavlink_message_counts": self.summary.get("mavlink_message_counts", {}),
            "baseline_notes": [
                "normal_operation_only",
                "approved_work_queue_only",
                "uav_ugv_joint_tracking_enabled",
            ],
        }
    def _source_sample_from_frame(self, frame: TelemetryFrame, time_s: int) -> dict[str, Any]:
        registry = self.source_registry["simulation"]
        return {
            "asset_id": frame.asset_id,
            "source_id": registry["source_id"],
            "source_type": registry["source_type"],
            "domain": registry["domain"],
            "authority": frame.c2_node_id or registry["authority"],
            "time_s": frame.time_s,
            "age_s": max(0, time_s - frame.time_s),
            "stale": False,
            "confidence": registry["base_confidence"] if frame.status == "active" else 0.5,
            "position": list(frame.position),
            "velocity_mps": list(frame.velocity_mps),
            "heading_deg": frame.heading_deg,
            "status": frame.status,
            "mission_id": frame.mission_id,
            "battery_wh": frame.battery_wh,
            "c2_node_id": frame.c2_node_id,
            "link_profile": frame.link_profile,
        }

    def _source_sample_from_external(self, frame: dict[str, Any], requested_time_s: int) -> dict[str, Any]:
        source_id = str(frame.get("source_id") or frame.get("source") or "external")
        registry = self.source_registry.get(source_id, {})
        base_confidence = float(registry.get("base_confidence", 0.65))
        explicit_confidence = float(frame.get("track_confidence") or 0.0)
        frame_time_s = int(frame.get("time_s", requested_time_s))
        age_s = abs(requested_time_s - frame_time_s)
        stale = age_s > max(10, self.scenario.step_s * 3)
        confidence = explicit_confidence if explicit_confidence > 0 else max(0.2, base_confidence - min(age_s, 60) * 0.01)
        return {
            "asset_id": str(frame["asset_id"]),
            "source_id": source_id,
            "source_type": str(frame.get("source_type") or registry.get("source_type", "external_adapter")),
            "domain": str(registry.get("domain", "datalink")),
            "authority": str(frame.get("source_authority") or registry.get("authority", "External Adapter")),
            "time_s": frame_time_s,
            "age_s": age_s,
            "stale": stale,
            "confidence": round(confidence, 3),
            "position": list(frame["position"]),
            "velocity_mps": list(frame.get("velocity_mps", [0.0, 0.0, 0.0])),
            "heading_deg": float(frame.get("heading_deg", 0.0)),
            "status": str(frame.get("status", "external")),
            "mission_id": frame.get("mission_id"),
            "battery_wh": float(frame.get("battery_wh", 0.0)),
            "c2_node_id": frame.get("c2_node_id"),
            "link_profile": frame.get("link_profile"),
        }

    def _asset_metadata(self, asset_id: str) -> dict[str, Any]:
        for asset in self.scenario.assets:
            if asset.id == asset_id:
                return asdict(asset)
        return {}

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
        row = self.audit_store.append(event_type=event_type, data=data)
        self.audit_log.append(row)

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


def _protocol_log_row(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data", {}) if isinstance(row.get("data"), dict) else {}
    agent_view = row.get("agent_view", {}) if isinstance(row.get("agent_view"), dict) else {}
    event_type = str(row.get("event_type", "unknown"))
    return {
        "timestamp_utc": row.get("timestamp_utc") or row.get("created_at"),
        "event_id": row.get("event_id"),
        "event_type": event_type,
        "direction": _protocol_direction(event_type),
        "transport": _protocol_transport(event_type, data),
        "message_type": _protocol_message_type(event_type, data),
        "actor": row.get("actor"),
        "object_type": row.get("object_type"),
        "object_id": row.get("object_id"),
        "asset_id": data.get("asset_id"),
        "mission_id": data.get("mission_id"),
        "status": data.get("status") or data.get("result") or row.get("outcome"),
        "risk_score": agent_view.get("risk_score"),
        "labels": agent_view.get("labels", []),
        "summary": _protocol_summary(event_type, data),
    }


def _protocol_direction(event_type: str) -> str:
    if event_type.endswith(".requested"):
        return "operator_to_utm"
    if event_type.endswith(".approved") or event_type.endswith(".rejected"):
        return "approver_to_utm"
    if event_type.startswith("edge_device."):
        return "edge_to_utm"
    if event_type == "edge_work.acknowledged":
        return "edge_to_utm_ack"
    return "service_internal"


def _protocol_transport(event_type: str, data: dict[str, Any]) -> str:
    if event_type == "edge_work.acknowledged":
        return "REST_JSON_ACK"
    if event_type.startswith("edge_device."):
        return "REST_JSON_EDGE"
    if event_type.startswith("command."):
        return "REST_JSON_TO_MAVLINK_COMMAND"
    if event_type.startswith("mission_upload."):
        return "REST_JSON_TO_MAVLINK_MISSION"
    return "REST_JSON"


def _protocol_message_type(event_type: str, data: dict[str, Any]) -> str:
    if event_type.startswith("command."):
        command = data.get("mavlink_command", {}) if isinstance(data.get("mavlink_command"), dict) else {}
        return str(command.get("message_name") or "COMMAND_LONG")
    if event_type.startswith("mission_upload."):
        return "MISSION_ITEM_INT"
    if event_type == "edge_work.acknowledged":
        return "WORK_ACK"
    if event_type == "edge_device.registered":
        return "EDGE_REGISTER"
    if event_type == "edge_device.heartbeat":
        return "EDGE_HEARTBEAT"
    return event_type.upper().replace(".", "_")


def _protocol_summary(event_type: str, data: dict[str, Any]) -> str:
    if event_type.startswith("command."):
        return f"{event_type} {data.get('command_type', '-')} for {data.get('asset_id', '-')}"
    if event_type.startswith("mission_upload."):
        count = len(data.get("mavlink_items", [])) if isinstance(data.get("mavlink_items"), list) else 0
        return f"{event_type} {data.get('mission_id', '-')} for {data.get('asset_id', '-')} items={count}"
    if event_type.startswith("edge_device."):
        return f"{event_type} {data.get('edge_id', '-')} status={data.get('status', '-')}"
    if event_type == "edge_work.acknowledged":
        return f"ack {data.get('object_type', '-')}:{data.get('object_id', '-')} by {data.get('edge_id', '-')} result={data.get('result', '-')}"
    return event_type
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
