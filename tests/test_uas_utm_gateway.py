from __future__ import annotations

import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uas_utm_gateway.bidirectional_gateway import BidirectionalMavlinkGateway, Endpoint
from uas_utm_gateway.mavlink_builder import CRC_EXTRA, MESSAGE_IDS, build_command_long_frames, build_mavlink2_frame, x25_checksum
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

    def test_parse_mavlink2_command_ack(self) -> None:
        payload = struct.pack("<HB", 193, 0)
        frame = _mavlink2_frame(seq=8, system_id=31, component_id=1, message_id=77, payload=payload)

        parsed = parse_datagram(frame)

        self.assertEqual(parsed[0].message_name, "COMMAND_ACK")
        self.assertEqual(parsed[0].fields["command"], 193)
        self.assertEqual(parsed[0].fields["result"], 0)


    def test_mavlink2_frame_uses_crc_extra_checksum(self) -> None:
        payload = struct.pack("<HB", 193, 0)

        frame = build_mavlink2_frame(seq=8, system_id=31, component_id=1, message_id=77, payload=payload)
        expected_crc = x25_checksum(frame[1:10] + payload + bytes([CRC_EXTRA[77]]))
        actual_crc = struct.unpack_from("<H", frame, 10 + len(payload))[0]

        self.assertEqual(actual_crc, expected_crc)
        self.assertNotEqual(actual_crc, 0)

    def test_mavlink2_frame_can_be_signed(self) -> None:
        payload = struct.pack("<HB", 193, 0)
        key = bytes(range(32))

        frame = build_mavlink2_frame(
            seq=8,
            system_id=31,
            component_id=1,
            message_id=MESSAGE_IDS["COMMAND_ACK"],
            payload=payload,
            signing_key=key,
            signing_link_id=7,
            signing_timestamp=42,
        )
        unsigned_packet = frame[:-13]
        signature_block = frame[-13:]
        expected_prefix = bytes([7]) + (42).to_bytes(6, "little")
        expected_signature = hashlib.sha256(key + unsigned_packet + expected_prefix).digest()[:6]

        self.assertEqual(frame[2], 0x01)
        self.assertEqual(signature_block[:7], expected_prefix)
        self.assertEqual(signature_block[7:], expected_signature)
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

    def test_build_command_long_outbound_frame(self) -> None:
        command = {
            "command_id": "cmd-1",
            "asset_id": "small-dronebot-01",
            "command_type": "hold_position",
            "mavlink_command": {
                "command": "MAV_CMD_DO_PAUSE_CONTINUE",
                "params": {"param1": 0},
            },
        }

        frames = build_command_long_frames(command=command, system_id=31, component_id=1, sequence=9)
        parsed = parse_datagram(frames[0].frame)

        self.assertEqual(frames[0].message_name, "COMMAND_LONG")
        self.assertEqual(frames[0].command_id, 193)
        self.assertEqual(parsed[0].message_name, "COMMAND_LONG")
        self.assertEqual(parsed[0].system_id, 255)

    def test_bidirectional_gateway_records_command_ack(self) -> None:
        gateway = BidirectionalMavlinkGateway(
            scenario_path=ROOT / "scenarios" / "korea_defense_uas_utm_ops.json",
            service_url="http://127.0.0.1:8080",
            listen_host="127.0.0.1",
            listen_port=0,
        )
        fake_client = _FakeServiceClient()
        fake_sock = _FakeSocket()
        endpoint = Endpoint("127.0.0.1", 14600)
        gateway.client = fake_client
        gateway.endpoint_by_asset_id["small-dronebot-01"] = endpoint
        command = {
            "command_id": "cmd-1",
            "asset_id": "small-dronebot-01",
            "command_type": "hold_position",
            "mavlink_command": {"command": "MAV_CMD_DO_PAUSE_CONTINUE", "params": {}},
        }

        gateway._send_command(fake_sock, command)
        ack_payload = struct.pack("<HB", 193, 0)
        ack_frame = _mavlink2_frame(seq=10, system_id=31, component_id=1, message_id=77, payload=ack_payload)
        gateway.handle_datagram(fake_sock, ack_frame, endpoint)

        self.assertEqual(len(fake_sock.sent), 1)
        self.assertEqual(fake_client.acks[0]["edge_id"], "mavlink-edge-small-dronebot-01")
        self.assertEqual(fake_client.acks[0]["result"], "MAV_RESULT_ACCEPTED")

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


class _FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, datagram: bytes, address: tuple[str, int]) -> None:
        self.sent.append((datagram, address))


class _FakeServiceClient:
    def __init__(self):
        self.acks = []

    def ingest_telemetry(self, message):
        return {"payload": {"accepted": True}}

    def register_edge(self, **kwargs):
        return {"payload": kwargs}

    def ack_edge_work(self, **kwargs):
        self.acks.append(kwargs)
        return {"payload": kwargs}


if __name__ == "__main__":
    unittest.main()