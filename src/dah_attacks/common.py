"""공격 컨테이너 공통 HTTP 클라이언트."""
from __future__ import annotations
import json, time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GcsClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def get(self, path: str) -> dict[str, Any]:
        return self._req("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._req("POST", path, payload)

    def _req(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps({"payload": payload}).encode()
        req = Request(
            self.base + path, data=body, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"연결 실패 {method} {path}: {e}") from e


def wait_for_gcs(client: GcsClient, retries: int = 15, delay: float = 3.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            client.get("/api/health")
            print(f"[attack] GCS 연결 성공 (시도 {attempt})", flush=True)
            return
        except Exception as e:
            print(f"[attack] GCS 대기 중 ({attempt}/{retries}): {e}", flush=True)
            time.sleep(delay)
    raise SystemExit("[attack] GCS 연결 실패 — 종료")
