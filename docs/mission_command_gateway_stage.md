# Mission and Command Gateway Stage

이 단계는 실제 UAS 관제 시스템에서 가장 중요한 안전 경계 중 하나인 mission/command 승인 체계를
구현합니다. 한국 공식 방산 업체들이 공개한 체계 구성을 참고해 플랫폼, 임무장비, 지휘통제,
데이터링크, 운용지원의 역할을 분리하는 방향으로 설계했습니다.

## 구현 원칙

- operator 요청과 gateway 송신을 분리합니다.
- command는 생성 즉시 송신하지 않습니다.
- mission upload는 UTM이 승인한 mission만 큐에 들어갑니다.
- 승인된 command/upload만 gateway dispatch API에서 조회됩니다.
- 모든 요청, 승인, 거절은 audit log에 남깁니다.

## 공식 방산 구조 반영

KAI 공식 UAV 페이지는 RQ-101 군단급 UAV, 차기 군단급 무인기, VTOL/UCAV 선행연구와 함께
정찰 UAV의 군 운용 신뢰성, ISR 임무, 지상통제/운용지원 축을 공개합니다. 이 서비스는 특정
실제 업체 시스템을 복제하지 않고, 공개 구조를 다음 소프트웨어 경계로 반영합니다.

| 공개 구조 축 | 서비스 구현 |
| --- | --- |
| UAV platform | `asset_id`, platform class, system/component id |
| ISR/payload | mission required payload, mission type |
| Ground control / C2 | command request, approval authority, C2 node |
| Datalink | MAVLink gateway, gateway dispatch queue |
| Operational support | audit log, mission upload state, Docker deployment |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/commands/request` | operator command 요청 |
| POST | `/api/commands/approve` | command 승인 |
| POST | `/api/commands/reject` | command 거절 |
| GET | `/api/commands?status=pending_approval` | command queue 조회 |
| GET | `/api/gateway/commands` | gateway가 승인된 command 조회 |
| POST | `/api/mission-uploads/request` | 승인 mission의 upload 요청 |
| POST | `/api/mission-uploads/approve` | mission upload 승인 |
| GET | `/api/mission-uploads?status=pending_approval` | mission upload queue 조회 |
| GET | `/api/gateway/mission-uploads` | gateway가 승인된 mission upload 조회 |
| GET | `/api/audit` | 감사 로그 조회 |

## Command 예

```json
{
  "payload": {
    "asset_id": "small-dronebot-01",
    "command_type": "hold_position",
    "requested_by": "operator-a",
    "priority": 2,
    "params": {}
  }
}
```

승인 후 gateway 조회 결과에는 `COMMAND_LONG` 형태의 `mavlink_command`가 포함됩니다.

## Mission Upload 예

```json
{
  "payload": {
    "mission_id": "dronebot-local-recon",
    "requested_by": "operator-a"
  }
}
```

승인 후 gateway 조회 결과에는 `MISSION_ITEM_INT` 목록이 포함됩니다.

## 다음 확장

1. Gateway가 approved queue를 poll한 뒤 송신 완료 상태로 전환
2. MAVLink `COMMAND_ACK`, `MISSION_ACK` 수신 처리
3. operator role과 approval role 분리
4. command TTL, emergency override, two-person rule
5. append-only audit log 파일 저장
