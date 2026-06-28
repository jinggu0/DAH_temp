from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-tactical-router", role="virtual_tactical_router_tips", boundary="EMULATED / NOT REAL MILITARY SYSTEM", emulated=True, metrics=["route_table=mock", "reroute_required=false"])


if __name__ == "__main__":
    raise SystemExit(main())