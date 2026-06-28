from __future__ import annotations

from .common import run_role_service


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        from dah_runtime.role_service import main as role_service_main
        return role_service_main(argv)
    return run_role_service(service_id="dah-fault-injector", role="allowlisted_fault_injection_demo", boundary="CYBER LAB SIMULATION ONLY; NO REAL ATTACK TRAFFIC", metrics=["allowlist=mavlink_plaintext_warning,mission_count_reset_attempt,c2_link_delay,c2_link_packet_loss,tmmr_queue_overflow,ticn_route_metric_change,upper_c2_command_mismatch"])


if __name__ == "__main__":
    raise SystemExit(main())