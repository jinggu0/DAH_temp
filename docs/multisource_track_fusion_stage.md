# Multi-Source Track Fusion Stage

## 목표

이번 단계는 UAS/UTM 서비스가 단일 telemetry 화면이 아니라 여러 출처의 항적을 하나의 UTM track으로 융합하도록 확장한다.
공개된 한국 방산 업체의 UAV 사업 구분에서 반복되는 플랫폼, 임무장비, C2/지상통제, 데이터링크, 운용지원 구조를 일반화해 반영한다.

## 구현 범위

- `GET /api/operation-profile`
  - 플랫폼, 임무장비, C2/지상통제, 데이터링크, 운용지원 domain을 제공한다.
  - viewer, operator, approver, gateway, admin 역할을 분리한다.
- `GET /api/tracks`
  - 시뮬레이터 frame과 외부 ingest frame을 같은 track table로 융합한다.
  - source별 confidence, authority, age, stale 여부를 보존한다.
  - 대표 source는 stale 여부와 confidence 기준으로 선택한다.
- `POST /api/telemetry/ingest`
  - `source_id`, `source_authority`, `track_confidence` 필드를 받을 수 있다.
- UI
  - Track Fusion 지표와 Fused Track Table을 추가한다.

## 실제 대회 확장 방향

- 실제 MAVLink UDP/TCP gateway가 들어오면 `source_id`를 gateway별로 분리한다.
- ROS2, Remote ID, ADS-B 유사 feed를 추가할 때도 `/api/tracks`만 바라보게 만들어 UI와 UTM 판단 로직을 유지한다.
- 방산 운용 시나리오에서는 임무장비 source와 C2 source를 분리해 같은 asset에 여러 authority가 붙는 상황을 훈련한다.
- 취약점 분석 단계로 넘어가기 전에는 stale track, source confidence, 승인된 command queue를 정상 baseline으로 고정한다.

## 공식 구조 반영 원칙

- 공식 공개 자료에서 확인 가능한 사업/운용 구조만 일반화한다.
- 특정 업체의 비공개 명칭, 성능, 내부 프로토콜은 추정하지 않는다.
- 구현은 DAH 테스트용 가상환경이며 실제 방산 체계의 복제물이 아니다.

참고:

- KAI UAV 사업 공개 페이지: https://www.koreaaero.com/EN/Business/UAV.aspx
