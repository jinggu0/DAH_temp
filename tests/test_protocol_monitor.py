from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dah_harness.protocol_monitor import (
    MockMavlinkAdapter,
    VehicleTelemetry,
    command_from_queue,
    protocol_monitor_snapshot,
    telemetry_from_frame,
)
from uas_utm_service.state import ServiceState


class ProtocolMonitorTests(unittest.TestCase):
    def test_vehicle_telemetry_payload_validates_position(self) -> None:
        telemetry = VehicleTelemetry(
            timestamp_utc="2026-06-27T00:00:00+00:00",
            time_s=1,
            asset_id="uav-01",
            asset_kind="UAV",
            protocol="MAVLink2-compatible",
            position=(1.0, 2.0, 80.0),
        )

        payload = telemetry.to_payload()

        self.assertEqual(payload["position"], [1.0, 2.0, 80.0])
        self.assertEqual(payload["raw_message_type"], "GLOBAL_POSITION_INT")

    def test_mock_mavlink_adapter_works_without_pymavlink(self) -> None:
        adapter = MockMavlinkAdapter()

        status = adapter.status().to_payload()
        sample = adapter.sample_telemetry(asset_id="mock-ugv-01", asset_kind="UGV", position=(4.0, 5.0, 0.0)).to_payload()

        self.assertIn(status["mode"], {"mock", "udp_receive_available"})
        self.assertIn("GLOBAL_POSITION_INT", status["receive_messages"])
        self.assertEqual(status["transmit_policy"], "dry_run_only")
        self.assertEqual(sample["asset_kind"], "UGV")

    def test_queue_and_frame_convert_to_protocol_monitor_models(self) -> None:
        command = command_from_queue(
            {
                "command_id": "cmd-1",
                "asset_id": "ground-convoy-01",
                "command_type": "hold_position",
                "status": "pending_approval",
                "requested_by": "operator-a",
            }
        )
        telemetry = telemetry_from_frame(
            {
                "time_s": 10,
                "asset_id": "ground-convoy-01",
                "position": [10, 20, 0],
                "velocity_mps": [1, 0, 0],
                "battery_wh": 900,
                "link_profile": "mavlink_udp",
                "status": "edge-live",
            },
            asset_kind="UGV",
        )
        snapshot = protocol_monitor_snapshot(
            telemetry=[telemetry],
            commands=[command],
            tactical_messages=[],
            links=[],
            alerts=[],
        )

        self.assertEqual(snapshot["schema_version"], "dah-protocol-monitor.v1")
        self.assertEqual(snapshot["telemetry"][0]["asset_kind"], "UGV")
        self.assertTrue(snapshot["commands"][0]["dry_run"])

    def test_service_protocol_monitor_payload_exposes_models(self) -> None:
        state = ServiceState(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        payload = state.protocol_monitor_payload(limit=5)

        self.assertEqual(payload["schema_version"], "dah-protocol-monitor.v1")
        self.assertIn(payload["mavlink_adapter"]["mode"], {"mock", "udp_receive_available"})
        self.assertGreaterEqual(len(payload["tactical_messages"]), 1)
        self.assertGreaterEqual(len(payload["links"]), 1)
        self.assertEqual(payload["mavlink_adapter"]["transmit_policy"], "dry_run_only")


if __name__ == "__main__":
    unittest.main()