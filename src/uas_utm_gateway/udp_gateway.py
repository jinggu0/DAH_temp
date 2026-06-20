from __future__ import annotations

import argparse
import socket
from pathlib import Path

from .ingest_client import IngestClient
from .mavlink_parser import parse_datagram
from .translator import MavlinkTelemetryTranslator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Receive MAVLink UDP telemetry and forward it to the UAS/UTM service.")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=14550)
    parser.add_argument("--scenario", default="scenarios/korea_defense_uas_utm_ops.json")
    parser.add_argument("--ingest-url", default="http://127.0.0.1:8080/api/telemetry/ingest")
    parser.add_argument("--timeout-s", type=float, default=1.0)
    args = parser.parse_args(argv)

    translator = MavlinkTelemetryTranslator(Path(args.scenario))
    client = IngestClient(args.ingest_url, timeout_s=args.timeout_s)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.listen_host, args.listen_port))
    print(f"MAVLink UDP gateway listening on {args.listen_host}:{args.listen_port}")
    print(f"forwarding telemetry to {args.ingest_url}")
    try:
        while True:
            datagram, address = sock.recvfrom(65535)
            try:
                for item in parse_datagram(datagram):
                    message = translator.translate(item)
                    if message is None:
                        continue
                    response = client.post(message)
                    accepted = response.get("payload", {}).get("accepted")
                    print(f"{address[0]}:{address[1]} -> {message['payload']['asset_id']} accepted={accepted}")
            except Exception as exc:
                print(f"gateway error from {address[0]}:{address[1]}: {exc}")
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
