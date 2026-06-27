from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm_service.log_store import redact_sensitive
from uas_utm_service.protocol import envelope, protocol_profile
from uas_utm_service.state import ServiceState


class UasUtmServiceTests(unittest.TestCase):
    def test_protocol_envelope_has_standard_style_metadata(self) -> None:
        message = envelope(message_type="utm.health", payload={"ok": True})

        self.assertEqual(message["protocol"], "TTA-UAS-UTM-SIM")
        self.assertEqual(message["schema_version"], "1.5")
        self.assertEqual(message["message_type"], "utm.health")
        self.assertIn("timestamp_utc", message)
        self.assertEqual(message["payload"], {"ok": True})

    def test_service_state_exposes_summary_and_snapshots(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        summary = state.summary
        snapshot = state.telemetry_snapshot(120)

        self.assertGreaterEqual(summary["asset_count"], 4)
        self.assertIn("mavlink_message_counts", summary)
        self.assertEqual(len(snapshot["frames"]), summary["asset_count"])

    def test_protocol_profile_documents_live_ingest_and_mavlink_mapping(self) -> None:
        profile = protocol_profile()

        self.assertEqual(profile["transport"]["live_push"], "Server-Sent Events over HTTP")
        self.assertIn("utm.telemetry.ingest", profile["normal_operation_messages"])
        self.assertIn("utm.tracks", profile["normal_operation_messages"])
        self.assertIn("utm.operation_profile", profile["normal_operation_messages"])
        self.assertIn("utm.edge.device.register", profile["normal_operation_messages"])
        self.assertIn("utm.edge.work", profile["normal_operation_messages"])
        self.assertIn("utm.baseline.export", profile["normal_operation_messages"])
        self.assertIn("utm.protocol.logs", profile["normal_operation_messages"])
        self.assertIn("utm.runtime.logs", profile["normal_operation_messages"])
        self.assertIn("utm.command.request", profile["normal_operation_messages"])
        self.assertEqual(profile["mavlink_mapping"]["position"], "GLOBAL_POSITION_INT")
        self.assertEqual(profile["mavlink_mapping"]["command"], "COMMAND_LONG")

    def test_ingested_external_telemetry_appears_in_live_snapshot(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        result = state.ingest_telemetry(
            {
                "payload": {
                    "asset_id": "external-uas-01",
                    "time_s": 12,
                    "position": [10, 20, 90],
                    "status": "external-live",
                    "battery_wh": 100,
                    "source": "mavlink-udp-adapter",
                }
            }
        )
        snapshot = state.live_snapshot(12)

        self.assertTrue(result["accepted"])
        self.assertEqual(snapshot["mode"], "hybrid")
        self.assertEqual(snapshot["external_frames"][0]["asset_id"], "external-uas-01")

    def test_track_fusion_merges_simulation_and_external_sources(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        state.ingest_telemetry(
            {
                "payload": {
                    "asset_id": "small-dronebot-01",
                    "time_s": 120,
                    "position": [205, -240, 99],
                    "velocity_mps": [10, 0, 0],
                    "status": "mavlink-live",
                    "source": "mavlink-udp-adapter",
                    "source_authority": "ROKA UTM Cell",
                    "track_confidence": 0.94,
                }
            }
        )
        tracks = state.tracks_payload(120)
        fused = next(track for track in tracks["tracks"] if track["asset_id"] == "small-dronebot-01")

        self.assertEqual(tracks["mode"], "fused")
        self.assertEqual(fused["primary_source_id"], "mavlink-udp-adapter")
        self.assertEqual(fused["source_count"], 2)
        self.assertGreaterEqual(fused["confidence"], 0.94)

    def test_operation_profile_exposes_public_contractor_style_domains(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        profile = state.operation_profile()
        domains = {row["domain"] for row in profile["domains"]}
        roles = {row["role"] for row in profile["roles"]}

        self.assertIn("platform", domains)
        self.assertIn("mission_payload", domains)
        self.assertIn("c2_ground_control", domains)
        self.assertIn("datalink", domains)
        self.assertIn("approver", roles)


    def test_edge_device_registers_polls_work_and_acknowledges(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        device = state.register_edge_device(
            {
                "payload": {
                    "edge_id": "edge-dronebot-01",
                    "device_type": "uav_edge",
                    "asset_ids": ["small-dronebot-01"],
                    "authority": "ROKA UTM Cell",
                    "capabilities": ["telemetry_ingest", "approved_work_poll", "ack_work"],
                }
            }
        )
        heartbeat = state.heartbeat_edge_device(
            {
                "payload": {
                    "edge_id": "edge-dronebot-01",
                    "status": "online",
                    "cpu_load": 0.2,
                    "battery_wh": 700,
                    "link_quality": 0.95,
                }
            }
        )
        command = state.request_command(
            {"payload": {"asset_id": "small-dronebot-01", "command_type": "hold_position"}}
        )
        approved = state.approve_command({"payload": {"command_id": command["command_id"], "approver": "lead"}})
        work = state.edge_work_payload("edge-dronebot-01")
        ack = state.ack_edge_work(
            {
                "payload": {
                    "edge_id": "edge-dronebot-01",
                    "object_type": "command",
                    "object_id": approved["command_id"],
                    "result": "received_by_edge",
                }
            }
        )

        self.assertEqual(device["egress_policy"], "approved_queue_only")
        self.assertEqual(heartbeat["status"], "online")
        self.assertEqual(len(work["commands"]), 1)
        self.assertEqual(work["safety_interlock"], "local_edge_must_validate_before_actuation")
        self.assertEqual(ack["object_type"], "command")


    def test_baseline_export_contains_uav_ugv_normal_operation_report(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        export = state.baseline_export_payload(limit=20)
        asset_ids = {asset["id"] for asset in export["scenario"]["assets"]}

        self.assertIn("ground-convoy-01", asset_ids)
        self.assertIn("summary", export)
        self.assertIn("telemetry_jsonl", export)
        self.assertLessEqual(len(export["telemetry_jsonl"]), 20)
        self.assertIn("normal_operation_only", export["baseline_notes"])
    def test_command_request_requires_approval_before_gateway_dispatch(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        command = state.request_command(
            {
                "payload": {
                    "asset_id": "small-dronebot-01",
                    "command_type": "hold_position",
                    "requested_by": "operator-a",
                }
            }
        )
        pending = state.commands_payload(status="pending_approval")
        approved = state.approve_command({"payload": {"command_id": command["command_id"], "approver": "lead"}})
        dispatch = state.commands_payload(status="approved_for_gateway")

        self.assertEqual(command["status"], "pending_approval")
        self.assertEqual(len(pending["commands"]), 1)
        self.assertEqual(approved["status"], "approved_for_gateway")
        self.assertEqual(dispatch["commands"][0]["mavlink_command"]["message_name"], "COMMAND_LONG")

    def test_mission_upload_queue_renders_mission_item_int_after_approval(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        upload = state.request_mission_upload(
            {"payload": {"mission_id": "dronebot-local-recon", "requested_by": "operator-a"}}
        )
        approved = state.approve_mission_upload({"payload": {"upload_id": upload["upload_id"], "approver": "lead"}})
        dispatch = state.mission_uploads_payload(status="approved_for_gateway")

        self.assertEqual(upload["status"], "pending_approval")
        self.assertEqual(approved["status"], "approved_for_gateway")
        self.assertTrue(dispatch["mission_uploads"][0]["mavlink_items"])
        self.assertEqual(dispatch["mission_uploads"][0]["mavlink_items"][0]["message_name"], "MISSION_ITEM_INT")

    def test_audit_log_records_command_and_mission_flow(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        command = state.request_command(
            {"payload": {"asset_id": "small-dronebot-01", "command_type": "return_to_launch"}}
        )
        state.reject_command({"payload": {"command_id": command["command_id"], "reason": "training hold"}})
        state.request_mission_upload({"payload": {"mission_id": "dronebot-local-recon"}})

        audit = state.audit_payload()
        events = [row["event_type"] for row in audit["audit"]]

        self.assertIn("command.requested", events)
        self.assertIn("command.rejected", events)
        self.assertIn("mission_upload.requested", events)


    def test_audit_log_is_persisted_with_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))

            command = state.request_command(
                {"payload": {"asset_id": "small-dronebot-01", "command_type": "hold_position", "requested_by": "operator-a"}}
            )
            state.approve_command({"payload": {"command_id": command["command_id"], "approver": "lead"}})

            audit = state.audit_payload(limit=10)
            status = state.logs_status_payload()
            verify = state.verify_logs_payload()

            self.assertEqual(status["event_count"], 2)
            self.assertTrue(verify["valid"])
            self.assertEqual(verify["checked_count"], 2)
            self.assertTrue((Path(tmpdir) / "audit.jsonl").exists())
            self.assertEqual(audit["audit"][-1]["integrity"]["previous_hash"], audit["audit"][0]["integrity"]["event_hash"])

    def test_audit_log_redacts_sensitive_fields_before_storage(self) -> None:
        redacted = redact_sensitive(
            {
                "edge_id": "edge-1",
                "api_token": "plain-token",
                "nested": {"signing_key_hex": "secret-key"},
            }
        )

        self.assertEqual(redacted["api_token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["signing_key_hex"], "[REDACTED]")

    def test_baseline_export_includes_log_storage_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))
            state.request_command({"payload": {"asset_id": "small-dronebot-01", "command_type": "hold_position"}})

            export = state.baseline_export_payload(limit=20)

            self.assertIn("log_storage", export)
            self.assertIn("log_integrity", export)
            self.assertTrue(export["log_integrity"]["valid"])

    def test_agent_log_view_exposes_features_labels_and_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))
            command = state.request_command(
                {
                    "payload": {
                        "asset_id": "small-dronebot-01",
                        "command_type": "hold_position",
                        "requested_by": "operator-a",
                        "priority": 2,
                    }
                }
            )
            state.approve_command({"payload": {"command_id": command["command_id"], "approver": "lead"}})

            view = state.agent_logs_payload(limit=10)
            observation = view["observations"][-1]

            self.assertEqual(view["schema_version"], "uas-utm-agent-observation.v1")
            self.assertEqual(observation["phase"], "c2_command_workflow")
            self.assertIn("blue_defense", observation["perspectives"])
            self.assertIn("red_scenario_planning", observation["perspectives"])
            self.assertIn("control_plane", observation["labels"])
            self.assertTrue(observation["features"]["is_command"])
            self.assertGreater(observation["risk_score"], 0.2)
            self.assertTrue(observation["defense_questions"])
            self.assertIn("Simulation planning metadata", observation["safety_note"])

    def test_agent_log_view_can_filter_heartbeat_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))
            state.register_edge_device(
                {
                    "payload": {
                        "edge_id": "edge-dronebot-01",
                        "device_type": "uav_edge",
                        "asset_ids": ["small-dronebot-01"],
                    }
                }
            )
            state.heartbeat_edge_device({"payload": {"edge_id": "edge-dronebot-01", "status": "online"}})
            command = state.request_command({"payload": {"asset_id": "small-dronebot-01", "command_type": "hold_position"}})
            state.approve_command({"payload": {"command_id": command["command_id"], "approver": "lead"}})

            view = state.agent_logs_payload(limit=10, include_heartbeat=False)
            event_types = [item["event_type"] for item in view["observations"]]
            edge = state.audit_payload(event_type="edge_device.heartbeat")["audit"][0]

            self.assertNotIn("edge_device.heartbeat", event_types)
            self.assertIn("command.approved", event_types)
            self.assertEqual(edge["object_type"], "edge_device")

    def test_runtime_logs_payload_exposes_recent_service_lines(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        state.record_runtime_log(source="uas-utm-service", message="127.0.0.1 - GET /api/health HTTP/1.1 200 -")

        payload = state.runtime_logs_payload(limit=5)

        self.assertEqual(payload["schema_version"], "uas-utm-runtime-log.v1")
        self.assertEqual(payload["count"], 1)
        self.assertIn("/api/health", payload["runtime_logs"][0]["message"])
    def test_protocol_logs_payload_shapes_audit_as_protocol_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))
            state.register_edge_device(
                {
                    "payload": {
                        "edge_id": "edge-dashboard-ugv-01",
                        "device_type": "ugv_edge",
                        "asset_ids": ["ground-convoy-01"],
                    }
                }
            )
            state.heartbeat_edge_device({"payload": {"edge_id": "edge-dashboard-ugv-01", "status": "online"}})
            command = state.request_command(
                {"payload": {"asset_id": "ground-convoy-01", "command_type": "hold_position", "requested_by": "operator-a"}}
            )
            state.approve_command({"payload": {"command_id": command["command_id"], "approver": "lead"}})

            view = state.protocol_logs_payload(limit=10, include_heartbeat=False)
            event_types = [item["event_type"] for item in view["protocol_logs"]]
            approved = next(item for item in view["protocol_logs"] if item["event_type"] == "command.approved")

            self.assertEqual(view["schema_version"], "uas-utm-protocol-log.v1")
            self.assertNotIn("edge_device.heartbeat", event_types)
            self.assertIn("command.requested", event_types)
            self.assertEqual(approved["transport"], "REST_JSON_TO_MAVLINK_COMMAND")
            self.assertEqual(approved["message_type"], "COMMAND_LONG")
            self.assertEqual(approved["direction"], "approver_to_utm")
            self.assertEqual(approved["asset_id"], "ground-convoy-01")
    def test_dashboard_payload_exposes_dah_cards_and_boundaries(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        payload = state.dashboard_payload()

        self.assertEqual(payload["schema_version"], "dah-gcs-dashboard.v1")
        self.assertEqual(len(payload["cards"]), 6)
        self.assertIn("TMMR Emulator", [card["label"] for card in payload["cards"]])
        self.assertIn("TICN-like Network", [card["label"] for card in payload["cards"]])
        self.assertIn("TMMR role", payload["scope"]["emulated_only"])

    def test_allowlisted_fault_injection_creates_alert_and_degrades_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))

            result = state.inject_fault({"payload": {"fault_type": "tmmr_queue_overflow", "requested_by": "operator-a"}})
            alerts = state.alerts_payload()
            chain = state.chain_payload()

            self.assertTrue(result["accepted"])
            self.assertEqual(alerts["critical_count"], 1)
            self.assertEqual(chain["overall_status"], "critical")
            self.assertTrue(result["fault"]["simulation_only"])

    def test_fault_injection_rejects_non_allowlisted_faults(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        with self.assertRaises(ValueError):
            state.inject_fault({"payload": {"fault_type": "real_network_attack"}})
    def test_baseline_export_includes_agent_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json", log_dir=Path(tmpdir))
            state.request_command({"payload": {"asset_id": "small-dronebot-01", "command_type": "hold_position"}})

            export = state.baseline_export_payload(limit=20)

            self.assertIn("agent_observations", export)
            self.assertEqual(export["agent_observations"][0]["phase"], "c2_command_workflow")
            self.assertIn("features", export["agent_observations"][0])

if __name__ == "__main__":
    unittest.main()
