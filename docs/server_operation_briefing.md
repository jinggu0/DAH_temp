# DAH UAS/UTM 서버 작동 브리핑 개요

상세 운영/분석 자료: `docs/server_operation_detailed_briefing.md`

## 목적

이 문서는 구현된 UAS/UTM 서버를 발표할 때 사용할 요약 자료다. 상세한 프로토콜, 외부 송수신, 로그 분석 명령, 문제 진단 절차는 상세 문서를 기준으로 한다.

## 핵심 설명

현재 서버는 UAV/UGV가 포함된 UAS/UTM 정상 운용 환경을 Docker로 실행하고, REST API, Dashboard, MAVLink gateway, edge device agent, append-only audit log, AI agent용 observation view를 제공한다.

## 주요 구성

| 구성 | 역할 |
| --- | --- |
| UAS/UTM Service | REST API, Dashboard, scenario/mission/track/log 관리 |
| Telemetry Gateway | UDP 14550 MAVLink telemetry 수신 |
| Bidirectional MAVLink Gateway | UDP 14551 telemetry 수신 및 승인 command/mission 송신 |
| Edge Agent | UAV/UGV edge device register, heartbeat, work poll, ACK 모의 |
| Audit Log Store | `logs/uas_utm/audit.jsonl` append-only 로그 저장 |
| Agent View | `/api/logs/agent-view`로 공격/방어 agent용 관측값 제공 |

## 발표 핵심 메시지

1. 이 서버는 단순 지도 UI가 아니라 UAS/UTM workflow simulator다.
2. 모든 command/mission은 approval queue를 거친다.
3. 외부 UAV/UGV 또는 SITL은 MAVLink UDP로 송수신할 수 있다.
4. 핵심 이벤트는 append-only JSONL과 hash-chain으로 증적화된다.
5. AI agent는 `/api/logs/agent-view`에서 risk, label, feature, defense question을 받을 수 있다.
6. 현재는 대회 준비와 시나리오 설계에 적합하며, 본대회 운영에는 scoring, reset, team isolation이 추가로 필요하다.

## 빠른 데모 순서

```bash
docker compose up --build
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/edge/devices
curl "http://127.0.0.1:8080/api/logs/agent-view?limit=50&include_heartbeat=false"
curl http://127.0.0.1:8080/api/logs/verify
```

브라우저에서 `http://127.0.0.1:8080`을 열고 Dashboard의 Command Approval, Mission Upload Approval, Audit Timeline, Log Storage 패널을 시연한다.
