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
        self.assertEqual(message["schema_version"], "1.1")
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
        self.assertEqual(profile["mavlink_mapping"]["position"], "GLOBAL_POSITION_INT")
        self.assertEqual(profile["mavlink_mapping"]["utm_position"], "UTM_GLOBAL_POSITION")

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


if __name__ == "__main__":
    unittest.main()
