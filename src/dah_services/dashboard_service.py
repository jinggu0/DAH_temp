from __future__ import annotations

from dah_runtime.reverse_proxy import main as reverse_proxy_main


def main(argv: list[str] | None = None) -> int:
    return reverse_proxy_main(argv or ["--host", "0.0.0.0", "--port", "8080", "--target", "http://dah-gcs:8080"])


if __name__ == "__main__":
    raise SystemExit(main())