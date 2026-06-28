from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-defense-agent", role="rule_based_detection_and_response_recommendation", boundary="LOCAL DEFENSE MONITOR; NO REAL COMMAND EXECUTION", metrics=["executor=dry_run", "alert_source=dah-gcs"])


if __name__ == "__main__":
    raise SystemExit(main())