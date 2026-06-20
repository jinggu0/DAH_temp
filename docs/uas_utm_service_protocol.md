# UAS/UTM Service Protocol and Deployment

이 문서는 실행 가능한 UAS/UTM 가상 서비스의 REST API, live telemetry API, 표준형 메시지 envelope,
UI/UX, Docker 실행 방법을 정리합니다.

## 표준형 프로토콜 프로파일

본 구현은 공식 TTA 인증 구현이 아니라, 국내 표준 문서에 일반적으로 요구되는 추적성,
시간 기준, 메시지 유형, payload 분리를 맞춘 시뮬레이션 프로파일입니다.

프로파일:

- name: `TTA-UAS-UTM-SIM`
- schema version: `1.1`
- REST transport: HTTP/1.1 JSON
- live push: Server-Sent Events
- stream export: JSONL telemetry

공통 envelope:

```json
{
  "protocol": "TTA-UAS-UTM-SIM",
  "schema_version": "1.1",
  "message_id": "uuid",
  "trace_id": "uuid",
  "timestamp_utc": "2026-06-20T00:00:00Z",
  "source": "uas-utm-service",
  "message_type": "utm.telemetry.live",
  "payload": {}
}
```

## MAVLink 매핑

MAVLink 공식 common message set과 mission protocol을 기준으로 정상 운용 메시지를 생성합니다.

| Service field | MAVLink mapping |
| --- | --- |
| asset heartbeat | `HEARTBEAT` |
| position telemetry | `GLOBAL_POSITION_INT` |
| battery/link status | `SYS_STATUS` |
| active mission | `MISSION_CURRENT` |
| approved route | `MISSION_ITEM_INT` |
| UTM position sharing | `UTM_GLOBAL_POSITION` |

참고:

- https://mavlink.io/en/messages/common.html
- https://mavlink.io/en/services/mission.html
- https://mavlink.io/en/guide/message_signing.html

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | 웹 대시보드 |
| GET | `/api/health` | 서비스 상태 |
| GET | `/api/protocol` | 프로토콜 프로파일 |
| GET | `/api/scenario` | 자산, 공역, C2 노드, mission |
| GET | `/api/summary` | 실행 요약 |
| GET | `/api/decisions` | UTM 승인/거절 결과 |
| GET | `/api/timeline` | replay tick 목록 |
| GET | `/api/telemetry?time_s=120` | 특정 시점 simulation telemetry snapshot |
| GET | `/api/live/snapshot?time_s=120` | simulation snapshot + external ingest snapshot |
| GET | `/api/live/stream?interval_ms=1000` | SSE live telemetry stream |
| POST | `/api/telemetry/ingest` | 외부 adapter telemetry ingest |
| GET | `/api/mavlink?asset_id=muav-male-isr-01&limit=50` | MAVLink 메시지 샘플 |

## Telemetry Ingest Payload

`POST /api/telemetry/ingest`는 envelope 또는 raw payload를 모두 받을 수 있습니다.

```json
{
  "payload": {
    "asset_id": "external-uas-01",
    "time_s": 12,
    "position": [10, 20, 90],
    "velocity_mps": [1.5, 0.0, 0.0],
    "heading_deg": 90,
    "mission_id": null,
    "status": "external-live",
    "battery_wh": 100,
    "c2_node_id": "ground-control-east",
    "link_profile": "mavlink_udp",
    "source": "mavlink-udp-adapter"
  }
}
```

## UI/UX 구성

- 공역 map: operating area, no-fly zone, restricted altitude zone
- C2 node 위치
- mission route overlay
- replay slider와 `Play` 버튼
- `Live` 버튼: SSE stream으로 최신 snapshot 수신
- asset별 상태, mission, C2 link, 배터리, source
- UTM 승인/거절 목록
- MAVLink 메시지 카운트

## 로컬 실행

```powershell
$env:PYTHONPATH = "src"
python -m uas_utm_service.server `
  --host 127.0.0.1 `
  --port 8080 `
  --scenario scenarios/korea_defense_uas_utm_ops.json
```

브라우저에서 `http://127.0.0.1:8080`을 엽니다.

## Docker 실행

```bash
docker build -t dah-uas-utm-service .
docker run --rm -p 8080:8080 dah-uas-utm-service
```

## Docker Compose 실행

```bash
docker compose up --build
```

## 실제 UAS 발전 방향

세부 로드맵은 `docs/uas_real_system_roadmap.md`를 기준으로 진행합니다.

1. Live telemetry ingest와 SSE push
2. MAVLink UDP/TCP gateway
3. Mission/command gateway
4. Multi-source sensor fusion
5. 인증, 서명, 감사 로그
6. Docker Compose profile 분리
