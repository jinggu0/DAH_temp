from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.util import find_spec
from typing import Any, Literal
from uuid import uuid4

Position = tuple[float, float, float]
AssetKind = Literal["UAV", "UGV", "unknown"]
LinkStatus = Literal["normal", "degraded", "critical", "offline"]
AlertSeverity = Literal["info", "warning", "critical"]
ProtocolMode = Literal["mock", "udp_receive_available"]


@dataclass(frozen=True)
class VehicleTelemetry:
    timestamp_utc: str
    time_s: int
    asset_id: str
    asset_kind: AssetKind
    protocol: str
    position: Position
    velocity_mps: Position = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    battery_wh: float = 0.0
    link_id: str | None = None
    source: str = "mock_mavlink"
    status: str = "mock-live"
    raw_message_type: str = "GLOBAL_POSITION_INT"

    def validate(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id is required")
        if len(self.position) != 3:
            raise ValueError("position must contain x, y, z")
        if len(self.velocity_mps) != 3:
            raise ValueError("velocity_mps must contain vx, vy, vz")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class CommandEvent:
    command_id: str
    timestamp_utc: str
    asset_id: str
    command_type: str
    protocol: str = "REST_JSON_TO_MAVLINK_COMMAND"
    direction: str = "operator_to_utm"
    status: str = "queued_not_transmitted"
    requested_by: str = "operator"
    dry_run: bool = True
    params: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class TacticalMessage:
    message_id: str
    timestamp_utc: str
    source: str
    destination: str
    message_type: str
    layer: str
    priority: int = 3
    payload: dict[str, Any] = field(default_factory=dict)
    simulated: bool = True
    boundary: str = "SIMULATED / NOT REAL MILITARY SYSTEM"

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class LinkState:
    link_id: str
    source: str
    target: str
    transport: str
    status: LinkStatus = "normal"
    latency_ms: int = 0
    packet_loss_pct: float = 0.0
    simulated: bool = False
    boundary: str = "REAL UAS/MAVLINK-CAPABLE OR LOCAL MOCK"

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class AlertEvent:
    alert_id: str
    timestamp_utc: str
    severity: AlertSeverity
    category: str
    title: str
    target: str | None
    recommended_response: str
    source_event_id: str | None = None
    simulation_only: bool = True

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class MavlinkAdapterStatus:
    mode: ProtocolMode
    pymavlink_available: bool
    receive_messages: tuple[str, ...]
    transmit_policy: str = "dry_run_only"
    safety_boundary: str = "Command transmission is disabled unless a future explicit safety adapter is installed."

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


class MockMavlinkAdapter:
    receive_messages = (
        "HEARTBEAT",
        "SYS_STATUS",
        "GLOBAL_POSITION_INT",
        "COMMAND_ACK",
        "MISSION_COUNT",
        "MISSION_ITEM_INT",
    )

    def status(self) -> MavlinkAdapterStatus:
        available = find_spec("pymavlink") is not None
        return MavlinkAdapterStatus(
            mode="udp_receive_available" if available else "mock",
            pymavlink_available=available,
            receive_messages=self.receive_messages,
        )

    def sample_telemetry(
        self,
        *,
        asset_id: str = "mock-uav-01",
        asset_kind: AssetKind = "UAV",
        time_s: int = 0,
        position: Position = (0.0, 0.0, 80.0),
        link_id: str = "mavlink_udp",
    ) -> VehicleTelemetry:
        telemetry = VehicleTelemetry(
            timestamp_utc=utc_now(),
            time_s=time_s,
            asset_id=asset_id,
            asset_kind=asset_kind,
            protocol="MAVLink2-compatible",
            position=position,
            velocity_mps=(1.0, 0.0, 0.0),
            heading_deg=90.0,
            battery_wh=1200.0,
            link_id=link_id,
            source="mock_mavlink_adapter",
            status="mock-live",
        )
        telemetry.validate()
        return telemetry


def command_from_queue(command: dict[str, Any]) -> CommandEvent:
    return CommandEvent(
        command_id=str(command.get("command_id", uuid4())),
        timestamp_utc=str(command.get("created_at") or utc_now()),
        asset_id=str(command.get("asset_id", "unknown")),
        command_type=str(command.get("command_type", "unknown")),
        status=str(command.get("status", "queued_not_transmitted")),
        requested_by=str(command.get("requested_by", "operator")),
        params=dict(command.get("params", {}) if isinstance(command.get("params"), dict) else {}),
    )


def telemetry_from_frame(frame: dict[str, Any], *, asset_kind: AssetKind = "unknown") -> VehicleTelemetry:
    position = _position_tuple(frame.get("position"), "position")
    velocity = _position_tuple(frame.get("velocity_mps", (0.0, 0.0, 0.0)), "velocity_mps")
    telemetry = VehicleTelemetry(
        timestamp_utc=utc_now(),
        time_s=int(frame.get("time_s", 0)),
        asset_id=str(frame.get("asset_id", "")),
        asset_kind=asset_kind,
        protocol="MAVLink2-compatible" if frame.get("link_profile") == "mavlink_udp" else str(frame.get("link_profile") or "unknown"),
        position=position,
        velocity_mps=velocity,
        heading_deg=float(frame.get("heading_deg", 0.0)),
        battery_wh=float(frame.get("battery_wh", 0.0)),
        link_id=frame.get("link_profile"),
        source=str(frame.get("source", frame.get("source_id", "scenario_or_edge"))),
        status=str(frame.get("status", "unknown")),
        raw_message_type="GLOBAL_POSITION_INT",
    )
    telemetry.validate()
    return telemetry


def protocol_monitor_snapshot(
    *,
    telemetry: list[VehicleTelemetry],
    commands: list[CommandEvent],
    tactical_messages: list[TacticalMessage],
    links: list[LinkState],
    alerts: list[AlertEvent],
    adapter_status: MavlinkAdapterStatus | None = None,
) -> dict[str, Any]:
    adapter = adapter_status or MockMavlinkAdapter().status()
    return {
        "schema_version": "dah-protocol-monitor.v1",
        "generated_at_utc": utc_now(),
        "mavlink_adapter": adapter.to_payload(),
        "telemetry": [item.to_payload() for item in telemetry],
        "commands": [item.to_payload() for item in commands],
        "tactical_messages": [item.to_payload() for item in tactical_messages],
        "links": [item.to_payload() for item in links],
        "alerts": [item.to_payload() for item in alerts],
        "safety_boundary": "Real MAVLink receive can be added later; command transmit remains dry-run in this harness.",
    }


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _position_tuple(value: Any, field_name: str) -> Position:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must contain three numeric values")
    return (float(value[0]), float(value[1]), float(value[2]))


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value