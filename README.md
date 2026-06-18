# DAH_temp

DAH_SMU 레포에 올릴 UAS/UAV/UGV 가상 테스트 환경입니다.

DAH 2026 예선을 위한 UAV/UGV 방산 AI 사이버 보안 테스트 하네스를 이 저장소에서 먼저
구현하고 검증합니다.

이 저장소의 1차 목표는 본선 시뮬레이터가 공개되기 전에도 공격 시나리오, 방어 에이전트,
튜닝 지표를 반복 검증할 수 있는 경량 하네스를 갖추는 것입니다. 본선 인터페이스가 공개되면
`src/dah_harness`의 시뮬레이션 입출력만 ROS2/MAVLink/Gazebo 어댑터로 교체하는 구조로
확장합니다.

## 현재 구현 범위

- UAV/UGV convoy 시나리오 JSON
- GPS spoofing, command injection, link jamming 공격 주입
- 규칙 기반 방어 에이전트와 대응 액션 생성
- 탐지율, 평균 탐지 지연, 오탐 수, 미션 진행률 측정
- threshold override를 통한 빠른 튜닝
- `unittest` 기반 회귀 테스트
- Docker 실행 경로

## 빠른 실행

Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m dah_harness.cli --scenario scenarios/uav_ugv_convoy.json --output output/harness_summary.json
python -m unittest discover -s tests
```

또는:

```powershell
.\scripts\run_harness.ps1
```

Docker:

```bash
docker build -t dah-smu-harness .
docker run --rm -v "$PWD/output:/app/output" dah-smu-harness
```

## 튜닝 예시

방어 threshold는 실행 시 덮어쓸 수 있습니다.

```powershell
$env:PYTHONPATH = "src"
python -m dah_harness.cli `
  --scenario scenarios/uav_ugv_convoy.json `
  --set route_deviation_threshold_m=45 `
  --set link_loss_threshold_s=4 `
  --output output/tuned_summary.json
```

결과 JSON의 `metrics`에서 `detection_rate`, `mean_detection_latency_s`,
`false_positive_actions`, `mission_progress`를 비교해 threshold를 조정합니다.

## 제출 패키지 구성

DAH 예선 안내서의 부가자료 권장 구조에 맞춰 다음 구성을 유지합니다.

```text
README.md
src/                     # 에이전트 및 하네스 코드
scenarios/               # 공격/방어 검증 시나리오
tests/                   # 회귀 테스트
docs/                    # 안내서 요약, 스택, 아키텍처, 보고서 근거
requirements.txt
Dockerfile
```

## 다음 확장 우선순위

1. ROS2/Gazebo 또는 PX4/ArduPilot SITL 어댑터 추가
2. MAVLink/ROS topic replay를 하네스 입력으로 수집
3. 공격/방어 에이전트를 LLM planner와 규칙 기반 executor로 분리
4. 반복 튜닝 결과를 `output/experiments/`에 누적하고 보고서 표/그림으로 변환
5. 데모 영상용 runbook과 스크린샷 자동 생성

## 예선 산출물 기준

- 보고서 마감: 2026-07-10 23:59 KST
- 본선 진출팀 발표: 2026-07-31
- 본선 예정: 2026-08-21
- 평가 중심: 공격 시나리오 30점, 방어 전략 25점, AI 에이전트 아키텍처 25점
