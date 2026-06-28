from __future__ import annotations

from dah_runtime.role_service import main as role_service_main


def run_role_service(
    *,
    service_id: str,
    role: str,
    boundary: str,
    metrics: list[str] | None = None,
    emulated: bool = False,
) -> int:
    argv = [
        "--host", "0.0.0.0",
        "--port", "8080",
        "--service-id", service_id,
        "--role", role,
        "--boundary", boundary,
    ]
    if emulated:
        argv.append("--emulated")
    for metric in metrics or []:
        argv.extend(["--metric", metric])
    return role_service_main(argv)