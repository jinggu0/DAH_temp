# Real UAS System Roadmap

현재 서비스는 정상 운용 시뮬레이션, REST API, 웹 UI, MAVLink-like JSON 메시지 모델을 갖춘
가상 UAS/UTM 환경입니다. 실제 UAS 관제 시스템으로 발전하려면 아래 순서로 경계를 넓힙니다.

## Stage 1. Live 관제 기반

목표:

- replay 조회형 UI를 live 관제형 UI로 확장
- 외부 telemetry adapter가 데이터를 밀어 넣을 수 있는 ingest API 확보
- 관제 화면이 서버 push로 최신 snapshot을 받도록 구성

구현 상태:

- `POST /api/telemetry/ingest`
- `GET /api/live/snapshot`
- `GET /api/live/stream` Server-Sent Events
- `TTA-UAS-UTM-SIM` schema version `1.1`
- UI `Live` 모드

다음 연결 대상:

- MAVLink UDP listener
- ROS2 topic bridge
- log replay adapter

## Stage 2. MAVLink Gateway

목표:

- 실제 MAVLink UDP/TCP stream을 수신
- `HEARTBEAT`, `GLOBAL_POSITION_INT`, `SYS_STATUS`, `MISSION_CURRENT`, `UTM_GLOBAL_POSITION`을 파싱
- 파싱 결과를 `POST /api/telemetry/ingest` payload로 변환

구현 방향:

- `src/uas_utm_gateway/mavlink_udp.py` 추가
- 초기에는 pymavlink 의존성을 optional extra로 둠
- `system_id/component_id`를 UAS asset ID와 매핑
- sequence gap, heartbeat timeout, link 상태를 별도 field로 기록

대회 확장:

- 본선이 MAVLink를 제공하면 gateway만 교체하고 UTM core와 UI는 유지
- binary MAVLink log를 replay 가능한 JSONL로 저장해 보고서 증거로 사용

## Stage 3. Mission and Command Gateway

목표:

- UTM 승인 mission을 vehicle mission protocol로 전달
- `MISSION_ITEM_INT` mission upload/download flow 구현
- command authority와 operator approval workflow 분리

구현 방향:

- `POST /api/missions/request`
- `POST /api/missions/{id}/approve`
- `POST /api/commands`
- command는 바로 송신하지 않고 authorization queue를 거침

대회 확장:

- 방어/공격 단계 전에는 정상 command flow baseline으로 사용
- 이후 비정상 command 탐지와 비교할 수 있는 감사 로그 확보

## Stage 4. Multi-Source Sensor Fusion

목표:

- MAVLink, ROS2, simulator, ADS-B/Remote ID style source를 같은 UTM track으로 통합
- 같은 asset에 대한 다중 source telemetry를 track confidence와 함께 병합

구현 방향:

- track table: asset_id, source_id, last_seen, confidence, position, velocity
- stale track timeout
- source priority와 C2 authority 반영

대회 확장:

- UAV/UGV 협동 운용으로 확장할 때 ground route source도 같은 track table에 병합

## Stage 5. Security and Certification Boundary

목표:

- transport security, message authentication, audit log, role-based access control 추가
- TTA 공식 표준번호 또는 본선 지정 프로토콜이 공개되면 envelope를 해당 schema에 맞춤

구현 방향:

- mTLS 또는 reverse proxy TLS
- MAVLink 2 signing 여부와 key rotation 상태 기록
- operator role: viewer, controller, approver, admin
- append-only audit log

대회 확장:

- 방어 아키텍처 문서에서 정상 관제 baseline과 보안 boundary를 명확히 설명

## Stage 6. Deployment

목표:

- Docker Compose에서 API/UI/gateway/logger를 분리
- simulator 또는 real gateway를 profile로 선택

구현 방향:

- `docker-compose.sim.yml`
- `docker-compose.gateway.yml`
- output volume에 telemetry, decision, audit log 저장

대회 확장:

- 제출 자료는 simulator profile로 재현 가능하게 유지
- 본선 환경에서는 gateway profile만 바꿔 연결
