from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-tmmr-emulator", role="tmmr_queue_emulator", boundary="EMULATED / NOT REAL MILITARY SYSTEM", emulated=True, metrics=["queue_depth=0", "dropped_messages=0", "priority_starvation=false"])


if __name__ == "__main__":
    raise SystemExit(main())