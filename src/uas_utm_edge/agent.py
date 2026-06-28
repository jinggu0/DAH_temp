from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a simulated UAV/UGV edge device agent for the DAH UAS/UTM service.")
    parser.add_argument("--service-url", default="http://127.0.0.1:8080")
    parser.add_argument("--edge-id", required=True)
    parser.add_argument("--device-type", choices=["uav_edge", "ugv_edge", "payload_edge", "c2_gateway", "test_harness"], default="uav_edge")
    parser.add_argument("--asset", action="append", dest="assets", default=[])
    parser.add_argument("--authority", default="External Edge Cell")
    parser.add_argument("--link-profile", action="append", dest="link_profiles", default=["mavlink_udp"])
    parser.add_argument("--software-version", default="edge-dev")
    parser.add_argument("--interval-s", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--emit-sample-telemetry", action="store_true")
    args = parser.parse_args(argv)

    client = EdgeClient(args.service_url.rstrip("/"))
    registration = _register_with_retry(client, args)
    print(json.dumps({"registered": registration["payload"]}, ensure_ascii=False))

    while True:
        heartbeat = client.post(
            "/api/edge/devices/heartbeat",
            {
                "edge_id": args.edge_id,
                "status": "online",
                "cpu_load": 0.18,
                "battery_wh": 720.0,
                "link_quality": 0.96,
                "temperature_c": 39.5,
            },
        )
        if args.emit_sample_telemetry and args.assets:
            client.post(
                "/api/telemetry/ingest",
                {
                    "asset_id": args.assets[0],
                    "time_s": 120,
                    "position": [210.0, -235.0, 98.0],
                    "velocity_mps": [8.5, 0.5, 0.0],
                    "status": "edge-live",
                    "source": args.edge_id,
                    "source_id": args.edge_id,
                    "source_type": args.device_type,
                    "source_authority": args.authority,
                    "track_confidence": 0.9,
                    "link_profile": args.link_profiles[0] if args.link_profiles else None,
                },
            )
        work = client.get(f"/api/edge/work?edge_id={args.edge_id}")
        print(
            json.dumps(
                {
                    "heartbeat_status": heartbeat["payload"]["status"],
                    "command_count": len(work["payload"]["commands"]),
                    "mission_upload_count": len(work["payload"]["mission_uploads"]),
                    "egress_policy": work["payload"]["egress_policy"],
                },
                ensure_ascii=False,
            )
        )
        if args.once:
            return 0
        time.sleep(args.interval_s)


def _register_with_retry(client: "EdgeClient", args: argparse.Namespace, max_retries: int = 10, delay_s: float = 3.0) -> dict[str, Any]:
    payload = {
        "edge_id": args.edge_id,
        "device_type": args.device_type,
        "asset_ids": args.assets,
        "authority": args.authority,
        "link_profiles": args.link_profiles,
        "capabilities": ["telemetry_ingest", "approved_work_poll", "ack_work"],
        "software_version": args.software_version,
    }
    for attempt in range(1, max_retries + 1):
        try:
            return client.post("/api/edge/devices/register", payload)
        except SystemExit as exc:
            if attempt >= max_retries or "connection failed" not in str(exc):
                raise
            print(f"[edge-agent] GCS not ready (attempt {attempt}/{max_retries}), retrying in {delay_s}s...")
            time.sleep(delay_s)
    raise SystemExit("edge-agent: exceeded max retries for GCS registration")


class EdgeClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps({"payload": payload}).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"HTTP {exc.code} {method} {path}: {detail}") from exc
        except URLError as exc:
            raise SystemExit(f"connection failed {method} {path}: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
