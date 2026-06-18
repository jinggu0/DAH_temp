from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Literal

Position = tuple[float, float, float]
ZoneKind = Literal["operating_area", "no_fly_zone", "restricted_altitude"]
MissionStatus = Literal["pending", "approved", "rejected", "active", "completed"]


@dataclass(frozen=True)
class UavSpec:
    id: str
    callsign: str
    start: Position
    cruise_speed_mps: float
    min_altitude_m: float
    max_altitude_m: float
    battery_capacity_wh: float


@dataclass(frozen=True)
class AirspaceZone:
    id: str
    kind: ZoneKind
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    min_altitude_m: float
    max_altitude_m: float
    label: str = ""


@dataclass(frozen=True)
class MissionSpec:
    id: str
    asset_id: str
    route: list[Position]
    requested_start_s: int
    requested_end_s: int
    nominal_speed_mps: float
    purpose: str = "normal_ops"


@dataclass
class MissionState:
    spec: MissionSpec
    status: MissionStatus = "pending"
    rejection_reasons: list[str] = field(default_factory=list)
    current_waypoint_index: int = 0


@dataclass(frozen=True)
class UtmDecision:
    mission_id: str
    asset_id: str
    approved: bool
    reasons: list[str]


@dataclass(frozen=True)
class TelemetryFrame:
    time_s: int
    asset_id: str
    mission_id: str | None
    position: Position
    next_waypoint: Position | None
    status: str
    battery_wh: float


@dataclass(frozen=True)
class UasUtmScenario:
    name: str
    duration_s: int
    step_s: int
    conflict_distance_m: float
    assets: list[UavSpec]
    zones: list[AirspaceZone]
    missions: list[MissionSpec]


@dataclass(frozen=True)
class UasUtmResult:
    scenario: UasUtmScenario
    decisions: list[UtmDecision]
    telemetry: list[TelemetryFrame]


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


def round_position(position: Position) -> Position:
    return (round(position[0], 3), round(position[1], 3), round(position[2], 3))
