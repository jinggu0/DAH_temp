from __future__ import annotations

import json
from typing import Any
from urllib import parse, request


class UtmServiceClient:
    def __init__(self, base_url: str, timeout_s: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def get_gateway_commands(self) -> list[dict[str, Any]]:
        payload = self.get("/api/gateway/commands").get("payload", {})
        return list(payload.get("commands", []))

    def get_gateway_mission_uploads(self) -> list[dict[str, Any]]:
        payload = self.get("/api/gateway/mission-uploads").get("payload", {})
        return list(payload.get("mission_uploads", []))

    def ingest_telemetry(self, message: dict[str, Any]) -> dict[str, Any]:
        return self.post("/api/telemetry/ingest", message)

    def register_edge(self, *, edge_id: str, asset_id: str, device_type: str = "uav_edge", authority: str = "MAVLink Bidirectional Gateway") -> dict[str, Any]:
        return self.post(
            "/api/edge/devices/register",
            {
                "payload": {
                    "edge_id": edge_id,
                    "device_type": device_type,
                    "asset_ids": [asset_id],
                    "authority": authority,
                    "capabilities": ["mavlink_udp_rx", "mavlink_udp_tx", "command_ack"],
                    "link_profiles": ["mavlink_udp"],
                    "software_version": "mavlink-bidir-dev",
                }
            },
        )

    def ack_edge_work(self, *, edge_id: str, object_type: str, object_id: str, result: str) -> dict[str, Any]:
        return self.post(
            "/api/edge/work/ack",
            {
                "payload": {
                    "edge_id": edge_id,
                    "object_type": object_type,
                    "object_id": object_id,
                    "result": result,
                }
            },
        )

    def get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        if query:
            url += "?" + parse.urlencode(query)
        req = request.Request(url, method="GET", headers={"Accept": "application/json"})
        with request.urlopen(req, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, message: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with request.urlopen(req, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))