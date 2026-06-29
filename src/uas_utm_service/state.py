from __future__ import annotations

import json
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
from dah_harness.tactical_emulator import (
    ALLOWED_FAULT_TYPES,
    TacticalEmulatorRuntime,
    fault_severity,
    recommended_response,
    tactical_alert_from_fault,
)
from dah_harness.protocol_monitor import (
    AlertEvent,
    LinkState,
    MockMavlinkAdapter,
    TacticalMessage,
    command_from_queue,
    protocol_monitor_snapshot,
    telemetry_from_frame,
)

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
        self.fault_events: list[dict[str, Any]] = []
        self.tactical_emulator = TacticalEmulatorRuntime()
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

    def deregister_edge_device(self, edge_id: str) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.deregister(edge_id)

    def clear_edge_devices(self) -> dict[str, Any]:
        with self._lock:
            return self.edge_registry.clear_all()

    def service_status_payload(self) -> dict[str, Any]:
        edge_payload = self.edge_devices_payload()
        alerts = self.alerts_payload(limit=20)
        chain = self.chain_payload()
        component_status = {item["id"]: item for item in chain["nodes"]}
        uav_count = sum(1 for item in edge_payload["edge_devices"] if "uav" in str(item.get("device_type", "")).lower())
        ugv_count = sum(1 for item in edge_payload["edge_devices"] if "ugv" in str(item.get("device_type", "")).lower())
        statuses = [
            _service_status("dah-uav-sim", "UAV Simulator", "uav_mock_or_sitl_ready", "normal" if uav_count else "degraded", False, "REAL UAS INTEGRATION POSSIBLE / MOCK MODE", {"registered_edges": uav_count}),
            _service_status("dah-ugv-sim", "UGV Simulator", "ugv_mock_telemetry", "normal" if ugv_count else "degraded", False, "REAL UGV INTEGRATION POSSIBLE / MOCK MODE", {"registered_edges": ugv_count}),
            _service_status("dah-gcs", "GCS / Ground Gateway", "telemetry_ingest_command_queue_mission_upload", "normal", False, "LOCAL GCS/UTM SERVICE", {"commands": len(self.command_queue), "mission_uploads": len(self.mission_upload_queue)}),
            _service_status("dah-mavlink-gateway", "C2 Data Link", "mavlink_udp_gateway", component_status.get("c2_link", {}).get("status", "normal"), False, "REAL MAVLINK-CAPABLE / LOCAL MOCK", component_status.get("c2_link", {}).get("metrics", {})),
            _service_status("dah-tactical-router", "Tactical Router", "virtual_tactical_router_tips", component_status.get("router", {}).get("status", "normal"), True, "EMULATED / NOT REAL MILITARY SYSTEM", component_status.get("router", {}).get("metrics", {})),
            _service_status("dah-tmmr-emulator", "TMMR Emulator", "tmmr_queue_emulator", component_status.get("tmmr", {}).get("status", "normal"), True, "EMULATED / NOT REAL MILITARY SYSTEM", component_status.get("tmmr", {}).get("metrics", {})),
            _service_status("dah-ticn-emulator", "TICN-like Network", "route_metric_emulator", component_status.get("ticn", {}).get("status", "normal"), True, "EMULATED / NOT REAL MILITARY SYSTEM", component_status.get("ticn", {}).get("metrics", {})),
            _service_status("dah-upper-c2", "Upper C2/BMS", "upper_c2_bms_simulator", component_status.get("upper_c2", {}).get("status", "normal"), True, "EMULATED / NOT REAL MILITARY SYSTEM; VIA GCS ONLY", component_status.get("upper_c2", {}).get("metrics", {})),
            _service_status("dah-defense-agent", "Defense Agent", "rule_based_detection_response", "critical" if alerts["critical_count"] else "degraded" if alerts["alert_count"] else "normal", False, "LOCAL DEFENSE MONITOR / DRY-RUN RESPONSE", {"alerts": alerts["alert_count"], "critical_alerts": alerts["critical_count"]}),
            _service_status("dah-telemetry-collector", "Telemetry Collector", "telemetry_command_fault_audit_log", "normal", False, "LOCAL JSONL LOG COLLECTION", {"storage": "jsonl", "audit_events": len(self.audit_payload(20).get("audit", []))}),
        ]
        return {
            "schema_version": "dah-service-status.v1",
            "service_statuses": statuses,
            "count": len(statuses),
            "docker_service_names": [item["service_id"] for item in statuses],
            "safety_boundary": "Tactical Router, TMMR, TICN-like Network, and Upper C2/BMS are emulator roles only.",
        }
    def scenario_packages_payload(self) -> dict[str, Any]:
        scenario_dir = _first_existing_path([Path("scenarios/dah_training"), self.scenario_path.parent / "dah_training"])
        output_dir = Path("output/scenario-packages")
        scenarios = []
        for path in sorted(scenario_dir.glob("*.json")) if scenario_dir.exists() else []:
            raw = _read_json_file(path)
            intent = raw.get("scenario_intent", {}) if isinstance(raw.get("scenario_intent", {}), dict) else {}
            scenarios.append(
                {
                    "scenario_name": raw.get("name", path.stem),
                    "scenario_file": _slash(path),
                    "fault_profile": intent.get("fault_profile", "baseline"),
                    "training_goal": intent.get("training_goal", "DAH local training scenario"),
                    "expected_logs": intent.get("expected_logs", []),
                    "validate_command": f"PYTHONPATH=src python -m uas_utm.scenario_report --scenario {_slash(path)} --markdown-output output/reports/{path.stem}.md",
                    "package_command": f"PYTHONPATH=src python -m uas_utm.scenario_package --scenario {_slash(path)} --output-dir {_slash(output_dir)}",
                }
            )
        index_path = output_dir / "index.json"
        index_payload = _read_json_file(index_path) if index_path.exists() else {}
        return {
            "schema_version": "dah-scenario-packages.v1",
            "scenario_dir": _slash(scenario_dir),
            "output_dir": _slash(output_dir),
            "count": len(scenarios),
            "scenarios": scenarios,
            "batch_command": f"PYTHONPATH=src python -m uas_utm.scenario_batch --scenario-dir {_slash(scenario_dir)} --output-dir {_slash(output_dir)}",
            "briefing_command": f"PYTHONPATH=src python -m uas_utm.scenario_briefing --index {_slash(index_path)}",
            "index_available": index_path.exists(),
            "index_path": _slash(index_path),
            "last_index": index_payload if index_payload else None,
            "docs": ["docs/scenarios.md", "docs/vulnerabilities.md", "docs/docker_desktop_runbook.md"],
            "safety_boundary": "Scenario packaging exports local reports and baseline evidence only; no real tactical network, wireless, or actuator command is executed.",
        }
    def dashboard_payload(self) -> dict[str, Any]:
        edge_payload = self.edge_devices_payload()
        chain = self.chain_payload()
        alerts = self.alerts_payload(limit=20)
        service_status = self.service_status_payload()
        cards = [
            _status_card(item["label"], item["status"], f"{item['service_id']} / {item['role']}", "emulated" if item["emulated"] else "real_or_mock")
            for item in service_status["service_statuses"]
        ]
        return {
            "schema_version": "dah-gcs-dashboard.v1",
            "title": "DAH UAS/UGV Tactical Chain Dashboard",
            "scope": {
                "real_implementable": ["UAS/UGV telemetry ingest", "MAVLink-compatible parsing", "GCS approval queue", "audit logging"],
                "emulated_only": ["TMMR role", "TICN-like network role", "Upper C2/BMS role"],
                "safety_boundary": "Fault injection is local simulation only; no real tactical network, wireless attack, or actuator command is executed.",
            },
            "cards": cards,
            "chain": chain,
            "alerts": alerts,
            "fault_allowlist": sorted(ALLOWED_FAULT_TYPES),
            "mavlink_mode": "REAL MAVLINK-CAPABLE / MOCK MODE",
            "service_statuses": service_status["service_statuses"],
            "docker_service_names": service_status["docker_service_names"],
        }

    def tactical_emulator_payload(self) -> dict[str, Any]:
        return self.tactical_emulator.snapshot()

    def chain_payload(self) -> dict[str, Any]:
        emulator = self.tactical_emulator.snapshot()
        component_by_id = {item["component_id"]: item for item in emulator["components"]}
        nodes = []
        for component_id in ["assets", "c2_link", "gcs", "router", "tmmr", "ticn", "upper_c2"]:
            component = component_by_id[component_id]
            nodes.append(
                _chain_node(
                    component["component_id"],
                    component["label"],
                    component["status"],
                    component["boundary"],
                    metrics=component.get("metrics", {}),
                    simulated=component.get("simulated", True),
                    role=component.get("role"),
                )
            )
        links = [
            {
                "from": link["source"],
                "to": link["target"],
                "status": link["status"],
                "latency_ms": link["latency_ms"],
                "packet_loss_pct": link["packet_loss_pct"],
                "simulated": link["simulated"],
                "boundary": link["boundary"],
                "transport": link["transport"],
            }
            for link in emulator["links"]
        ]
        return {
            "schema_version": "dah-tactical-chain.v1",
            "nodes": nodes,
            "links": links,
            "overall_status": emulator["overall_status"],
            "emulator": emulator,
        }

    def alerts_payload(self, limit: int = 50) -> dict[str, Any]:
        fault_events = self.tactical_emulator.fault_events[-max(1, limit) :]
        alerts = [tactical_alert_from_fault(row) for row in fault_events]
        return {
            "schema_version": "dah-alert-events.v1",
            "alerts": alerts,
            "alert_count": len(alerts),
            "critical_count": sum(1 for item in alerts if item["severity"] == "critical"),
            "safety_scope": "local Docker simulation and defensive monitoring only",
        }

    def protocol_monitor_payload(self, requested_time_s: int | None = None, limit: int = 25) -> dict[str, Any]:
        live = self.live_snapshot(requested_time_s)
        asset_kinds = self._asset_kind_lookup()
        telemetry_rows = []
        for frame in (live.get("external_frames") or [])[-limit:]:
            telemetry_rows.append(telemetry_from_frame(frame, asset_kind=asset_kinds.get(str(frame.get("asset_id")), "unknown")))
        if not telemetry_rows:
            for frame in (live.get("frames") or [])[-limit:]:
                telemetry_rows.append(telemetry_from_frame(frame, asset_kind=asset_kinds.get(str(frame.get("asset_id")), "unknown")))
        with self._lock:
            command_rows = [command_from_queue(command) for command in list(self.command_queue.values())[-limit:]]
        chain = self.chain_payload()
        emulator = chain["emulator"]
        links = [
            LinkState(
                link_id=f"{link['source']}->{link['target']}",
                source=link["source"],
                target=link["target"],
                transport=link["transport"],
                status=link["status"],
                latency_ms=link["latency_ms"],
                packet_loss_pct=link["packet_loss_pct"],
                simulated=link["simulated"],
                boundary=link["boundary"],
            )
            for link in emulator["links"]
        ]
        tactical_messages = [
            TacticalMessage(
                message_id=f"tactical-{item['component_id']}",
                timestamp_utc=emulator["generated_at_utc"],
                source=item["component_id"],
                destination=emulator["components"][index + 1]["component_id"] if index + 1 < len(emulator["components"]) else "terminal",
                message_type="COMPONENT_STATE",
                layer="tactical_emulator" if item["simulated"] else "gcs_link",
                priority=2 if item["status"] != "normal" else 4,
                payload={"status": item["status"], "metrics": item.get("metrics", {}), "boundary": item["boundary"]},
                simulated=item["simulated"],
            )
            for index, item in enumerate(emulator["components"])
        ]
        alerts = [
            AlertEvent(
                alert_id=str(row.get("alert_id")),
                timestamp_utc=str(row.get("timestamp_utc") or _now()),
                severity=str(row.get("severity", "warning")),
                category=str(row.get("category", "simulated_tactical_fault")),
                title=str(row.get("title", "unknown")),
                target=row.get("target"),
                recommended_response=str(row.get("recommended_response", "Review simulated event.")),
                source_event_id=str(row.get("alert_id")),
                simulation_only=True,
            )
            for row in self.alerts_payload(limit=limit)["alerts"]
        ]
        return protocol_monitor_snapshot(
            telemetry=telemetry_rows,
            commands=command_rows,
            tactical_messages=tactical_messages,
            links=links,
            alerts=alerts,
            adapter_status=MockMavlinkAdapter().status(),
        )

    def inject_fault(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        if not isinstance(payload, dict):
            raise ValueError("fault payload must be an object")
        fault_type = _required_str(payload, "fault_type")
        if fault_type not in ALLOWED_FAULT_TYPES:
            raise ValueError(f"fault_type is not allowlisted:{fault_type}")
        event = self.tactical_emulator.apply_fault(
            fault_type,
            requested_by=str(payload.get("requested_by", "dashboard-operator")),
            target=payload.get("target"),
            parameters=payload.get("parameters", {}) if isinstance(payload.get("parameters", {}), dict) else {},
        )
        event_payload = event.to_payload()
        with self._lock:
            self.fault_events.append(event_payload)
            self._audit("fault.injected", event_payload)
        return {
            "accepted": True,
            "fault": event_payload,
            "alert": tactical_alert_from_fault(event),
            "chain": self.chain_payload(),
        }

    def _component_status(self, component: str) -> str:
        return self.tactical_emulator.component_status(component)
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
        frame_key = f"{normalized['source_id']}:{asset_id}"
        with self._lock:
            self.external_frames[frame_key] = normalized
            external_asset_count = len({str(frame.get("asset_id")) for frame in self.external_frames.values()})
        return {
            "accepted": True,
            "asset_id": asset_id,
            "source_id": normalized["source_id"],
            "frame_key": frame_key,
            "external_frame_count": len(self.external_frames),
            "external_asset_count": external_asset_count,
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

    def _asset_kind_lookup(self) -> dict[str, str]:
        lookup = {}
        for asset in self.scenario.assets:
            platform = str(getattr(asset, "platform_class", "")).lower()
            role = str(getattr(asset, "role", "")).lower()
            asset_id = str(getattr(asset, "id", ""))
            if "ugv" in platform or "ground" in platform or "ground" in role:
                lookup[asset_id] = "UGV"
            elif asset_id:
                lookup[asset_id] = "UAV"
        return lookup

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
        asset_ids.update(str(frame.get("asset_id")) for frame in self.external_frames.values() if frame.get("asset_id"))
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



def _first_existing_path(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _slash(path: Path) -> str:
    return str(path).replace("\\", "/")


def _service_status(
    service_id: str,
    label: str,
    role: str,
    status: str,
    emulated: bool,
    boundary: str,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "service_id": service_id,
        "docker_service_name": service_id,
        "container_name": service_id,
        "label": label,
        "role": role,
        "status": status,
        "emulated": emulated,
        "boundary": boundary,
        "health_url": "/health" if service_id != "dah-gcs" else "/api/health",
        "status_url": "/status" if service_id != "dah-gcs" else "/api/dashboard",
        "metrics": metrics or {},
    }
def _status_card(label: str, status: str, detail: str, mode: str) -> dict[str, Any]:
    return {"label": label, "status": status, "detail": detail, "mode": mode}


def _fleet_status(devices: list[dict[str, Any]]) -> str:
    if not devices:
        return "degraded"
    statuses = {str(item.get("status", "unknown")).lower() for item in devices}
    if "critical" in statuses or "offline" in statuses:
        return "critical"
    if "degraded" in statuses or "unknown" in statuses:
        return "degraded"
    return "normal"


def _chain_node(
    node_id: str,
    label: str,
    status: str,
    boundary: str,
    metrics: dict[str, Any] | None = None,
    simulated: bool = True,
    role: str | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "status": status,
        "boundary": boundary,
        "metrics": metrics or {},
        "simulated": simulated,
        "role": role,
    }


def _worst_status(statuses: list[str]) -> str:
    if "critical" in statuses:
        return "critical"
    if "degraded" in statuses:
        return "degraded"
    return "normal"


def _legacy_fault_severity(fault_type: str) -> str:
    if fault_type in {"tmmr_queue_overflow", "c2_link_packet_loss", "upper_c2_command_mismatch"}:
        return "critical"
    return "warning"


def _legacy_default_fault_target(fault_type: str) -> str:
    if fault_type.startswith("tmmr"):
        return "tmmr-emulator"
    if fault_type.startswith("ticn"):
        return "ticn-like-network"
    if fault_type.startswith("upper_c2"):
        return "upper-c2-bms-sim"
    if fault_type.startswith("c2"):
        return "c2-data-link"
    return "mavlink-adapter"


def _legacy_alert_from_fault(fault: dict[str, Any]) -> dict[str, Any]:
    fault_type = str(fault.get("fault_type", "unknown"))
    return {
        "alert_id": fault.get("fault_id"),
        "timestamp_utc": fault.get("created_at"),
        "severity": fault.get("severity", fault_severity(fault_type)),
        "category": "simulated_fault",
        "title": fault_type.replace("_", " ").title(),
        "target": fault.get("target"),
        "status": "open",
        "recommended_response": recommended_response(fault_type),
        "simulation_only": True,
    }


def _legacyrecommended_response(fault_type: str) -> str:
    mapping = {
        "mavlink_plaintext_warning": "Flag unauthenticated telemetry, preserve packets, and require signed/encrypted transport in the next profile.",
        "mission_count_reset_attempt": "Hold mission upload approval, compare mission sequence counters, and request operator confirmation.",
        "c2_link_delay": "Mark C2 link degraded and prefer local edge safety policy until delay clears.",
        "c2_link_packet_loss": "Switch to degraded-link playbook and stop non-essential work dispatch.",
        "tmmr_queue_overflow": "Throttle low-priority tactical messages and preserve queue metrics for analysis.",
        "ticn_route_metric_change": "Freeze route decision baseline and compare route metric deltas against allowlisted changes.",
        "upper_c2_command_mismatch": "Require dual approval before any command leaves the GCS queue.",
    }
    return mapping.get(fault_type, "Review simulated event and keep real command execution disabled.")

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
