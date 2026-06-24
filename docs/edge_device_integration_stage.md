# Edge Device Integration Stage

## 목적

UAS/UTM 중앙 서비스와 외부 UAV/UGV edge device가 같은 메시지 체계로 통신할 수 있는 구조를 추가한다.
이 단계는 실제 장비를 직접 구동하지 않는다. 중앙 서비스는 승인된 work queue만 제공하고, edge agent는 local safety interlock을 통과해야만 하위 장비 계층으로 넘긴다는 경계를 둔다.

## 역할 분리

| 역할 | 책임 | 구현 위치 |
| --- | --- | --- |
| viewer | scenario, track, audit 조회 | UAS/UTM UI/API |
| operator | command, mission upload 요청 | `/api/commands/request`, `/api/mission-uploads/request` |
| approver | command/mission 승인 또는 반려 | `/api/commands/approve`, `/api/commands/reject` |
| edge_gateway | 외부 UAV/UGV edge 등록, heartbeat, telemetry ingest, approved work polling | `src/uas_utm_edge/agent.py` |
| maintainer | device health, audit, profile rotation 확인 | `/api/edge/devices`, `/api/audit` |
| admin | 서비스와 source profile 운영 | service deployment |

## API

- `POST /api/edge/devices/register`
  - `edge_id`, `device_type`, `asset_ids`, `capabilities`, `link_profiles`, `authority`를 등록한다.
- `POST /api/edge/devices/heartbeat`
  - edge health와 link quality를 갱신한다.
- `GET /api/edge/devices`
  - 등록된 edge device와 상태를 조회한다.
- `GET /api/edge/work?edge_id=...`
  - 해당 edge가 맡은 asset의 `approved_for_gateway` command와 mission upload만 반환한다.
- `POST /api/edge/work/ack`
  - edge가 command 또는 mission upload 수신 결과를 감사 로그에 남긴다.
- `POST /api/telemetry/ingest`
  - edge agent가 UAV/UGV telemetry를 UTM track fusion으로 보낸다.

## 배치

PowerShell:

```powershell
.\scripts\run_uas_utm_service.ps1
.\scripts\run_uas_utm_edge.ps1 -Once -EmitSampleTelemetry
```

Docker Compose:

```bash
docker compose up --build uas-utm-service uas-utm-edge-dronebot
```

## 실제 대회 확장 방향

- edge agent를 장비별 container 또는 SBC 서비스로 배포한다.
- 실제 MAVLink/ROS2/serial adapter는 edge agent 안쪽 plugin으로 넣고, 중앙 UTM API는 그대로 유지한다.
- command는 항상 중앙 승인 후 work queue로만 내려가게 한다.
- edge는 local geofence, link state, arm/disarm safety, operator presence 같은 현장 interlock을 통과한 후에만 장비 adapter로 전달한다.
- UGV는 같은 edge registry를 사용하되 `device_type=ugv_edge`, asset id, route/position adapter만 바꾼다.

## 공식 구조 반영 원칙

KAI 공식 UAV 사업 페이지처럼 공개적으로 확인 가능한 platform, mission payload, C2/ground control, datalink, operation support 축만 일반화한다.
비공개 성능, 실전 운용 절차, 업체 내부 프로토콜은 구현하거나 추정하지 않는다.

참고: https://www.koreaaero.com/EN/Business/UAV.aspx
