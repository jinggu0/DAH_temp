from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm_service.protocol import envelope, protocol_profile
from uas_utm_service.state import ServiceState


class UasUtmServiceTests(unittest.TestCase):
    def test_protocol_envelope_has_standard_style_metadata(self) -> None:
        message = envelope(message_type="utm.health", payload={"ok": True})

        self.assertEqual(message["protocol"], "TTA-UAS-UTM-SIM")
        self.assertEqual(message["schema_version"], "1.4")
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


if __name__ == "__main__":
    unittest.main()


