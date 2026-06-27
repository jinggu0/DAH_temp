from __future__ import annotations

import argparse
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uas_utm.simulator import load_scenario

from .mavlink_builder import ACK_RESULTS, OutboundMavlinkFrame, build_command_long_frames, build_mission_count_frame, build_mission_item_int_frames
from .mavlink_parser import ParsedMavlinkFrame, parse_datagram
from .service_client import UtmServiceClient
from .translator import MavlinkTelemetryTranslator


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int

    @property
    def socket_address(self) -> tuple[str, int]:
        return self.host, self.port


class BidirectionalMavlinkGateway:
    def __init__(
        self,
        *,
        scenario_path: Path,
        service_url: str,
        listen_host: str,
        listen_port: int,
        poll_interval_s: float = 1.0,
        timeout_s: float = 0.2,
        signing_key: bytes | None = None,
        signing_link_id: int = 0,
    ):
        self.scenario = load_scenario(scenario_path)
        self.translator = MavlinkTelemetryTranslator(scenario_path)
        self.client = UtmServiceClient(service_url, timeout_s=max(timeout_s, 1.0))
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s
        self.asset_by_system_id = {asset.system_id: asset for asset in self.scenario.assets}
        self.asset_by_id = {asset.id: asset for asset in self.scenario.assets}
        self.endpoint_by_asset_id: dict[str, Endpoint] = {}
        self.sent_work_ids: set[tuple[str, str]] = set()
        self.pending_ack: dict[tuple[str, int, int], OutboundMavlinkFrame] = {}
        self.pending_mission_items: dict[tuple[str, int], list[OutboundMavlinkFrame]] = {}
        self.pending_mission_upload: dict[tuple[str, int], OutboundMavlinkFrame] = {}
        self.registered_edges: set[str] = set()
        self.sequence = 0
        self.signing_key = signing_key
        self.signing_link_id = signing_link_id
        self.signing_timestamp = 0

    def serve_forever(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.listen_host, self.listen_port))
        sock.settimeout(self.timeout_s)
        print(f"Bidirectional MAVLink gateway listening on {self.listen_host}:{self.listen_port}")
        print(f"service: {self.client.base_url}")
        last_poll = 0.0
        try:
            while True:
                now = time.monotonic()
                if now - last_poll >= self.poll_interval_s:
                    self.poll_and_send(sock)
                    last_poll = now
                try:
                    datagram, address = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                self.handle_datagram(sock, datagram, Endpoint(address[0], address[1]))
        except KeyboardInterrupt:
            pass
        finally:
            sock.close()

    def handle_datagram(self, sock: socket.socket, datagram: bytes, endpoint: Endpoint) -> None:
        for item in parse_datagram(datagram):
            if isinstance(item, ParsedMavlinkFrame):
                self._remember_endpoint(item, endpoint)
                if item.message_name == "COMMAND_ACK":
                    self._handle_command_ack(item, endpoint)
                    continue
                if item.message_name == "MISSION_REQUEST_INT":
                    self._handle_mission_request_int(sock, item, endpoint)
                    continue
                if item.message_name == "MISSION_ACK":
                    self._handle_mission_ack(item, endpoint)
                    continue
            message = self.translator.translate(item)
            if message is None:
                continue
            response = self.client.ingest_telemetry(message)
            accepted = response.get("payload", {}).get("accepted")
            print(f"{endpoint.host}:{endpoint.port} -> {message['payload']['asset_id']} accepted={accepted}")

    def poll_and_send(self, sock: socket.socket) -> None:
        for command in self.client.get_gateway_commands():
            key = ("command", str(command["command_id"]))
            if key in self.sent_work_ids:
                continue
            self._send_command(sock, command)
            self.sent_work_ids.add(key)
        for upload in self.client.get_gateway_mission_uploads():
            key = ("mission_upload", str(upload["upload_id"]))
            if key in self.sent_work_ids:
                continue
            self._send_mission_upload(sock, upload)
            self.sent_work_ids.add(key)

    def _send_command(self, sock: socket.socket, command: dict[str, Any]) -> None:
        asset = self.asset_by_id.get(str(command["asset_id"]))
        endpoint = self.endpoint_by_asset_id.get(str(command["asset_id"]))
        if asset is None or endpoint is None:
            return
        frames = build_command_long_frames(
            command=command,
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence=self._next_sequence(),
            signing_key=self.signing_key,
            signing_link_id=self.signing_link_id,
            signing_timestamp=self._next_signing_timestamp() if self.signing_key else None,
        )
        self._send_frames(sock, endpoint, frames)

    def _send_mission_upload(self, sock: socket.socket, upload: dict[str, Any]) -> None:
        asset = self.asset_by_id.get(str(upload["asset_id"]))
        endpoint = self.endpoint_by_asset_id.get(str(upload["asset_id"]))
        if asset is None or endpoint is None:
            return
        signing_timestamp = self._next_signing_timestamp() if self.signing_key else None
        frames = build_mission_item_int_frames(
            upload=upload,
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence_start=self._next_sequence(),
            signing_key=self.signing_key,
            signing_link_id=self.signing_link_id,
            signing_timestamp=signing_timestamp,
        )
        count_frame = build_mission_count_frame(
            upload=upload,
            system_id=asset.system_id,
            component_id=asset.component_id,
            sequence=self._next_sequence(),
            signing_key=self.signing_key,
            signing_link_id=self.signing_link_id,
            signing_timestamp=None if signing_timestamp is None else signing_timestamp + len(frames),
        )
        key = (endpoint.host, asset.system_id)
        self.pending_mission_items[key] = frames
        self.pending_mission_upload[key] = count_frame
        self._send_frames(sock, endpoint, [count_frame])

    def _send_frames(self, sock: socket.socket, endpoint: Endpoint, frames: list[OutboundMavlinkFrame]) -> None:
        for frame in frames:
            sock.sendto(frame.frame, endpoint.socket_address)
            if frame.command_id is not None:
                self.pending_ack[(endpoint.host, frame.system_id, frame.command_id)] = frame
            print(f"sent {frame.message_name} {frame.object_type}:{frame.object_id} -> {endpoint.host}:{endpoint.port}")

    def _remember_endpoint(self, frame: ParsedMavlinkFrame, endpoint: Endpoint) -> None:
        asset = self.asset_by_system_id.get(frame.system_id)
        if asset is None:
            return
        self.endpoint_by_asset_id[asset.id] = endpoint
        edge_id = self._edge_id(asset.id)
        if edge_id not in self.registered_edges:
            self.client.register_edge(edge_id=edge_id, asset_id=asset.id, device_type=_device_type(asset.platform_class))
            self.registered_edges.add(edge_id)


    def _handle_mission_request_int(self, sock: socket.socket, frame: ParsedMavlinkFrame, endpoint: Endpoint) -> None:
        key = (endpoint.host, frame.system_id)
        items = self.pending_mission_items.get(key)
        if not items:
            return
        seq = int(frame.fields.get("seq", -1))
        if seq < 0 or seq >= len(items):
            return
        item = items[seq]
        sock.sendto(item.frame, endpoint.socket_address)
        print(f"sent {item.message_name} seq={seq} {item.object_type}:{item.object_id} -> {endpoint.host}:{endpoint.port}")

    def _handle_mission_ack(self, frame: ParsedMavlinkFrame, endpoint: Endpoint) -> None:
        key = (endpoint.host, frame.system_id)
        pending = self.pending_mission_upload.pop(key, None)
        self.pending_mission_items.pop(key, None)
        if pending is None:
            return
        result = f"MISSION_ACK_{int(frame.fields.get('type', -1))}"
        edge_id = self._edge_id(pending.asset_id)
        self.client.ack_edge_work(edge_id=edge_id, object_type=pending.object_type, object_id=pending.object_id, result=result)
        print(f"mission ack {pending.object_type}:{pending.object_id} from {endpoint.host}:{endpoint.port} result={result}")
    def _handle_command_ack(self, frame: ParsedMavlinkFrame, endpoint: Endpoint) -> None:
        command_id = int(frame.fields.get("command", -1))
        key = (endpoint.host, frame.system_id, command_id)
        pending = self.pending_ack.pop(key, None)
        if pending is None:
            return
        result_code = int(frame.fields.get("result", -1))
        result = ACK_RESULTS.get(result_code, f"MAV_RESULT_{result_code}")
        edge_id = self._edge_id(pending.asset_id)
        self.client.ack_edge_work(edge_id=edge_id, object_type=pending.object_type, object_id=pending.object_id, result=result)
        print(f"ack {pending.object_type}:{pending.object_id} from {endpoint.host}:{endpoint.port} result={result}")

    def _next_sequence(self) -> int:
        value = self.sequence
        self.sequence = (self.sequence + 1) % 256
        return value

    def _next_signing_timestamp(self) -> int:
        self.signing_timestamp += 1
        return self.signing_timestamp

    @staticmethod
    def _edge_id(asset_id: str) -> str:
        return f"mavlink-edge-{asset_id}"


