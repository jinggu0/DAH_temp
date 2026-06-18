from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Literal

Position = tuple[float, float, float]
AssetKind = Literal["UAV", "UGV"]


@dataclass
class AssetSpec:
    id: str
    kind: AssetKind
    start: Position
    waypoints: list[Position]
    nominal_speed_mps: float


@dataclass
class AttackEvent:
    id: str
    asset_id: str
    kind: str
    start_s: int
    end_s: int
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DefenseConfig:
    gps_jump_threshold_m: float = 40.0
    route_deviation_threshold_m: float = 60.0
    command_deviation_threshold_m: float = 45.0
    link_loss_threshold_s: int = 5
    quarantine_score_threshold: int = 2


@dataclass
class Scenario:
    name: str
    description: str
    duration_s: int
    step_s: int
    seed: int
    assets: list[AssetSpec]
    attacks: list[AttackEvent]
    defense: DefenseConfig
    metric_detection_grace_s: int = 5


@dataclass
class TelemetryMutation:
    reported_position: Position | None
    command_target: Position
    link_ok: bool
    active_attack_ids: list[str]


@dataclass
class TelemetryFrame:
    time_s: int
    asset_id: str
    asset_kind: AssetKind
    true_position: Position
    expected_position: Position
    reported_position: Position | None
    nominal_target: Position
    command_target: Position
    link_ok: bool
    active_attack_ids: list[str]


@dataclass
class DefenseAction:
    time_s: int
    asset_id: str
    action_type: str
    reason: str
    active_attack_ids: list[str]


@dataclass
class SimulationResult:
    scenario: Scenario
    frames: list[TelemetryFrame]
    actions: list[DefenseAction]


def distance(left: Position, right: Position) -> float:
    return sqrt(
        (left[0] - right[0]) ** 2
        + (left[1] - right[1]) ** 2
        + (left[2] - right[2]) ** 2
    )


def move_toward(position: Position, target: Position, max_distance: float) -> Position:
    remaining = distance(position, target)
    if remaining == 0 or max_distance >= remaining:
        return target
    ratio = max_distance / remaining
    return (
        position[0] + (target[0] - position[0]) * ratio,
        position[1] + (target[1] - position[1]) * ratio,
        position[2] + (target[2] - position[2]) * ratio,
    )
