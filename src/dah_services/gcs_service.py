from __future__ import annotations

from uas_utm_service.server import main as uas_utm_service_main


def main(argv: list[str] | None = None) -> int:
    return uas_utm_service_main(argv or ["--host", "0.0.0.0", "--port", "8080", "--scenario", "scenarios/korea_defense_uas_utm_ops.json", "--log-dir", "logs/uas_utm"])


if __name__ == "__main__":
    raise SystemExit(main())