from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

PROFILE_NAME = "TTA-UAS-UTM-SIM"
PROFILE_VERSION = "1.3"


def envelope(
    *,
    message_type: str,
    payload: Any,
    source: str = "uas-utm-service",
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "protocol": PROFILE_NAME,
        "schema_version": PROFILE_VERSION,
        "message_id": str(uuid4()),
        "trace_id": trace_id or str(uuid4()),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "source": source,
        "message_type": message_type,
        "payload": _normalize(payload),
    }


def protocol_profile() -> dict[str, Any]:
    return {
        "profile": PROFILE_NAME,
        "version": PROFILE_VERSION,
        "certification_note": "Simulation profile aligned to standard-style Korean UAS/UTM message envelopes; not an official TTA certification.",
        "transport": {
            "rest": "HTTP/1.1 JSON",
            "live_push": "Server-Sent Events over HTTP",
            "stream_export": "JSONL telemetry",
            "container": "Docker image exposing TCP/8080",
        },
        "message_envelope": {
            "protocol": "string",
            "schema_version": "string",
            "message_id": "uuid",
            "trace_id": "uuid",
            "timestamp_utc": "ISO-8601 UTC",
            "source": "string",
            "message_type": "string",
            "payload": "object|array",
        },
        "normal_operation_messages": [
            "utm.health",
            "utm.scenario",
            "utm.summary",
            "utm.decisions",
            "utm.telemetry.snapshot",
            "utm.telemetry.ingest",
            "utm.telemetry.live",
            "utm.tracks",
            "utm.operation_profile",
            "utm.mavlink.messages",
            "utm.command.request",
            "utm.command.approve",
            "utm.command.reject",
            "utm.mission_upload.request",
            "utm.mission_upload.approve",
            "utm.audit",
        ],
        "telemetry_ingest_payload": {
            "asset_id": "string, required",
            "time_s": "integer seconds",
            "position": "[x_m, y_m, z_m], required",
            "velocity_mps": "[vx, vy, vz]",
            "heading_deg": "float",
            "mission_id": "string|null",
            "status": "string",
            "battery_wh": "float",
            "c2_node_id": "string|null",
            "link_profile": "string|null",
            "source": "external adapter id",
            "source_id": "stable source id for fusion",
            "source_authority": "source owner or C2 authority",
            "track_confidence": "0.0-1.0 optional source confidence",
        },
        "track_fusion_payload": {
            "track_count": "integer",
            "mode": "single_source|fused",
            "tracks": [
                {
                    "asset_id": "string",
                    "fused_position": "[x_m, y_m, z_m]",
                    "confidence": "0.0-1.0",
                    "primary_source_id": "simulation|mavlink-udp-adapter|...",
                    "sources": "per-source samples with age/stale/authority",
                }
            ],
        },
        "command_payload": {
            "asset_id": "string, required",
            "command_type": "hold_position|return_to_launch|set_mode|goto|land",
            "params": "object",
            "requested_by": "operator id",
            "priority": "integer",
            "safety": "commands are queued and never transmitted until approved",
        },
        "mission_upload_payload": {
            "mission_id": "UTM-approved mission id",
            "requested_by": "operator id",
            "output": "MISSION_ITEM_INT list queued for gateway",
        },
        "mavlink_mapping": {
            "heartbeat": "HEARTBEAT",
            "position": "GLOBAL_POSITION_INT",
            "status": "SYS_STATUS",
            "mission_state": "MISSION_CURRENT",
            "mission_plan": "MISSION_ITEM_INT",
            "command": "COMMAND_LONG",
            "utm_position": "UTM_GLOBAL_POSITION",
        },
    }


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value
