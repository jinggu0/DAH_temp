from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dah_attacks.passive_mavlink_recon import (
    IntelligenceReport,
    _handle_frame,
    classify_pattern,
    confidence_score,
    follow_on_candidates,
    predict_position,
)
from uas_utm_gateway.mavlink_builder import MESSAGE_IDS, build_mavlink2_frame
from uas_utm_gateway.mavlink_parser import ParsedMavlinkFrame, parse_datagram


class PassiveMavlinkReconTests(unittest.TestCase):
    def test_signed_frame_metadata_is_exposed_by_parser(self) -> None:
        payload = struct.pack("<HB", 193, 0)
        frame = build_mavlink2_frame(
            seq=8,
            system_id=31,
            component_id=1,
            message_id=MESSAGE_IDS["COMMAND_ACK"],
            payload=payload,
            signing_key=bytes(range(32)),
            signing_link_id=7,
            signing_timestamp=42,
        )

        parsed = parse_datagram(frame)[0]

        self.assertIsInstance(parsed, ParsedMavlinkFrame)
        self.assertTrue(parsed.signed)
        self.assertTrue(parsed.crc_valid)
        self.assertEqual(parsed.signature_link_id, 7)
        self.assertEqual(parsed.signature_timestamp, 42)

    def test_report_scores_and_maps_follow_on_candidates(self) -> None:
        report = IntelligenceReport()
        for frame in [
            _heartbeat_frame(),
            _position_frame(seq=2, lat=376000000, lon=1271000000, vx=110),
            _position_frame(seq=3, lat=376000100, lon=1271000000, vx=110),
            _sys_status_frame(),
        ]:
            parsed = parse_datagram(frame)[0]
            self.assertIsInstance(parsed, ParsedMavlinkFrame)
            _handle_frame(report, parsed, "172.20.0.10")

        rec = report.assets[31]
        rec["position_history"][0]["received_s"] = 100.0
        rec["position_history"][1]["received_s"] = 101.0

        self.assertGreaterEqual(confidence_score(rec), 0.8)
        self.assertIn("GNSS-DRIFT(S01)", follow_on_candidates(rec, confidence_score(rec)))
        self.assertEqual(classify_pattern(rec), "TRANSIT")
        prediction = predict_position(rec, 60)
        self.assertIsNotNone(prediction)
        self.assertEqual(prediction["horizon_s"], 60)


def _heartbeat_frame() -> bytes:
    payload = struct.pack("<IBBBBB", 0, 2, 0, 0x88, 4, 3)
    return build_mavlink2_frame(seq=1, system_id=31, component_id=1, message_id=0, payload=payload)


def _position_frame(*, seq: int, lat: int, lon: int, vx: int) -> bytes:
    payload = struct.pack(
        "<IiiiihhhH",
        12_000 + seq,
        lat,
        lon,
        90_000,
        90_000,
        vx,
        0,
        0,
        9_000,
    )
    return build_mavlink2_frame(seq=seq, system_id=31, component_id=1, message_id=33, payload=payload)


def _sys_status_frame() -> bytes:
    payload = bytearray(31)
    struct.pack_into("<H", payload, 18, 0)
    struct.pack_into("<H", payload, 20, 0)
    struct.pack_into("<b", payload, 30, 77)
    return build_mavlink2_frame(seq=4, system_id=31, component_id=1, message_id=1, payload=bytes(payload))


if __name__ == "__main__":
    unittest.main()