def _device_type(platform_class: str) -> str:
    return "ugv_edge" if "ugv" in platform_class.lower() or "ground" in platform_class.lower() else "uav_edge"



def _parse_signing_key(value: str | None) -> bytes | None:
    if not value:
        return None
    key = bytes.fromhex(value)
    if len(key) != 32:
        raise ValueError("--signing-key-hex must decode to exactly 32 bytes")
    return key

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Receive and transmit MAVLink UDP messages for the UAS/UTM service.")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=14551)
    parser.add_argument("--scenario", default="scenarios/korea_defense_uas_utm_ops.json")
    parser.add_argument("--service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--poll-interval-s", type=float, default=1.0)
    parser.add_argument("--timeout-s", type=float, default=0.2)
    parser.add_argument("--signing-key-hex", default=None, help="Optional 32-byte MAVLink2 signing key as 64 hex chars")
    parser.add_argument("--signing-link-id", type=int, default=0)
    args = parser.parse_args(argv)

    gateway = BidirectionalMavlinkGateway(
        scenario_path=Path(args.scenario),
        service_url=args.service_url,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        poll_interval_s=args.poll_interval_s,
        timeout_s=args.timeout_s,
        signing_key=_parse_signing_key(args.signing_key_hex),
        signing_link_id=args.signing_link_id,
    )
    gateway.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())