from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, sqrt
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
    service_branch: str = "generic"
    platform_class: str = "small_uas"
    role: str = "normal_ops"
    datalink_profiles: tuple[str, ...] = ("mavlink_udp",)
    sensor_payloads: tuple[str, ...] = ()
    endurance_s: int | None = None
    system_id: int = 1
    component_id: int = 1


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
    controlling_authority: str = "UTM"


@dataclass(frozen=True)
class C2Node:
    id: str
    kind: str
    location: Position
    coverage_radius_m: float
    supported_links: tuple[str, ...]
    latency_ms: int
    authority: str


@dataclass(frozen=True)
class MissionSpec:
    id: str
    asset_id: str
    route: list[Position]
    requested_start_s: int
    requested_end_s: int
    nominal_speed_mps: float
    purpose: str = "normal_ops"
    mission_type: str = "transit"
    priority: int = 3
    control_mode: str = "auto"
    required_payloads: tuple[str, ...] = ()
    required_link: str = "mavlink_udp"
    corridor_width_m: float = 60.0


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
class MavlinkMessage:
    message_name: str
    system_id: int
    component_id: int
    sequence: int
    fields: dict[str, int | float | str | None]


@dataclass(frozen=True)
class TelemetryFrame:
    time_s: int
    asset_id: str
    mission_id: str | None
    position: Position
    next_waypoint: Position | None
    status: str
    battery_wh: float
    velocity_mps: Position = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    c2_node_id: str | None = None
    link_profile: str | None = None
    mavlink_messages: list[MavlinkMessage] = field(default_factory=list)


@dataclass(frozen=True)
class UasUtmScenario:
    name: str
    duration_s: int
    step_s: int
    conflict_distance_m: float
    assets: list[UavSpec]
    zones: list[AirspaceZone]
    missions: list[MissionSpec]
    c2_nodes: list[C2Node] = field(default_factory=list)
    origin_lat_e7: int = 373500000
    origin_lon_e7: int = 1270000000


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


def velocity_between(previous: Position, current: Position, step_s: int) -> Position:
    if step_s <= 0:
        return (0.0, 0.0, 0.0)
    return (
        (current[0] - previous[0]) / step_s,
        (current[1] - previous[1]) / step_s,
        (current[2] - previous[2]) / step_s,
    )


def heading_from_velocity(velocity: Position) -> float:
    if velocity[0] == 0 and velocity[1] == 0:
        return 0.0
    return round((degrees(atan2(velocity[0], velocity[1])) + 360.0) % 360.0, 2)


def round_position(position: Position) -> Position:
    return (round(position[0], 3), round(position[1], 3), round(position[2], 3))
