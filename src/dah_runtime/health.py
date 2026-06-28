from __future__ import annotations

from typing import Any

from .service_contracts import ServiceStatus, make_service_status


def health_payload(status: ServiceStatus) -> dict[str, Any]:
    return {"ok": status.status != "critical", **status.to_payload()}


def status_payload(
    *,
    service_id: str,
    role: str,
    status: str = "normal",
    emulated: bool = False,
    boundary: str = "local Docker service",
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return make_service_status(
        service_id=service_id,
        role=role,
        status=status,  # type: ignore[arg-type]
        emulated=emulated,
        boundary=boundary,
        metrics=metrics or {},
    ).to_payload()