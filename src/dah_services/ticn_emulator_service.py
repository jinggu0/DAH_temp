from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-ticn-emulator", role="ticn_like_route_metric_emulator", boundary="EMULATED / NOT REAL MILITARY SYSTEM", emulated=True, metrics=["route_metric=10", "route_change_count=0", "gateway_status=mock"])


if __name__ == "__main__":
    raise SystemExit(main())