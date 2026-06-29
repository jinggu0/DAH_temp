from __future__ import annotations

import argparse
import socket
from http import HTTPStatus
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a minimal local reverse proxy for DAH Docker Desktop entrypoints.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--target", required=True, help="Target base URL, for example http://dah-gcs:8080")
    parser.add_argument("--timeout-s", type=float, default=30.0, help="Upstream request timeout in seconds")
    args = parser.parse_args(argv)

    target = args.target.rstrip("/") + "/"
    handler_class = _make_handler(target, args.timeout_s)
    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    print(f"DAH reverse proxy listening on http://{args.host}:{args.port} -> {target}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _make_handler(target: str, timeout_s: float = 30.0) -> type[BaseHTTPRequestHandler]:
    class ProxyHandler(BaseHTTPRequestHandler):
        server_version = "DahReverseProxy/0.1"

        def do_GET(self) -> None:
            self._proxy()

        def do_POST(self) -> None:
            self._proxy()

        def do_PUT(self) -> None:
            self._proxy()

        def do_DELETE(self) -> None:
            self._proxy()

        def _proxy(self) -> None:
            url = urljoin(target, self.path.lstrip("/"))
            body = None
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 0:
                body = self.rfile.read(content_length)
            headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"}
            request = Request(url, data=body, method=self.command, headers=headers)
            try:
                with urlopen(request, timeout=timeout_s) as response:
                    response_body = response.read()
                    self.send_response(response.status)
                    for key, value in response.headers.items():
                        if key.lower() not in HOP_BY_HOP_HEADERS:
                            self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(response_body)
            except HTTPError as exc:
                response_body = exc.read()
                self.send_response(exc.code)
                self.send_header("Content-Type", exc.headers.get("Content-Type", "text/plain; charset=utf-8"))
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            except (TimeoutError, socket.timeout) as exc:
                self._send_proxy_error(HTTPStatus.GATEWAY_TIMEOUT, "upstream_timeout", exc)
            except RemoteDisconnected as exc:
                self._send_proxy_error(HTTPStatus.BAD_GATEWAY, "upstream_disconnected", exc)
            except URLError as exc:
                reason = exc.reason if hasattr(exc, "reason") else exc
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    self._send_proxy_error(HTTPStatus.GATEWAY_TIMEOUT, "upstream_timeout", reason)
                else:
                    self._send_proxy_error(HTTPStatus.BAD_GATEWAY, "upstream_unavailable", exc)

        def _send_proxy_error(self, status: HTTPStatus, code: str, exc: BaseException) -> None:
            response_body = f"{code}: {exc}".encode("utf-8", errors="replace")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} - {format % args}")

    return ProxyHandler


if __name__ == "__main__":
    raise SystemExit(main())
