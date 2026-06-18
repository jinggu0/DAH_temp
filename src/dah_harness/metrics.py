from __future__ import annotations

from statistics import mean
from typing import Any

from .models import SimulationResult, distance


def score_result(result: SimulationResult, *, detection_grace_s: int = 5) -> dict[str, Any]:
    detections: dict[str, int | None] = {}
    latencies: list[int] = []

    for attack in result.scenario.attacks:
        first_detection_s: int | None = None
        for action in result.actions:
            if action.asset_id != attack.asset_id:
                continue
            if action.time_s < attack.start_s:
                continue
            if action.time_s > attack.end_s + detection_grace_s:
                continue
            if _action_matches_attack(action.reason, attack.kind):
                first_detection_s = action.time_s
                break
        detections[attack.id] = first_detection_s
        if first_detection_s is not None:
            latencies.append(first_detection_s - attack.start_s)

    false_positive_actions = [
        action
        for action in result.actions
        if not any(
            attack.asset_id == action.asset_id
            and attack.start_s <= action.time_s <= attack.end_s + detection_grace_s
            for attack in result.scenario.attacks
        )
    ]

    attack_count = len(result.scenario.attacks)
    detected_count = sum(1 for value in detections.values() if value is not None)
    mission_progress = _mission_progress(result)

    return {
        "attack_count": attack_count,
        "detected_count": detected_count,
        "detection_rate": round(detected_count / attack_count, 4) if attack_count else 1.0,
        "mean_detection_latency_s": round(mean(latencies), 2) if latencies else None,
        "false_positive_actions": len(false_positive_actions),
        "detections": detections,
        "mission_progress": mission_progress,
    }


def _action_matches_attack(reason: str, attack_kind: str) -> bool:
    if attack_kind == "gps_spoof":
        return reason.startswith("gps_jump") or reason.startswith("route_deviation")
    if attack_kind == "command_injection":
        return reason.startswith("command_deviation")
    if attack_kind == "link_jam":
        return reason.startswith("link_loss")
    return False


def _mission_progress(result: SimulationResult) -> dict[str, float]:
    progress: dict[str, float] = {}
    last_frames = {}
    for frame in result.frames:
        last_frames[frame.asset_id] = frame

    for asset in result.scenario.assets:
        if not asset.waypoints:
            progress[asset.id] = 1.0
            continue
        last_frame = last_frames.get(asset.id)
        if last_frame is None:
            progress[asset.id] = 0.0
            continue
        total_distance = distance(asset.start, asset.waypoints[-1])
        remaining_distance = distance(last_frame.true_position, asset.waypoints[-1])
        if total_distance == 0:
            progress[asset.id] = 1.0
        else:
            progress[asset.id] = round(max(0.0, min(1.0, 1.0 - remaining_distance / total_distance)), 4)
    return progress
