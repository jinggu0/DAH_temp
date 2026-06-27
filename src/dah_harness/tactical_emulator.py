from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

ComponentStatus = Literal["normal", "degraded", "critical"]

ALLOWED_FAULT_TYPES = {
    "mavlink_plaintext_warning",
    "mission_count_reset_attempt",
    "c2_link_delay",
    "c2_link_packet_loss",
    "tmmr_queue_overflow",
    "ticn_route_metric_change",
    "upper_c2_command_mismatch",
}

SIMULATED_BOUNDARY = "SIMULATED / NOT REAL MILITARY SYSTEM"
REAL_OR_MOCK_BOUNDARY = "REAL UAS/MAVLINK-CAPABLE OR LOCAL MOCK"


@dataclass
class TacticalComponentState:
    component_id: str
    label: str
    role: str
    status: ComponentStatus = "normal"
    simulated: bool = True
    boundary: str = SIMULATED_BOUNDARY
    metrics: dict[str, int | float | str | bool] = field(default_factory=dict)

    def apply(self, *, status: ComponentStatus | None = None, **metrics: int | float | str | bool) -> None:
        if status:
            self.status = _worst_status([self.status, status])
        self.metrics.update(metrics)

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class TacticalLinkState:
    source: str
    target: str
    transport: str
    status: ComponentStatus = "normal"
    latency_ms: int = 0
    packet_loss_pct: float = 0.0
    simulated: bool = True
    boundary: str = SIMULATED_BOUNDARY

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class TacticalFaultEvent:
    fault_id: str
    fault_type: str
    target_component: str
    severity: str
    status: str
    created_at: str
    requested_by: str
    simulation_only: bool
    safety_boundary: str
    parameters: dict[str, Any]
    effects: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


