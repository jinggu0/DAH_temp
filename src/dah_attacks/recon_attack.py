"""
Silent Reconnaissance (무음 정찰) 공격
독창 시나리오 #11 | USENIX Security 2023 "API Surface Enumeration for CPS"

사전 공격 단계: 어떤 흔적도 남기지 않고(GET 요청만 사용)
GCS API를 체계적으로 열거해 이후 공격의 정밀도를 극대화한다.

수집 정보:
  - 모든 자산 ID, 미션 ID, 엣지 디바이스 ID
  - 현재 승인 대기 커맨드 목록 (intercept 가능한 command_id)
  - 현재 승인 대기 미션 업로드 목록
  - 실제 운용 중인 엣지 ID (heartbeat 타이밍 파악)
  - source_registry 구조 (FDI 공격 파라미터 최적화)
  - 타임라인 범위 (Timestamp Rollback 공격 파라미터 최적화)
  - 감사 로그 패턴 (Alert Fatigue 공격 최적화)

결과 리포트를 JSON으로 출력 → 후속 공격 컨테이너에 전달
"""
from __future__ import annotations

import argparse
import json
import time
from .common import GcsClient, wait_for_gcs

# 열거할 GET 엔드포인트 목록
ENDPOINTS = [
    ("/api/health",              "헬스 체크"),
    ("/api/scenario",            "시나리오 구조 (자산·미션·구역)"),
    ("/api/timeline",            "타임라인 범위 (Rollback 파라미터)"),
    ("/api/tracks",              "현재 항적 (자산 위치·신뢰도)"),
    ("/api/edge/devices",        "등록된 엣지 디바이스 목록"),
    ("/api/commands",            "커맨드 큐 전체 (command_id 수집)"),
    ("/api/mission-uploads",     "미션 업로드 큐"),
    ("/api/operation-profile",   "source_registry (FDI 파라미터)"),
    ("/api/alerts",              "활성 경보 목록"),
    ("/api/service-status",      "서비스 상태"),
    ("/api/summary",             "운영 요약"),
    ("/api/dashboard",           "대시보드 전체"),
    ("/api/chain",               "전술 체인 상태"),
    ("/api/protocol-monitor",    "프로토콜 모니터"),
    ("/api/mavlink",             "MAVLink 메시지 이력"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Silent Reconnaissance 공격")
    parser.add_argument("--service-url",     default="http://dah-gcs:8080")
    parser.add_argument("--repeat-interval", type=float, default=30.0,
                        help="정찰 반복 간격 (s, 0=1회만)")
    parser.add_argument("--duration-s",      type=float, default=60.0)
    parser.add_argument("--output-file",     default="/tmp/recon_report.json")
    args = parser.parse_args(argv)

    client = GcsClient(args.service_url)
    wait_for_gcs(client)

    print("[recon] 무음 정찰 시작 — GET 요청만 사용, 감사 로그에 기록 없음", flush=True)

    start = time.time()
    run = 0

    while (time.time() - start) < args.duration_s:
        run += 1
        report: dict = {
            "recon_run": run,
            "timestamp": time.time(),
            "service_url": args.service_url,
            "findings": {},
        }

        for path, label in ENDPOINTS:
            try:
                data = client.get(path)
                payload = data.get("payload", data)
                report["findings"][path] = {"label": label, "ok": True, "data": payload}
                print(f"[recon] ✓ {path:35s} — {label}", flush=True)
            except Exception as e:
                report["findings"][path] = {"label": label, "ok": False, "error": str(e)}
                print(f"[recon] ✗ {path:35s} — {e}", flush=True)

        # 핵심 정보 요약 추출
        _summarize(report)

        # 리포트 저장
        try:
            with open(args.output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            print(f"[recon] 리포트 저장: {args.output_file}", flush=True)
        except Exception as e:
            print(f"[recon] 리포트 저장 실패: {e}", flush=True)

        if args.repeat_interval <= 0:
            break
        remaining = args.duration_s - (time.time() - start)
        if remaining > 0:
            time.sleep(min(args.repeat_interval, remaining))

    print("[recon] 정찰 종료", flush=True)
    return 0


def _summarize(report: dict) -> None:
    findings = report["findings"]
    summary = {}

    # 자산 ID 목록
    scenario = (findings.get("/api/scenario") or {}).get("data", {})
    if isinstance(scenario, dict):
        assets = scenario.get("assets", [])
        summary["asset_ids"] = [a.get("id") for a in assets if isinstance(a, dict)]
        summary["mission_ids"] = [m.get("id") for m in scenario.get("missions", []) if isinstance(m, dict)]

    # 타임라인 (Rollback 파라미터)
    tl = (findings.get("/api/timeline") or {}).get("data", {})
    if isinstance(tl, dict):
        summary["timeline_end_s"] = tl.get("end_s")
        summary["step_s"] = tl.get("step_s")
        summary["stale_threshold_s"] = max(10, (tl.get("step_s") or 1) * 3)

    # 엣지 디바이스 (합법 엣지 ID 목록)
    edge_payload = (findings.get("/api/edge/devices") or {}).get("data", {})
    if isinstance(edge_payload, dict):
        summary["edge_ids"] = [
            e.get("edge_id") for e in edge_payload.get("edge_devices", [])
            if isinstance(e, dict) and not str(e.get("edge_id", "")).startswith("edge-attack")
        ]

    # 커맨드 큐 (intercept 가능한 pending command_id)
    cmd_payload = (findings.get("/api/commands") or {}).get("data", {})
    if isinstance(cmd_payload, dict):
        pending = [
            c.get("command_id") for c in cmd_payload.get("commands", [])
            if isinstance(c, dict) and c.get("status") == "pending_approval"
        ]
        summary["pending_command_ids"] = pending

    # source_registry (FDI 파라미터)
    op_profile = (findings.get("/api/operation-profile") or {}).get("data", {})
    if isinstance(op_profile, dict):
        summary["source_registry"] = [
            {"id": s.get("source_id"), "confidence": s.get("base_confidence")}
            for s in op_profile.get("source_registry", [])
            if isinstance(s, dict)
        ]

    report["attack_intelligence"] = summary

    print(
        f"\n[recon] ★ 정찰 요약:\n"
        f"  자산: {summary.get('asset_ids')}\n"
        f"  미션: {summary.get('mission_ids')}\n"
        f"  합법 엣지: {summary.get('edge_ids')}\n"
        f"  대기 커맨드: {summary.get('pending_command_ids')}\n"
        f"  source_registry: {summary.get('source_registry')}\n"
        f"  stale 임계: {summary.get('stale_threshold_s')}s\n",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
