from __future__ import annotations

import argparse
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .protocol import envelope, protocol_profile
from .state import ServiceState


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the UAS/UTM virtual environment dashboard and API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--scenario", default="scenarios/korea_defense_uas_utm_ops.json")
    parser.add_argument("--log-dir", default="logs/uas_utm", help="Append-only JSONL audit log directory")
    args = parser.parse_args(argv)

    state = ServiceState(Path(args.scenario), log_dir=Path(args.log_dir))
    handler_class = _make_handler(state)
    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    print(f"UAS/UTM service listening on http://{args.host}:{args.port}")
    print(f"scenario: {Path(args.scenario).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _make_handler(state: ServiceState) -> type[BaseHTTPRequestHandler]:
    static_root = Path(__file__).resolve().parent / "static"

    class UasUtmHandler(BaseHTTPRequestHandler):
        server_version = "UasUtmService/0.3"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/api/health":
                self._send_json(envelope(message_type="utm.health", payload={"ok": True, "scenario": state.scenario.name}))
            elif path == "/api/protocol-monitor":
                self._send_json(envelope(message_type="dah.protocol_monitor", payload=state.protocol_monitor_payload(_int_query(query, "time_s"), _int_query(query, "limit") or 25)))
            elif path == "/api/protocol":
                self._send_json(envelope(message_type="utm.protocol", payload=protocol_profile()))
            elif path == "/api/scenario":
                self._send_json(envelope(message_type="utm.scenario", payload=state.scenario_payload()))
            elif path == "/api/operation-profile":
                self._send_json(envelope(message_type="utm.operation_profile", payload=state.operation_profile()))
            elif path == "/api/edge/devices":
                self._send_json(envelope(message_type="utm.edge.devices", payload=state.edge_devices_payload()))
            elif path == "/api/service-status":
                self._send_json(envelope(message_type="dah.service_status", payload=state.service_status_payload()))
            elif path == "/api/scenario-packages":
                self._send_json(envelope(message_type="dah.scenario_packages", payload=state.scenario_packages_payload()))
            elif path == "/api/tactical-emulator":
                self._send_json(envelope(message_type="dah.tactical_emulator", payload=state.tactical_emulator_payload()))
            elif path == "/api/dashboard":
                self._send_json(envelope(message_type="dah.dashboard", payload=state.dashboard_payload()))
            elif path == "/api/chain":
                self._send_json(envelope(message_type="dah.chain", payload=state.chain_payload()))
            elif path == "/api/alerts":
                self._send_json(envelope(message_type="dah.alerts", payload=state.alerts_payload(_int_query(query, "limit") or 50)))
            elif path == "/api/summary":
                self._send_json(envelope(message_type="utm.summary", payload=state.summary))
            elif path == "/api/decisions":
                self._send_json(envelope(message_type="utm.decisions", payload=state.decisions_payload()))
            elif path == "/api/timeline":
                self._send_json(envelope(message_type="utm.timeline", payload=state.timeline_payload()))
            elif path == "/api/telemetry":
                time_s = _int_query(query, "time_s")
                self._send_json(envelope(message_type="utm.telemetry.snapshot", payload=state.telemetry_snapshot(time_s)))
            elif path == "/api/live/snapshot":
                time_s = _int_query(query, "time_s")
                self._send_json(envelope(message_type="utm.telemetry.live", payload=state.live_snapshot(time_s)))
            elif path == "/api/tracks":
                time_s = _int_query(query, "time_s")
                self._send_json(envelope(message_type="utm.tracks", payload=state.tracks_payload(time_s)))
            elif path == "/api/edge/work":
                edge_id = _str_query(query, "edge_id")
                if edge_id is None:
                    self._send_json(envelope(message_type="utm.edge.work", payload={"accepted": False, "error": "edge_id is required"}), status=HTTPStatus.BAD_REQUEST)
                else:
                    try:
                        self._send_json(envelope(message_type="utm.edge.work", payload=state.edge_work_payload(edge_id)))
                    except ValueError as exc:
                        self._send_json(envelope(message_type="utm.edge.work", payload={"accepted": False, "error": str(exc)}), status=HTTPStatus.BAD_REQUEST)
            elif path == "/api/live/stream":
                self._send_sse(query)
            elif path == "/api/mavlink":
                limit = _int_query(query, "limit") or 80
                asset_id = query.get("asset_id", [None])[0]
                self._send_json(
                    envelope(
                        message_type="utm.mavlink.messages",
                        payload=state.mavlink_payload(asset_id=asset_id, limit=max(1, min(limit, 500))),
                    )
                )
            elif path == "/api/commands":
                self._send_json(envelope(message_type="utm.command.list", payload=state.commands_payload(_str_query(query, "status"))))
            elif path == "/api/mission-uploads":
                self._send_json(
                    envelope(
                        message_type="utm.mission_upload.list",
                        payload=state.mission_uploads_payload(_str_query(query, "status")),
                    )
                )
            elif path == "/api/gateway/commands":
                self._send_json(
                    envelope(
                        message_type="utm.gateway.commands",
                        payload=state.commands_payload(_str_query(query, "status") or "approved_for_gateway"),
                    )
                )
            elif path == "/api/gateway/mission-uploads":
                self._send_json(
                    envelope(
                        message_type="utm.gateway.mission_uploads",
                        payload=state.mission_uploads_payload(_str_query(query, "status") or "approved_for_gateway"),
                    )
                )
            elif path == "/api/audit" or path == "/api/logs":
                self._send_json(
                    envelope(
                        message_type="utm.audit",
                        payload=state.audit_payload(
                            _int_query(query, "limit") or 100,
                            event_type=_str_query(query, "event_type"),
                        ),
                    )
                )
            elif path == "/api/logs/agent-view":
                self._send_json(
                    envelope(
                        message_type="utm.logs.agent_view",
                        payload=state.agent_logs_payload(
                            _int_query(query, "limit") or 100,
                            event_type=_str_query(query, "event_type"),
                            phase=_str_query(query, "phase"),
                            include_heartbeat=_bool_query(query, "include_heartbeat", True),
                        ),
                    )
                )
            elif path == "/api/protocol/logs":
                self._send_json(
                    envelope(
                        message_type="utm.protocol.logs",
                        payload=state.protocol_logs_payload(
                            _int_query(query, "limit") or 100,
                            include_heartbeat=_bool_query(query, "include_heartbeat", True),
                        ),
                    )
                )
            elif path == "/api/runtime/logs":
                self._send_json(envelope(message_type="utm.runtime.logs", payload=state.runtime_logs_payload(_int_query(query, "limit") or 100)))
            elif path == "/api/logs/status":
                self._send_json(envelope(message_type="utm.logs.status", payload=state.logs_status_payload()))
            elif path == "/api/logs/verify":
                self._send_json(envelope(message_type="utm.logs.verify", payload=state.verify_logs_payload()))
            elif path == "/api/baseline/export":
                self._send_json(envelope(message_type="utm.baseline.export", payload=state.baseline_export_payload(_int_query(query, "limit") or 500)))
            elif path == "/" or path == "/index.html":
                self._send_file(static_root / "index.html")
            elif path.startswith("/static/"):
                self._send_file(static_root / path.removeprefix("/static/"))
            else:
                self._send_json(
                    envelope(message_type="utm.error", payload={"error": "not_found", "path": path}),
                    status=HTTPStatus.NOT_FOUND,
                )

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            route_map = {
                "/api/telemetry/ingest": ("utm.telemetry.ingest", state.ingest_telemetry, HTTPStatus.ACCEPTED),
                "/api/edge/devices/register": ("utm.edge.device.register", state.register_edge_device, HTTPStatus.ACCEPTED),
                "/api/edge/devices/heartbeat": ("utm.edge.device.heartbeat", state.heartbeat_edge_device, HTTPStatus.ACCEPTED),
                "/api/edge/work/ack": ("utm.edge.work.ack", state.ack_edge_work, HTTPStatus.OK),
                "/api/commands/request": ("utm.command.request", state.request_command, HTTPStatus.ACCEPTED),
                "/api/commands/approve": ("utm.command.approve", state.approve_command, HTTPStatus.OK),
                "/api/commands/reject": ("utm.command.reject", state.reject_command, HTTPStatus.OK),
                "/api/mission-uploads/request": ("utm.mission_upload.request", state.request_mission_upload, HTTPStatus.ACCEPTED),
                "/api/mission-uploads/approve": ("utm.mission_upload.approve", state.approve_mission_upload, HTTPStatus.OK),
                "/api/faults/inject": ("dah.fault.inject", state.inject_fault, HTTPStatus.ACCEPTED),
            }
            route = route_map.get(parsed.path)
            if route is None:
                self._send_json(
                    envelope(message_type="utm.error", payload={"error": "not_found", "path": parsed.path}),
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            message_type, handler, success_status = route
            try:
                message = self._read_json_body()
                payload = handler(message)
            except ValueError as exc:
                self._send_json(
                    envelope(message_type=message_type, payload={"accepted": False, "error": str(exc)}),
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(envelope(message_type=message_type, payload=payload), status=success_status)

        def log_message(self, format: str, *args: object) -> None:
            rendered = format % args
            remote = self.address_string()
            line = f"{remote} - {rendered}"
            print(line)
            try:
                state.record_runtime_log(
                    source="uas-utm-service",
                    message=line,
                    data={"remote": remote, "request": rendered},
                )
            except Exception:
                pass

        def _read_json_body(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                raise ValueError("request body is required")
            body = self.rfile.read(content_length)
            try:
                value = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("request body must be valid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("request body must be a JSON object")
            return value

        def _send_sse(self, query: dict[str, list[str]]) -> None:
            interval_ms = max(100, min(_int_query(query, "interval_ms") or 1000, 10000))
            max_events = max(1, min(_int_query(query, "max_events") or 120, 10000))
            timeline = state.timeline or [0]
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for index in range(max_events):
                time_s = timeline[index % len(timeline)]
                message = envelope(message_type="utm.telemetry.live", payload=state.live_snapshot(time_s))
                data = json.dumps(message, ensure_ascii=False)
                try:
                    self.wfile.write(f"event: telemetry\ndata: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(interval_ms / 1000)
            self.close_connection = True

        def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path) -> None:
            try:
                resolved = path.resolve()
                if static_root.resolve() not in resolved.parents and resolved != static_root.resolve():
                    raise FileNotFoundError
                body = resolved.read_bytes()
            except OSError:
                self._send_json(
                    envelope(message_type="utm.error", payload={"error": "static_not_found"}),
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return UasUtmHandler


def _int_query(query: dict[str, list[str]], key: str) -> int | None:
    raw_value = query.get(key, [None])[0]
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _bool_query(query: dict[str, list[str]], key: str, default: bool = False) -> bool:
    raw_value = query.get(key, [None])[0]
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}

def _str_query(query: dict[str, list[str]], key: str) -> str | None:
    value = query.get(key, [None])[0]
    return value if value else None


if __name__ == "__main__":
    raise SystemExit(main())
