"""
DAH Attack Runner — 통합 공격 시나리오 실행기
모든 공격 시나리오를 단일 dah-attack 컨테이너 안에서 관리.

환경 변수:
  DAH_ATTACK_SCENARIOS  실행할 시나리오 이름(쉼표 구분) 또는 "all"
                        기본값: "all"
  DAH_GCS_URL           GCS 서비스 URL  기본값: http://dah-gcs:8080

CLI:
  python -m dah_attacks.attack_runner [--scenarios NAMES] [--service-url URL] [--list]

시나리오 이름 목록:
  gnss-drift, link-degrade, dynamic-spoof, sync-disrupt, cmd-inject,
  sybil-fleet, fdi-fusion, alert-fatigue, timestamp-rollback, battery-crisis,
  recon, edge-work-snooping, mission-queue-exhaust, audit-flood,
  priority-escalation, mimicry, geofence-inject, multi-vector-blitz

예시:
  # 전체 실행 (Docker 기본)
  python -m dah_attacks.attack_runner --scenarios all

  # 개별/조합 실행
  python -m dah_attacks.attack_runner --scenarios recon,fdi-fusion,mimicry

  # Docker Compose 환경변수 오버라이드
  DAH_ATTACK_SCENARIOS=gnss-drift,alert-fatigue docker compose --profile cyber-attack up dah-attack
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from typing import NamedTuple


# ── 시나리오 레지스트리 ────────────────────────────────────────────────────────
# (모듈명, [기본 파라미터 리스트])
# --service-url 은 runner 가 동적으로 주입

class ScenarioSpec(NamedTuple):
    module: str
    args: list[str]
    label: str


def _registry(service_url: str) -> dict[str, ScenarioSpec]:
    """서비스 URL을 주입한 시나리오 레지스트리 반환"""
    U = ["--service-url", service_url]
    return {
        # ── 1차: PDF 유사 시나리오 ─────────────────────────────────────────
        "gnss-drift": ScenarioSpec(
            "dah_attacks.gnss_drift_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--spoof-edge-id", "edge-attack-gnss-01",
                 "--drift-rate", "0.6", "--duration-s", "120"],
            "GNSS Drift 누적",
        ),
        "link-degrade": ScenarioSpec(
            "dah_attacks.link_degrade_attack",
            U + ["--target-edge", "edge-dronebot-01",
                 "--degrade-rate", "0.025", "--duration-s", "90"],
            "링크 저하 Fail-safe 유도",
        ),
        "dynamic-spoof": ScenarioSpec(
            "dah_attacks.dynamic_spoof_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--spoof-edge-id", "edge-attack-dynspoof-01",
                 "--orbit-radius", "120", "--duration-s", "100"],
            "동역학 일치 GPS 스푸핑",
        ),
        "sync-disrupt": ScenarioSpec(
            "dah_attacks.sync_disrupt_attack",
            U + ["--target-asset", "ground-convoy-01",
                 "--spoof-edge-id", "edge-attack-sync-01",
                 "--duration-s", "90"],
            "협동 임무 동기화 교란",
        ),
        "cmd-inject": ScenarioSpec(
            "dah_attacks.cmd_inject_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--repeat", "3", "--interval-s", "4"],
            "Command Injection",
        ),
        # ── 2차: 어드벤스드 (FDI/Sybil/Alert) ────────────────────────────
        "sybil-fleet": ScenarioSpec(
            "dah_attacks.sybil_fleet_attack",
            U + ["--fleet-size", "12", "--interval-s", "1.0", "--duration-s", "120"],
            "Sybil 유령 함대",
        ),
        "fdi-fusion": ScenarioSpec(
            "dah_attacks.fdi_fusion_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--hijack-source", "mavlink-udp-adapter",
                 "--interval-s", "0.8", "--duration-s", "100"],
            "Track Fusion FDI",
        ),
        "alert-fatigue": ScenarioSpec(
            "dah_attacks.alert_fatigue_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--phase1-duration", "45",
                 "--interval-s", "1.5", "--inject-every", "5"],
            "Alert Fatigue + 은닉 Command Injection",
        ),
        # ── 3차: 코드 분석 기반 ────────────────────────────────────────────
        "timestamp-rollback": ScenarioSpec(
            "dah_attacks.timestamp_rollback_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--stale-time-s", "0",
                 "--interval-s", "1.0", "--duration-s", "90"],
            "Timestamp Rollback 포이즈닝",
        ),
        "battery-crisis": ScenarioSpec(
            "dah_attacks.battery_crisis_attack",
            U + ["--warmup-ticks", "8", "--crisis-battery", "1.5",
                 "--interval-s", "1.2", "--duration-s", "80"],
            "Battery Crisis 동시 스푸핑",
        ),
        "recon": ScenarioSpec(
            "dah_attacks.recon_attack",
            U + ["--repeat-interval", "30", "--duration-s", "120"],
            "Silent Reconnaissance",
        ),
        # ── 4차: API 취약점 직접 공략 ──────────────────────────────────────
        "edge-work-snooping": ScenarioSpec(
            "dah_attacks.edge_work_snooping_attack",
            U + ["--interval-s", "8.0", "--duration-s", "120"],
            "Edge Work Queue Snooping + ACK Spoofing",
        ),
        "mission-queue-exhaust": ScenarioSpec(
            "dah_attacks.mission_queue_exhaust_attack",
            U + ["--burst-count", "150", "--burst-rounds", "3", "--duration-s", "90"],
            "Mission Upload Queue Exhaustion",
        ),
        "audit-flood": ScenarioSpec(
            "dah_attacks.audit_flood_attack",
            U + ["--target-events", "8000", "--burst-size", "50", "--duration-s", "120"],
            "Audit Hash Chain Disconnection",
        ),
        "priority-escalation": ScenarioSpec(
            "dah_attacks.priority_escalation_attack",
            U + ["--attack-priority", "0", "--spam-priority", "-999",
                 "--inject-count", "5", "--duration-s", "90"],
            "Command Priority Escalation",
        ),
        "mimicry": ScenarioSpec(
            "dah_attacks.mimicry_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--drift-per-tick", "0.05",
                 "--interval-s", "1.0", "--duration-s", "120"],
            "Mimicry 정상 동작 모방",
        ),
        "geofence-inject": ScenarioSpec(
            "dah_attacks.geofence_inject_attack",
            U + ["--target-asset", "small-dronebot-01",
                 "--spoof-edge-id", "edge-attack-geofence-01",
                 "--interval-s", "2.0", "--duration-s", "90"],
            "Geofence Violation Injection",
        ),
        "multi-vector-blitz": ScenarioSpec(
            "dah_attacks.multi_vector_blitz_attack",
            U + ["--duration-s", "180"],
            "Multi-Vector Blitz 킬체인",
        ),
    }


# ── 프로세스 관리 ──────────────────────────────────────────────────────────────

class AttackProcess:
    def __init__(self, name: str, spec: ScenarioSpec):
        self.name = name
        self.spec = spec
        self.proc: subprocess.Popen | None = None
        self.started_at: float = 0.0
        self.exit_code: int | None = None

    def start(self) -> None:
        cmd = [sys.executable, "-m", self.spec.module] + self.spec.args
        print(f"[runner] ▶  {self.name:30s} | {self.spec.label}", flush=True)
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.started_at = time.time()

    def poll(self) -> bool:
        """True = 아직 실행 중"""
        if self.proc is None:
            return False
        rc = self.proc.poll()
        if rc is not None:
            self.exit_code = rc
            return False
        return True

    def terminate(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def elapsed(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0


def _drain_logs(procs: list[AttackProcess]) -> None:
    """모든 자식 프로세스 stdout 비동기 출력 (non-blocking)"""
    import select
    fds = {p.proc.stdout.fileno(): p for p in procs if p.proc and p.proc.stdout}
    if not fds:
        return
    try:
        readable, _, _ = select.select(list(fds.keys()), [], [], 0.1)
    except (ValueError, OSError):
        return
    for fd in readable:
        proc_obj = fds[fd]
        try:
            line = proc_obj.proc.stdout.readline()
            if line:
                tag = f"[{proc_obj.name}]"
                print(f"{tag:25s} {line}", end="", flush=True)
        except OSError:
            pass


# ── 메인 실행 루프 ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DAH 통합 공격 시나리오 런처",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--service-url",
        default=os.environ.get("DAH_GCS_URL", "http://dah-gcs:8080"),
    )
    parser.add_argument(
        "--scenarios",
        default=os.environ.get("DAH_ATTACK_SCENARIOS", "all"),
        help="실행할 시나리오 이름(쉼표 구분) 또는 'all'",
    )
    parser.add_argument(
        "--stagger-s", type=float, default=2.0,
        help="시나리오 간 시작 지연 (s, 기본 2s)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="사용 가능한 시나리오 이름 출력 후 종료",
    )
    args = parser.parse_args(argv)

    registry = _registry(args.service_url)

    if args.list:
        print("사용 가능한 시나리오:")
        for name, spec in registry.items():
            print(f"  {name:30s} — {spec.label}")
        return 0

    # 실행 대상 결정
    if args.scenarios.strip().lower() == "all":
        targets = list(registry.keys())
    else:
        targets = [s.strip() for s in args.scenarios.split(",") if s.strip()]
        unknown = [t for t in targets if t not in registry]
        if unknown:
            print(f"[runner] 알 수 없는 시나리오: {unknown}", flush=True)
            print(f"[runner] 사용 가능: {list(registry.keys())}", flush=True)
            return 1

    print(
        "=" * 62 + "\n"
        f"[runner] DAH Attack Runner 시작\n"
        f"  GCS URL    : {args.service_url}\n"
        f"  시나리오수 : {len(targets)}개\n"
        f"  시작 간격  : {args.stagger_s}s\n"
        f"  실행 목록  : {', '.join(targets)}\n" +
        "=" * 62,
        flush=True,
    )

    # 모든 시나리오 시작
    attack_procs: list[AttackProcess] = []
    for name in targets:
        ap = AttackProcess(name, registry[name])
        ap.start()
        attack_procs.append(ap)
        time.sleep(args.stagger_s)

    print(f"\n[runner] {len(attack_procs)}개 시나리오 실행 중 — Ctrl+C 로 중단\n", flush=True)

    # 종료 시그널 처리
    def _shutdown(signum, frame):  # noqa: ANN001
        print("\n[runner] 종료 신호 수신 — 모든 공격 프로세스 종료 중…", flush=True)
        for ap in attack_procs:
            ap.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 상태 모니터링 루프
    while True:
        _drain_logs(attack_procs)

        alive = [ap for ap in attack_procs if ap.poll()]
        finished = [ap for ap in attack_procs if ap.exit_code is not None]
        failed = [ap for ap in finished if ap.exit_code != 0]

        if not alive:
            break

        # 30초마다 상태 요약 출력
        if int(time.time()) % 30 == 0:
            print(
                f"\n[runner] ── 상태 ── "
                f"실행중={len(alive)} 완료={len(finished)} 실패={len(failed)}",
                flush=True,
            )
            for ap in alive:
                print(f"  ▶  {ap.name:30s} {ap.elapsed():.0f}s 경과", flush=True)
            time.sleep(1.1)  # 중복 출력 방지

        time.sleep(0.3)

    # 종료 요약
    finished = [ap for ap in attack_procs if ap.exit_code is not None]
    failed = [ap for ap in finished if ap.exit_code != 0]
    print(
        f"\n[runner] ★ 모든 시나리오 종료\n"
        f"  성공: {len(finished) - len(failed)}개\n"
        f"  실패: {len(failed)}개"
        + (f"\n  실패 목록: {[ap.name for ap in failed]}" if failed else ""),
        flush=True,
    )
    return len(failed)


if __name__ == "__main__":
    raise SystemExit(main())
