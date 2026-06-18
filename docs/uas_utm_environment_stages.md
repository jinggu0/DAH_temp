# UAS/UTM Virtual Environment Stages

이 문서는 DAH 1단계 가상환경 구축 계획과 구현 범위를 정리합니다. 이 단계에서는 취약점,
공격, 방어 분석을 다루지 않고 정상 UAS/UTM 운용만 검증합니다.

## Stage 1. 데이터 모델과 공역 정의

구현 범위:

- UAV asset schema: ID, callsign, 시작 위치, 순항 속도, 운용 고도, 배터리
- Mission schema: asset, route, 요청 시간, 목적, 명목 속도
- Airspace schema: operating area, no-fly zone, restricted altitude zone
- Telemetry schema: 시간, 위치, mission 상태, 다음 waypoint, 배터리

현재 구현 파일:

- `src/uas_utm/models.py`
- `src/uas_utm/airspace.py`
- `scenarios/normal_utm_ops.json`

대회 확장 방향:

- 본선 simulator가 제공하는 UAV/UGV 상태 메시지를 `TelemetryFrame`으로 정규화
- 실제 공역 좌표계가 주어지면 local Cartesian 좌표를 WGS84/ENU 좌표계로 교체
- UGV가 포함되면 route schema에 road segment, terrain constraint, depot를 추가

## Stage 2. UTM 승인 서비스

구현 범위:

- mission 접수 후 승인 또는 거절 판단
- operating area 이탈 검사
- no-fly zone 침범 검사
- asset별 고도 제한 검사
- mission 간 시간/공간 충돌 가능성 검사

현재 구현 파일:

- `src/uas_utm/utm_service.py`
- `tests/test_uas_utm.py`

대회 확장 방향:

- 본선 운영 규칙이 공개되면 승인 정책을 rule set으로 분리
- UAS Traffic Management 관점에서 strategic deconfliction과 tactical deconfliction을 분리
- 다수 팀/다수 asset 환경이면 priority, emergency override, reserved corridor를 추가

## Stage 3. 정상 운용 시뮬레이터

구현 범위:

- 승인된 mission만 실행
- discrete-time tick 기반 waypoint 이동
- asset별 telemetry 생성
- 배터리 감소량 기록
- 재현 가능한 summary와 telemetry JSONL 출력

현재 구현 파일:

- `src/uas_utm/simulator.py`
- `src/uas_utm/cli.py`
- `scripts/run_uas_utm.ps1`

대회 확장 방향:

- Gazebo, PX4 SITL, ArduPilot SITL, ROS2 simulator에서 나오는 실제 위치를 telemetry source로 연결
- simulator adapter를 추가해 현재 UTM core를 교체 없이 재사용
- demo 영상용 2D map replay 또는 live dashboard를 추가

## Stage 4. 실행 산출물과 회귀 테스트

구현 범위:

- `python -m uas_utm.cli` 실행 경로
- `output/uas_utm_summary.json` 생성
- `output/uas_utm_telemetry.jsonl` 생성
- `unittest` 기반 정상 운용 검증

실행 명령:

```powershell
$env:PYTHONPATH = "src"
python -m uas_utm.cli `
  --scenario scenarios/normal_utm_ops.json `
  --output output/uas_utm_summary.json `
  --telemetry-output output/uas_utm_telemetry.jsonl
python -m unittest discover -s tests
```

대회 확장 방향:

- 보고서에는 approval/rejection log, telemetry frame 수, mission completion을 정상 운용 baseline으로 제시
- 이후 단계에서 취약점 분석을 시작할 때 이 baseline과 비교할 수 있도록 output artifact를 고정
- 제출 ZIP에는 `scenarios/`, `src/uas_utm/`, `tests/`, `docs/uas_utm_environment_stages.md`를 포함

## 현재 완료 기준

- 정상 mission 2개 승인
- no-fly zone 침범 mission 1개 거절
- 3개 UAV에 대해 전체 duration telemetry 생성
- summary JSON과 telemetry JSONL 생성
- 회귀 테스트 통과

## 아직 하지 않는 것

- 취약점 분석
- 공격 시나리오 설계
- 방어 에이전트 설계
- MAVLink/ROS2 message mutation
- cyber scoring metric
