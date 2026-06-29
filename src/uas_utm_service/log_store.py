from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "uas-utm-audit-log.v1.1"
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
SENSITIVE_TOKENS = (
    "password",
    "passwd",
    "token",
    "secret",
    "credential",
    "authorization",
    "api_key",
    "private_key",
    "signing_key",
    "signature",
)


@dataclass(frozen=True)
class LogPolicy:
    storage_model: str = "append_only_jsonl"
    timestamp: str = "ISO-8601 UTC"
    integrity: str = "sha256_hash_chain"
    rotation: str = "size_based"
    sensitivity: str = "redact_secrets_and_credentials"
    retention: str = "scenario_defined_or_operator_managed"


class JsonlAuditStore:
    def __init__(self, root_dir: Path, *, max_bytes: int = DEFAULT_MAX_BYTES):
        self.root_dir = root_dir
        self.max_bytes = max_bytes
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.current_path = self.root_dir / "audit.jsonl"
        self.manifest_path = self.root_dir / "manifest.json"
        self._last_hash = self._load_last_hash()
        self._write_manifest()

    def append(self, *, event_type: str, data: dict[str, Any], source: str = "uas-utm-service") -> dict[str, Any]:
        self._rotate_if_needed()
        created_at = _now()
        redacted_data = redact_sensitive(data)
        actor = _actor_from(redacted_data)
        object_id = _object_id_from(redacted_data)
        object_type = _object_type_from(event_type, redacted_data)
        row: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": str(uuid4()),
            "event_type": event_type,
            "created_at": created_at,
            "timestamp_utc": created_at,
            "source": source,
            "actor": actor,
            "object_type": object_type,
            "object_id": object_id,
            "outcome": str(redacted_data.get("status") or redacted_data.get("result") or "recorded"),
            "severity": _severity_for(event_type),
            "data": redacted_data,
            "integrity": {
                "algorithm": "sha256",
                "previous_hash": self._last_hash,
            },
            "control_mapping": ["NIST-SP-800-92", "NIST-SP-800-53-AU", "OWASP-Logging-Cheat-Sheet"],
        }
        row["agent_view"] = agent_observation(row)
        row_hash = event_hash(row)
        row["integrity"]["event_hash"] = row_hash
        with self.current_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._last_hash = row_hash
        self._write_manifest()
        return row

    def tail(self, *, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, limit)
        if event_type:
            rows = self._read_rows()
            rows = [row for row in rows if row.get("event_type") == event_type]
            return rows[-limit:]
        return self._read_tail_rows(limit)

    def status(self) -> dict[str, Any]:
        return {
            "profile": SCHEMA_VERSION,
            "storage_root": str(self.root_dir),
            "current_file": str(self.current_path),
            "event_count": self._count_rows(),
            "last_hash": self._last_hash,
            "policy": self.policy(),
        }

    def verify(self) -> dict[str, Any]:
        previous_hash: str | None = None
        errors: list[dict[str, Any]] = []
        checked = 0
        for index, row in enumerate(self._read_rows()):
            checked += 1
            integrity = row.get("integrity", {}) if isinstance(row.get("integrity"), dict) else {}
            expected_previous = integrity.get("previous_hash")
            if expected_previous != previous_hash:
                errors.append({"line": index + 1, "error": "previous_hash_mismatch"})
            actual_hash = integrity.get("event_hash")
            row_without_hash = json.loads(json.dumps(row, ensure_ascii=False))
            row_without_hash.get("integrity", {}).pop("event_hash", None)
            expected_hash = event_hash(row_without_hash)
            if actual_hash != expected_hash:
                errors.append({"line": index + 1, "error": "event_hash_mismatch"})
            previous_hash = actual_hash
        return {
            "valid": not errors,
            "checked_count": checked,
            "last_hash": previous_hash,
            "errors": errors,
        }

    @staticmethod
    def policy() -> dict[str, str]:
        policy = LogPolicy()
        return {
            "storage_model": policy.storage_model,
            "timestamp": policy.timestamp,
            "integrity": policy.integrity,
            "rotation": policy.rotation,
            "sensitivity": policy.sensitivity,
            "retention": policy.retention,
        }

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.current_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.current_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def _read_tail_rows(self, limit: int) -> list[dict[str, Any]]:
        if not self.current_path.exists():
            return []
        limit = max(1, limit)
        chunk_size = 8192
        data = b""
        with self.current_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            while position > 0 and data.count(b"\n") <= limit:
                read_size = min(chunk_size, position)
                position -= read_size
                handle.seek(position)
                data = handle.read(read_size) + data
        lines = [line.strip() for line in data.splitlines() if line.strip()]
        return [json.loads(line.decode("utf-8")) for line in lines[-limit:]]

    def _count_rows(self) -> int:
        if not self.current_path.exists():
            return 0
        count = 0
        with self.current_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                count += chunk.count(b"\n")
        return count

    def _load_last_hash(self) -> str | None:
        rows = self._read_tail_rows(1)
        if not rows:
            return None
        integrity = rows[-1].get("integrity", {})
        return str(integrity.get("event_hash")) if integrity.get("event_hash") else None

    def _rotate_if_needed(self) -> None:
        if not self.current_path.exists() or self.current_path.stat().st_size < self.max_bytes:
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive = self.root_dir / f"audit-{stamp}.jsonl"
        self.current_path.rename(archive)
        self._last_hash = None

    def _write_manifest(self) -> None:
        manifest = {
            "profile": SCHEMA_VERSION,
            "generated_at_utc": _now(),
            "current_file": self.current_path.name,
            "last_hash": self._last_hash,
            "policy": self.policy(),
        }
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")