class TacticalEmulatorRuntime:
    def __init__(self) -> None:
        self.components = _initial_components()
        self.fault_events: list[TacticalFaultEvent] = []

    def apply_fault(self, fault_type: str, *, requested_by: str = "operator", target: str | None = None, parameters: dict[str, Any] | None = None) -> TacticalFaultEvent:
        if fault_type not in ALLOWED_FAULT_TYPES:
            raise ValueError(f"fault_type is not allowlisted:{fault_type}")
        parameters = parameters or {}
        target_component = target or default_fault_target(fault_type)
        effects = self._apply_fault_effect(fault_type, target_component, parameters)
        event = TacticalFaultEvent(
            fault_id=str(uuid4()),
            fault_type=fault_type,
            target_component=target_component,
            severity=fault_severity(fault_type),
            status="injected",
            created_at=utc_now(),
            requested_by=requested_by,
            simulation_only=True,
            safety_boundary="No real attack traffic, tactical network traffic, wireless traffic, or actuator command is generated.",
            parameters=parameters,
            effects=effects,
        )
        self.fault_events.append(event)
        return event

    def component_status(self, component_id: str) -> ComponentStatus:
        component = self.components.get(component_id)
        return component.status if component else "normal"

    def snapshot(self) -> dict[str, Any]:
        components = [component.to_payload() for component in self.components.values()]
        links = [link.to_payload() for link in self._links()]
        return {
            "schema_version": "dah-tactical-emulator.v1",
            "generated_at_utc": utc_now(),
            "components": components,
            "links": links,
            "overall_status": _worst_status([component["status"] for component in components]),
            "fault_count": len(self.fault_events),
            "recent_faults": [event.to_payload() for event in self.fault_events[-20:]],
            "safety_boundary": "All tactical components are local emulators except UAS/MAVLink-capable edge integration points.",
        }

    def _apply_fault_effect(self, fault_type: str, target_component: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if fault_type == "mavlink_plaintext_warning":
            self.components["c2_link"].apply(status="degraded", plaintext_warning=True, authentication="missing_or_mock")
            return {"component": "c2_link", "plaintext_warning": True}
        if fault_type == "mission_count_reset_attempt":
            self.components["gcs"].apply(status="degraded", mission_sequence_guard="hold_for_operator_review", reset_attempts=_inc(self.components["gcs"], "reset_attempts"))
            return {"component": "gcs", "mission_sequence_guard": "hold_for_operator_review"}
        if fault_type == "c2_link_delay":
            latency_ms = int(parameters.get("latency_ms", 750))
            self.components["c2_link"].apply(status="degraded", latency_ms=latency_ms)
            return {"component": "c2_link", "latency_ms": latency_ms}
        if fault_type == "c2_link_packet_loss":
            packet_loss_pct = float(parameters.get("packet_loss_pct", 35.0))
            self.components["c2_link"].apply(status="critical", packet_loss_pct=packet_loss_pct)
            return {"component": "c2_link", "packet_loss_pct": packet_loss_pct}
        if fault_type == "tmmr_queue_overflow":
            queue_depth = int(parameters.get("queue_depth", 1250))
            self.components["router"].apply(status="degraded", reroute_required=True)
            self.components["tmmr"].apply(status="critical", queue_depth=queue_depth, dropped_messages=_inc(self.components["tmmr"], "dropped_messages", 12), priority_starvation=True)
            return {"component": "tmmr", "queue_depth": queue_depth, "priority_starvation": True}
        if fault_type == "ticn_route_metric_change":
            route_metric = int(parameters.get("route_metric", 90))
            self.components["router"].apply(status="degraded", route_recalculation=True)
            self.components["ticn"].apply(status="degraded", route_metric=route_metric, route_change_count=_inc(self.components["ticn"], "route_change_count"))
            return {"component": "ticn", "route_metric": route_metric}
        if fault_type == "upper_c2_command_mismatch":
            self.components["upper_c2"].apply(status="degraded", command_mismatch_count=_inc(self.components["upper_c2"], "command_mismatch_count"), dual_approval_required=True)
            return {"component": "upper_c2", "dual_approval_required": True}
        raise ValueError(f"fault_type is not implemented:{fault_type}")

    def _links(self) -> list[TacticalLinkState]:
        sequence = ["assets", "c2_link", "gcs", "router", "tmmr", "ticn", "upper_c2"]
        links = []
        for source, target in zip(sequence, sequence[1:]):
            left = self.components[source]
            right = self.components[target]
            status = _worst_status([left.status, right.status])
            latency = max(int(left.metrics.get("latency_ms", 0)), int(right.metrics.get("latency_ms", 0)))
            packet_loss = max(float(left.metrics.get("packet_loss_pct", 0.0)), float(right.metrics.get("packet_loss_pct", 0.0)))
            links.append(
                TacticalLinkState(
                    source=source,
                    target=target,
                    transport="REST_JSON/MAVLink/Tactical-Emulator",
                    status=status,
                    latency_ms=latency,
                    packet_loss_pct=packet_loss,
                    simulated=right.simulated,
                    boundary=right.boundary,
                )
            )
        return links


def default_fault_target(fault_type: str) -> str:
    if fault_type.startswith("tmmr"):
        return "tmmr"
    if fault_type.startswith("ticn"):
        return "ticn"
    if fault_type.startswith("upper_c2"):
        return "upper_c2"
    if fault_type.startswith("c2") or fault_type.startswith("mavlink"):
        return "c2_link"
    if fault_type.startswith("mission"):
        return "gcs"
    return "router"


def fault_severity(fault_type: str) -> str:
    if fault_type in {"tmmr_queue_overflow", "c2_link_packet_loss", "upper_c2_command_mismatch"}:
        return "critical"
    return "warning"


def tactical_alert_from_fault(event: TacticalFaultEvent) -> dict[str, Any]:
    return {
        "alert_id": event.fault_id,
        "timestamp_utc": event.created_at,
        "severity": event.severity,
        "category": "simulated_tactical_fault",
        "title": event.fault_type.replace("_", " ").title(),
        "target": event.target_component,
        "status": "open",
        "recommended_response": recommended_response(event.fault_type),
        "simulation_only": True,
        "effects": event.effects,
    }


def recommended_response(fault_type: str) -> str:
    mapping = {
        "mavlink_plaintext_warning": "Flag unauthenticated telemetry, preserve packets, and require signed/encrypted transport in the next profile.",
        "mission_count_reset_attempt": "Hold mission upload approval, compare mission sequence counters, and request operator confirmation.",
        "c2_link_delay": "Mark C2 link degraded and prefer local edge safety policy until delay clears.",
        "c2_link_packet_loss": "Switch to degraded-link playbook and stop non-essential work dispatch.",
        "tmmr_queue_overflow": "Throttle low-priority tactical messages and preserve queue metrics for analysis.",
        "ticn_route_metric_change": "Freeze route decision baseline and compare route metric deltas against allowlisted changes.",
        "upper_c2_command_mismatch": "Require dual approval before any command leaves the GCS queue.",
    }
    return mapping.get(fault_type, "Review simulated event and keep real command execution disabled.")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _initial_components() -> dict[str, TacticalComponentState]:
    return {
        "assets": TacticalComponentState("assets", "UAV/UGV Edge Assets", "edge_integration", simulated=False, boundary=REAL_OR_MOCK_BOUNDARY, metrics={"registered_assets": 0}),
        "c2_link": TacticalComponentState("c2_link", "C2 Data Link", "mavlink_rest_gateway", simulated=False, boundary=REAL_OR_MOCK_BOUNDARY, metrics={"latency_ms": 0, "packet_loss_pct": 0.0}),
        "gcs": TacticalComponentState("gcs", "GCS / UTM Service", "approval_and_monitoring", simulated=False, boundary="Docker local service", metrics={"approval_queue": "dry_run"}),
        "router": TacticalComponentState("router", "Virtual Tactical Router / TIPS", "routing_emulator", metrics={"reroute_required": False}),
        "tmmr": TacticalComponentState("tmmr", "TMMR Emulator", "radio_queue_emulator", metrics={"queue_depth": 0, "dropped_messages": 0, "priority_starvation": False}),
        "ticn": TacticalComponentState("ticn", "TICN-like Network", "route_metric_emulator", metrics={"route_metric": 10, "route_change_count": 0}),
        "upper_c2": TacticalComponentState("upper_c2", "Upper C2/BMS Simulator", "upper_command_consistency_check", metrics={"command_mismatch_count": 0, "dual_approval_required": False}),
    }


def _inc(component: TacticalComponentState, key: str, amount: int = 1) -> int:
    value = int(component.metrics.get(key, 0)) + amount
    component.metrics[key] = value
    return value


def _worst_status(statuses: list[str]) -> ComponentStatus:
    if "critical" in statuses:
        return "critical"
    if "degraded" in statuses:
        return "degraded"
    return "normal"


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value