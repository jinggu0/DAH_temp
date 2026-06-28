from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-telemetry-collector", role="telemetry_command_fault_audit_collector", boundary="LOCAL JSONL LOG COLLECTION ROLE", metrics=["storage=jsonl", "log_dir=/app/logs"])


if __name__ == "__main__":
    raise SystemExit(main())