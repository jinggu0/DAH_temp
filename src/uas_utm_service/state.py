from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any

from uas_utm.models import TelemetryFrame
from uas_utm.simulator import load_scenario, run_environment, summarize_result


class ServiceState:
    def __init__(self, scenario_path: Path):
        self.scenario_path = scenario_path
        self._lock = Lock()
        self.external_frames: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self.scenario = load_scenario(self.scenario_path)
            self.result = run_environment(self.scenario)
            self.summary = summarize_result(self.result)
            self.frames_by_time: dict[int, list[TelemetryFrame]] = {}
            for frame in self.result.telemetry:
                self.frames_by_time.setdefault(frame.time_s, []).append(frame)
            self.timeline = sorted(self.frames_by_time)

    def scenario_payload(self) -> dict[str, Any]:
        return {
            "name": self.scenario.name,
            "duration_s": self.scenario.duration_s,
            "step_s": self.scenario.step_s,
            "conflict_distance_m": self.scenario.conflict_distance_m,
            "origin_lat_e7": self.scenario.origin_lat_e7,
            "origin_lon_e7": self.scenario.origin_lon_e7,
            "assets": [asdict(asset) for asset in self.scenario.assets],
            "zones": [asdict(zone) for zone in self.scenario.zones],
            "c2_nodes": [asdict(node) for node in self.scenario.c2_nodes],
            "missions": [asdict(mission) for mission in self.scenario.missions],
        }

    def decisions_payload(self) -> list[dict[str, Any]]:
        return [asdict(decision) for decision in self.result.decisions]

    def telemetry_snapshot(self, requested_time_s: int | None = None) -> dict[str, Any]:
        time_s = self._nearest_time(requested_time_s)
        frames = self.frames_by_time.get(time_s, [])
        return {
            "time_s": time_s,
            "frames": [asdict(frame) for frame in frames],
        }

    def live_snapshot(self, requested_time_s: int | None = None) -> dict[str, Any]:
        snapshot = self.telemetry_snapshot(requested_time_s)
        with self._lock:
            external_frames = list(self.external_frames.values())
        snapshot["external_frames"] = external_frames
        snapshot["mode"] = "hybrid" if external_frames else "simulation"
        return snapshot

    def ingest_telemetry(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = message.get("payload", message)
        if not isinstance(payload, dict):
            raise ValueError("telemetry payload must be an object")
        asset_id = str(payload.get("asset_id", "")).strip()
        position = payload.get("position")
        if not asset_id:
            raise ValueError("asset_id is required")
        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("position must be [x, y, z]")

        normalized = {
            "time_s": int(payload.get("time_s", self.timeline[-1] if self.timeline else 0)),
            "asset_id": asset_id,
            "mission_id": payload.get("mission_id"),
            "position": [float(position[0]), float(position[1]), float(position[2])],
            "status": str(payload.get("status", "external")),
            "battery_wh": float(payload.get("battery_wh", 0.0)),
            "velocity_mps": payload.get("velocity_mps", [0.0, 0.0, 0.0]),
            "heading_deg": float(payload.get("heading_deg", 0.0)),
            "c2_node_id": payload.get("c2_node_id"),
            "link_profile": payload.get("link_profile"),
            "source": str(payload.get("source", "external")),
        }
        with self._lock:
            self.external_frames[asset_id] = normalized
        return {
            "accepted": True,
            "asset_id": asset_id,
            "external_asset_count": len(self.external_frames),
        }

    def timeline_payload(self) -> dict[str, Any]:
        return {
            "start_s": self.timeline[0] if self.timeline else 0,
            "end_s": self.timeline[-1] if self.timeline else 0,
            "step_s": self.scenario.step_s,
            "ticks": self.timeline,
        }

    def mavlink_payload(self, asset_id: str | None = None, limit: int = 80) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for frame in self.result.telemetry:
            if asset_id and frame.asset_id != asset_id:
                continue
            for message in frame.mavlink_messages:
                rows.append(
                    {
                        "time_s": frame.time_s,
                        "asset_id": frame.asset_id,
                        "mission_id": frame.mission_id,
                        "message": asdict(message),
                    }
                )
        return {
            "asset_id": asset_id,
            "limit": limit,
            "messages": rows[-limit:],
        }

    def _nearest_time(self, requested_time_s: int | None) -> int:
        if not self.timeline:
            return 0
        if requested_time_s is None:
            return self.timeline[-1]
        return min(self.timeline, key=lambda item: abs(item - requested_time_s))
