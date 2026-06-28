from __future__ import annotations

from uas_utm_edge.agent import main as edge_main


def main(argv: list[str] | None = None) -> int:
    return edge_main(argv or ["--service-url", "http://dah-gcs:8080", "--edge-id", "edge-dashboard-uav-01", "--device-type", "uav_edge", "--asset", "small-dronebot-01", "--authority", "ROKA UTM Cell", "--software-version", "dashboard-edge-0.1", "--emit-sample-telemetry"])


if __name__ == "__main__":
    raise SystemExit(main())