def agent_observation(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data", {}) if isinstance(row.get("data"), dict) else {}
    event_type = str(row.get("event_type", "unknown"))
    labels = _agent_labels(event_type, data)
    features = _agent_features(event_type, data)
    return {
        "observation_id": row.get("event_id"),
        "timestamp_utc": row.get("timestamp_utc") or row.get("created_at"),
        "event_type": event_type,
        "event_family": event_type.split(".", 1)[0] if "." in event_type else event_type,
        "phase": _agent_phase(event_type),
        "perspectives": ["blue_defense", "red_scenario_planning"],
        "subject": {
            "actor": row.get("actor", "system"),
            "source": row.get("source", "unknown"),
            "role_guess": _role_guess(str(row.get("actor", "system")), event_type),
        },
        "object": {
            "type": row.get("object_type"),
            "id": row.get("object_id"),
            "asset_id": data.get("asset_id"),
            "mission_id": data.get("mission_id"),
        },
        "action": event_type.split(".")[-1],
        "outcome": row.get("outcome"),
        "severity": row.get("severity"),
        "risk_score": _risk_score(event_type, data),
        "labels": labels,
        "features": features,
        "defense_questions": _defense_questions(event_type, data),
        "scenario_hooks": _scenario_hooks(event_type, data),
        "safety_note": "Simulation planning metadata only; does not contain exploit steps or actuator instructions.",
    }


def _agent_phase(event_type: str) -> str:
    if event_type.startswith("command."):
        return "c2_command_workflow"
    if event_type.startswith("mission_upload."):
        return "mission_planning_workflow"
    if event_type.startswith("edge_work."):
        return "edge_execution_feedback"
    if event_type.startswith("edge_device."):
        return "edge_registration_health"
    if event_type.startswith("telemetry."):
        return "tracking_and_fusion"
    return "service_operation"


def _agent_labels(event_type: str, data: dict[str, Any]) -> list[str]:
    labels = ["audit", _agent_phase(event_type)]
    if event_type.startswith("command."):
        labels.extend(["control_plane", "operator_approval"])
    if event_type.startswith("mission_upload."):
        labels.extend(["mission_plane", "mavlink_mission"])
    if event_type.startswith("edge"):
        labels.extend(["edge_boundary", "device_trust"])
    if data.get("asset_id"):
        labels.append("asset_scoped")
    if data.get("status") == "approved_for_gateway":
        labels.append("gateway_dispatch_ready")
    if event_type.endswith(".rejected"):
        labels.append("blocked_or_denied")
    if "ack" in event_type:
        labels.append("execution_feedback")
    return sorted(set(labels))


def _agent_features(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_command": event_type.startswith("command."),
        "is_mission_upload": event_type.startswith("mission_upload."),
        "is_edge_event": event_type.startswith("edge"),
        "has_asset": bool(data.get("asset_id")),
        "has_mission": bool(data.get("mission_id")),
        "priority": _int_or_none(data.get("priority")),
        "status_approved_for_gateway": data.get("status") == "approved_for_gateway",
        "status_rejected": data.get("status") == "rejected" or event_type.endswith(".rejected"),
        "edge_acknowledged": "ack" in event_type,
        "mavlink_command": _nested_get(data, "mavlink_command", "command"),
        "mavlink_message_name": _nested_get(data, "mavlink_command", "message_name"),
        "mavlink_item_count": len(data.get("mavlink_items", [])) if isinstance(data.get("mavlink_items"), list) else 0,
    }


def _defense_questions(event_type: str, data: dict[str, Any]) -> list[str]:
    if event_type == "command.requested":
        return [
            "Is the requester authorized for this asset and command type?",
            "Does the command align with the active UTM-approved mission?",
            "Is a second approval required before gateway dispatch?",
        ]
    if event_type == "command.approved":
        return [
            "Was approval performed by a distinct approver?",
            "Should the edge device receive this command within the expected time window?",
        ]
    if event_type.startswith("mission_upload."):
        return [
            "Do all mission items match the approved UTM route and corridor?",
            "Is the mission upload scoped to the correct asset system id?",
        ]
    if event_type.startswith("edge_device."):
        return [
            "Is the edge identity expected for this asset assignment?",
            "Do heartbeat health values match normal operating bounds?",
        ]
    if "ack" in event_type:
        return ["Did edge acknowledgement arrive from the assigned device and expected link profile?"]
    return ["Does this event match the scenario baseline and expected operator workflow?"]


def _scenario_hooks(event_type: str, data: dict[str, Any]) -> list[str]:
    hooks: list[str] = []
    if event_type == "command.requested":
        hooks.append("unauthorized_or_mistimed_command_request_candidate")
    if event_type == "command.approved":
        hooks.append("approval_chain_validation_candidate")
    if event_type.startswith("mission_upload."):
        hooks.append("route_or_mission_integrity_validation_candidate")
    if event_type.startswith("edge_device."):
        hooks.append("edge_identity_and_health_validation_candidate")
    if "ack" in event_type:
        hooks.append("edge_feedback_latency_and_origin_validation_candidate")
    return hooks or ["baseline_sequence_validation_candidate"]


def _risk_score(event_type: str, data: dict[str, Any]) -> float:
    score = 0.1
    if event_type.startswith("command."):
        score += 0.25
    if event_type.startswith("mission_upload."):
        score += 0.2
    if data.get("status") == "approved_for_gateway":
        score += 0.2
    if event_type.endswith(".rejected"):
        score += 0.25
    if "ack" in event_type:
        score += 0.15
    priority = _int_or_none(data.get("priority"))
    if priority is not None:
        score += max(0, 5 - priority) * 0.03
    return round(min(score, 1.0), 3)


def _role_guess(actor: str, event_type: str) -> str:
    lowered = actor.lower()
    if "edge" in lowered or event_type.startswith("edge"):
        return "edge_gateway"
    if "approver" in lowered or event_type.endswith(".approved") or event_type.endswith(".rejected"):
        return "approver"
    if "operator" in lowered or event_type.endswith(".requested"):
        return "operator"
    return "service"


def _nested_get(data: dict[str, Any], outer: str, inner: str) -> Any:
    value = data.get(outer)
    if isinstance(value, dict):
        return value.get(inner)
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def event_hash(row: dict[str, Any]) -> str:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in SENSITIVE_TOKENS)


def _actor_from(data: dict[str, Any]) -> str:
    for key in ("requested_by", "approved_by", "rejected_by", "approver", "rejector", "edge_id", "source_id"):
        value = data.get(key)
        if value:
            return str(value)
    return "system"


def _object_id_from(data: dict[str, Any]) -> str | None:
    for key in ("command_id", "upload_id", "mission_id", "edge_id", "asset_id"):
        value = data.get(key)
        if value:
            return str(value)
    return None


def _object_type_from(event_type: str, data: dict[str, Any]) -> str:
    if event_type.startswith("command."):
        return "command"
    if event_type.startswith("mission_upload."):
        return "mission_upload"
    if event_type.startswith("edge_device."):
        return "edge_device"
    if event_type.startswith("edge_work."):
        return "edge_work"
    if event_type.startswith("edge."):
        return "edge_device"
    if event_type.startswith("telemetry."):
        return "telemetry"
    if data.get("asset_id"):
        return "asset"
    return "system"


def _severity_for(event_type: str) -> str:
    if event_type.endswith(".rejected") or event_type.endswith(".failed"):
        return "warning"
    if "ack" in event_type or event_type.endswith(".approved"):
        return "notice"
    return "info"


def _now() -> str:
    return datetime.now(UTC).isoformat()
