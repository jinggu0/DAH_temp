from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-upper-c2", role="upper_c2_bms_simulator", boundary="EMULATED / NOT REAL MILITARY SYSTEM; TASKING VIA GCS ONLY", emulated=True, metrics=["situation_sharing=mock", "direct_vehicle_command=false"])


if __name__ == "__main__":
    raise SystemExit(main())