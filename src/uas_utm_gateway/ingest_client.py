from __future__ import annotations

import json
from typing import Any
from urllib import request


class IngestClient:
    def __init__(self, ingest_url: str, timeout_s: float = 2.0):
        self.ingest_url = ingest_url
        self.timeout_s = timeout_s

    def post(self, message: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.ingest_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
