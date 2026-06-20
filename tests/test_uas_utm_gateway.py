from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm_gateway.mavlink_parser import ParsedMavlinkFrame, parse_datagram
from uas_utm_gateway.translator import MavlinkTelemetryTranslator, local_position_from_wgs84_int


class UasUtmGatewayTests(unittest.TestCase):
    def test_parse_mavlink2_global_position_int(self) -> None:
        payload = struct.pack(
            "<IiiiihhhH",
            12_000,
            376000100,
            1271000200,
            90_000,
            90_000,
            150,
            -20,
            0,
            9_000,
        )
        frame = _mavlink2_frame(seq=7, system_id=31, component_id=1, message_id=33, payload=payload)

        parsed = parse_datagram(frame)

        self.assertEqual(len(parsed), 1)
        self.assertIsInstance(parsed[0], ParsedMavlinkFrame)
        self.assertEqual(parsed[0].message_name, "GLOBAL_POSITION_INT")
        self.assertEqual(parsed[0].fields["lat"], 376000100)
        self.assertEqual(parsed[0].fields["vx"], 150)

    def test_translator_maps_system_id_to_asset_ingest_payload(self) -> None:
        translator = MavlinkTelemetryTranslator(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")
        frame = ParsedMavlinkFrame(
            version=2,
            sequence=1,
            system_id=31,
            component_id=1,
            message_id=33,
            message_name="GLOBAL_POSITION_INT",
            fields={
                "time_boot_ms": 12_000,
                "lat": 376000100,
                "lon": 1271000200,
                "alt": 90_000,
                "relative_alt": 90_000,
                "vx": 150,
                "vy": -20,
                "vz": -5,
                "hdg": 9_000,
            },
        )

        message = translator.translate(frame)

        self.assertIsNotNone(message)
        self.assertEqual(message["payload"]["asset_id"], "small-dronebot-01")
        self.assertEqual(message["payload"]["time_s"], 12)
        self.assertEqual(message["payload"]["heading_deg"], 90.0)
        self.assertEqual(message["payload"]["source"], "mavlink-udp-gateway")

    def test_json_datagram_passthrough_for_adapter_tests(self) -> None:
        datagram = json.dumps({"payload": {"asset_id": "external", "position": [1, 2, 3]}}).encode("utf-8")
        translator = MavlinkTelemetryTranslator(ROOT / "scenarios" / "korea_defense_uas_utm_ops.json")

        parsed = parse_datagram(datagram)
        message = translator.translate(parsed[0])

        self.assertEqual(message["payload"]["asset_id"], "external")
        self.assertEqual(message["payload"]["source"], "mavlink-json-udp")

    def test_local_position_from_wgs84_int_inverse_mapping(self) -> None:
        x, y, z = local_position_from_wgs84_int(
            lat=376000100,
            lon=1271000200,
            alt_mm=90_000,
            origin_lat_e7=376000000,
            origin_lon_e7=1271000000,
        )

        self.assertAlmostEqual(x, 1.776, places=3)
        self.assertAlmostEqual(y, 1.1132, places=4)
        self.assertEqual(z, 90)


def _mavlink2_frame(
    *,
    seq: int,
    system_id: int,
    component_id: int,
    message_id: int,
    payload: bytes,
) -> bytes:
    header = bytes(
        [
            0xFD,
            len(payload),
            0,
            0,
            seq,
            system_id,
            component_id,
            message_id & 0xFF,
            (message_id >> 8) & 0xFF,
            (message_id >> 16) & 0xFF,
        ]
    )
    return header + payload + b"\x00\x00"


if __name__ == "__main__":
    unittest.main()
