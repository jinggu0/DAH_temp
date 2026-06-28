from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .service_contracts import make_service_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight DAH role status service for Docker Desktop demos.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--status", default="normal", choices=["normal", "degraded", "critical"])
    parser.add_argument("--emulated", action="store_true")
    parser.add_argument("--boundary", default="local Docker mock/demo service")
    parser.add_argument("--metric", action="append", default=[], help="metric key=value")
    args = parser.parse_args(argv)

    metrics = _parse_metrics(args.metric)
    payload = make_service_status(
        service_id=args.service_id,
        role=args.role,
        status=args.status,
        emulated=args.emulated,
        boundary=args.boundary,
        metrics=metrics,
    ).to_payload()

    handler_class = _make_handler(payload)
    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    print(f"{args.service_id} role service listening on http://{args.host}:{args.port}")
    print(json.dumps(payload, ensure_ascii=False))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _make_handler(payload: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    class RoleHandler(BaseHTTPRequestHandler):
        server_version = "DahRoleService/0.1"

        def do_GET(self) -> None:
            if self.path in {"/", "/health"}:
                self._send_json({"ok": True, **payload, "updated_at": _now()})
            elif self.path == "/status":
                self._send_json({**payload, "updated_at": _now()})
            elif self.path == "/metrics":
                self._send_json({"service_id": payload["service_id"], "metrics": payload["metrics"], "updated_at": _now()})
            else:
                self._send_json({"error": "not_found", "path": self.path}, HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}")

        def _send_json(self, value: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return RoleHandler


def _parse_metrics(raw_items: list[str]) -> dict[str, str | int | float | bool]:
    metrics: dict[str, str | int | float | bool] = {}
    for item in raw_items:
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            continue
        metrics[key] = _coerce_value(raw_value.strip())
    return metrics


def _coerce_value(value: str) -> str | int | float | bool:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())