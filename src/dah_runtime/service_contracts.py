from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

ServiceHealth = Literal["normal", "degraded", "critical"]
VehicleType = Literal["UAV", "UGV", "unknown"]


@dataclass(frozen=True)
class ServiceStatus:
    service_id: str
    role: str
    status: ServiceHealth
    emulated: bool
    boundary: str
    updated_at: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class TelemetryEvent:
    vehicle_id: str
    vehicle_type: VehicleType
    timestamp: str
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    mode: str
    mission_id: str | None
    waypoint_index: int | None
    link_status: str
    source_protocol: str

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class CommandEvent:
    command_id: str
    source: str
    destination: str
    command_type: str
    approved: bool
    dry_run: bool
    ack_status: str
    timestamp: str = field(default_factory=lambda: utc_now())
    params: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class TacticalMessage:
    message_id: str
    source_layer: str
    destination_layer: str
    message_type: str
    priority: int
    route_path: list[str]
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: utc_now())

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class FaultEvent:
    fault_id: str
    fault_type: str
    target_layer: str
    simulation_only: bool
    parameters: dict[str, Any]
    effects: dict[str, Any]
    timestamp: str = field(default_factory=lambda: utc_now())

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class AlertEvent:
    alert_id: str
    severity: str
    category: str
    title: str
    description: str
    evidence: dict[str, Any]
    recommended_action: str
    timestamp: str = field(default_factory=lambda: utc_now())

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


def make_service_status(
    *,
    service_id: str,
    role: str,
    status: ServiceHealth = "normal",
    emulated: bool = False,
    boundary: str = "local Docker service",
    metrics: dict[str, Any] | None = None,
) -> ServiceStatus:
    return ServiceStatus(
        service_id=service_id,
        role=role,
        status=status,
        emulated=emulated,
        boundary=boundary,
        updated_at=utc_now(),
        metrics=metrics or {},
    )


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value