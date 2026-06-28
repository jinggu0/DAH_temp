from __future__ import annotations

from uas_utm_edge.agent import main as edge_main


def main(argv: list[str] | None = None) -> int:
    return edge_main(argv or ["--service-url", "http://dah-gcs:8080", "--edge-id", "edge-dashboard-ugv-01", "--device-type", "ugv_edge", "--asset", "ground-convoy-01", "--authority", "ROKA Ground Robotics Cell", "--link-profile", "mesh_ground", "--software-version", "dashboard-edge-0.1", "--emit-sample-telemetry"])


if __name__ == "__main__":
    raise SystemExit(main())