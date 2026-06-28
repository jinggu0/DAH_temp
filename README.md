# DAH 2026 — UAS/UGV 사이버 방어 시뮬레이션

> DAH 2026 예선을 위한 UAV/UGV 방산 사이버 보안 로컬 사이버 레인지.
> Docker Desktop 하나로 UAV/UGV/GCS/전술 체인/방어 에이전트를 역할별 컨테이너로 실행합니다.

---

## 구현 범위

| 구분 | 내용 |
|---|---|
| **실제 구현 가능** | UAS/UGV 텔레메트리 수신, MAVLink-compatible UDP 파싱, GCS 커맨드·미션 승인 큐, JSONL 감사 로그 |
| **에뮬레이터 전용** | Tactical Router/TIPS, TMMR, TICN-like Network, Upper C2/BMS |
| **미구현·금지** | 실제 군 통신망, 실제 TICN/TMMR 프로토콜, 무선 공격, 외부 IP 공격, 실제 액추에이터 명령 |

> **에뮬레이터 역할은 대시보드와 API 응답에 `EMULATED / NOT REAL MILITARY SYSTEM` 으로 명시됩니다.**

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  DAH UAS/UGV Cyber Range  [로컬 Docker 전용]             │
├─────────────────────────────────────────────────────────────────────────┤
│  dah-asset-net  (UAV/UGV Mock 텔레메트리 구간)                           │
│                                                                         │
│  ┌──────────────────┐    ┌──────────────────┐                           │
│  │   dah-uav-sim    │    │   dah-ugv-sim    │                           │
│  │  UAV Simulator   │    │  UGV Simulator   │                           │
│  │  Autopilot mock  │    │  Controller mock │                           │
│  │  MAVLink-like    │    │  ROS2/MQTT-like  │                           │
│  └────────┬─────────┘    └────────┬─────────┘                           │
│           │                       │                                     │
│  ┌────────▼───────────────────────▼──────────┐                          │
│  │   dah-mavlink-gateway      UDP :14550      │                          │
│  │   dah-bidir-mavlink-gateway UDP :14551     │  MAVLink-compatible      │
│  │   로컬 UDP 파싱·텔레메트리 수신            │  실제 파서 구현됨        │
│  └────────────────────┬──────────────────────┘                          │
├────────────────────────┼────────────────────────────────────────────────┤
│  dah-ops-net  (GCS·대시보드·수집·방어 구간)  │                           │
│                        │                                                │
│           ┌────────────▼─────────────┐                                  │
│           │        dah-gcs           │  HTTP :8080                      │
│           │   GCS / UTM Service      │                                  │
│           │   텔레메트리 수신         │                                  │
│           │   커맨드 승인 큐          │                                  │
│           │   미션 업로드 승인        │                                  │
│           │   JSONL 감사 로그         │                                  │
│           └──┬──────┬──────┬─────────┘                                  │
│              │      │      │                                             │
│   ┌──────────┘      │      └──────────────┐                              │
│   │                 │                      │                             │
│   ▼                 ▼                      ▼                             │
│ dah-defense-   dah-dashboard         dah-telemetry                      │
│   agent        (→dah-gcs proxy)       -collector                        │
│   방어 탐지·     전체 상태 UI           로그 수집                        │
│   대응 권고                                                               │
│                                                                         │
│  ┌──────────────────────────────────────────┐                           │
│  │              dah-gateway                 │  HTTP :9000               │
│  │        reverse proxy → dashboard         │  ← 단일 진입점            │
│  └──────────────────────────────────────────┘                           │
├─────────────────────────────────────────────────────────────────────────┤
│  dah-tactical-net  [EMULATED / NOT REAL MILITARY SYSTEM]                │
│                                                                         │
│  ┌──────────────────┐    ┌───────────────────┐    ┌──────────────────┐  │
│  │ dah-tactical-    │ →  │ dah-tmmr-emulator │ →  │ dah-ticn-        │  │
│  │   router         │    │  큐/대역폭 에뮬    │    │   emulator       │  │
│  │ virtual routing  │    │  [에뮬레이터]      │    │ 라우트 메트릭    │  │
│  └──────────────────┘    └───────────────────┘    └───────┬──────────┘  │
│                                                           │              │
│                                               ┌───────────▼───────────┐  │
│                                               │     dah-upper-c2      │  │
│                                               │  Upper C2/BMS Sim.    │  │
│                                               │  GCS 경유 명령만 허용  │  │
│                                               │  [에뮬레이터]          │  │
│                                               └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Docker Desktop 실행

### 기본 실행 (mock/demo 모드)

```bash
docker compose up -d --build
```

### 대시보드 접속

```
http://localhost:9000
```

### 기존 UTM API 호환 엔드포인트

```
http://localhost:8080
```

### 중지

```bash
docker compose down
```

### Cyber Lab 프로파일 (폴트 주입 데모 전용)

```bash
docker compose --profile cyber-lab up -d --build
```

### Sample Edge 프로파일 (엣지 디바이스 샘플)

```bash
docker compose --profile sample-edge up -d --build
```

---

## 컨테이너 목록

| 컨테이너 | 역할 | 경계 |
|---|---|---|
| `dah-gateway` | reverse proxy, 단일 진입점 (:9000) | 로컬 전용 |
| `dah-dashboard` | 대시보드 UI proxy | 로컬 전용 |
| `dah-gcs` | GCS/UTM 서비스, 모든 REST API (:8080) | **실제 구현 가능** |
| `dah-uav-sim` | UAV mock 텔레메트리 에이전트 | mock mode |
| `dah-ugv-sim` | UGV mock 텔레메트리 에이전트 | mock mode |
| `dah-mavlink-gateway` | MAVLink UDP 수신·파싱 (:14550) | **실제 MAVLink 가능** |
| `dah-bidir-mavlink-gateway` | 양방향 MAVLink 게이트웨이 (:14551) | **실제 MAVLink 가능** |
| `dah-tactical-router` | virtual tactical router/TIPS | **에뮬레이터** |
| `dah-tmmr-emulator` | TMMR 큐·대역폭 에뮬레이터 | **에뮬레이터** |
| `dah-ticn-emulator` | TICN-like 라우트 메트릭 에뮬레이터 | **에뮬레이터** |
| `dah-upper-c2` | Upper C2/BMS 시뮬레이터 | **에뮬레이터** |
| `dah-telemetry-collector` | JSONL 로그 수집 역할 | 로컬 전용 |
| `dah-defense-agent` | 규칙 기반 방어 탐지·대응 권고 | dry-run 전용 |
| `dah-fault-injector` *(cyber-lab)* | 폴트 주입 데모 | simulation-only |

---

## 주요 포트

| 포트 | 서비스 | 설명 |
|---|---|---|
| `9000` | `dah-gateway` | 단일 대시보드 진입점 |
| `8080` | `dah-gcs` | GCS/UTM REST API (하위 호환) |
| `14550/udp` | `dah-mavlink-gateway` | MAVLink UDP 수신 |
| `14551/udp` | `dah-bidir-mavlink-gateway` | 양방향 MAVLink |

---

## 대시보드 사용법

`http://localhost:9000` 접속 후 확인 가능한 항목:

| 패널 | 내용 |
|---|---|
| **상단 카드** | UAV Sim / UGV Sim / GCS / C2 Data Link / Tactical Router / TMMR / TICN / Upper C2 / Defense Agent / Telemetry Collector 상태 |
| **Tactical Protocol Chain** | UAV/UGV → C2 → GCS → Router → TMMR → TICN → Upper C2 체인 흐름, 각 노드 상태(normal/degraded/critical) |
| **Protocol Console** | 헬스 체크, UGV 등록/heartbeat/텔레메트리, 커맨드 요청·승인, 미션 업로드 요청·승인, 감사 로그 검증 |
| **Alerts** | 시뮬레이션 탐지 경보 목록 |
| **Defense Decisions** | 방어 에이전트 대응 결정 |
| **Fault Injection Events** | 주입된 폴트 이벤트 |
| **Recommended Responses** | 운영자 권고 대응 |
| **Safe Fault Injection** | allowlist 기반 폴트 선택·주입 (로컬 시뮬레이션만) |
| **Docker Service Status** | 전체 컨테이너 역할·상태·경계·링크 |
| **Protocol Log / Runtime Log** | 프로토콜 이벤트 및 런타임 로그 실시간 확인 |
| **Command Log / Tactical Message Log** | 커맨드·전술 메시지 이력 |
| **Scenario Packages** | DAH 훈련 시나리오 패키지 목록 및 실행 명령 |

---

## 폴트 주입 데모

대시보드 **Safe Fault Injection** 패널 또는 REST API로 실행합니다.
모든 폴트는 로컬 Docker 시뮬레이션 전용이며 실제 네트워크·장비에 영향을 주지 않습니다.

### 허용 폴트 프로파일

| 폴트 | 영향 레이어 | 탐지 신호 |
|---|---|---|
| `mavlink_plaintext_warning` | C2 Data Link | 프로토콜 로그 경보, 링크 degraded |
| `mission_count_reset_attempt` | GCS | 미션 시퀀스 guard alert, 업로드 hold |
| `c2_link_delay` | C2 Data Link | 체인 C2 노드 degraded, 지연 메트릭 |
| `c2_link_packet_loss` | C2 Data Link | 패킷 손실 메트릭, critical 전환 |
| `tmmr_queue_overflow` | TMMR Emulator | 큐 깊이·드롭 메시지·priority starvation |
| `ticn_route_metric_change` | TICN-like Network | 라우트 메트릭 변화·변경 횟수 |
| `upper_c2_command_mismatch` | Upper C2/BMS | 커맨드 불일치 카운트, dual-review alert |

### REST API로 폴트 주입

```bash
curl -X POST http://localhost:8080/api/faults/inject \
  -H "Content-Type: application/json" \
  -d '{"payload": {"fault_type": "tmmr_queue_overflow", "requested_by": "demo"}}'
```

체인 상태 확인:

```bash
curl http://localhost:8080/api/chain | python -m json.tool
curl http://localhost:8080/api/alerts | python -m json.tool
```

---

## Harness CLI (단독 실행)

Docker 없이 공격·방어 시나리오를 직접 실행할 수 있습니다.

```powershell
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m dah_harness.cli --scenario scenarios/uav_ugv_convoy.json --output output/harness_summary.json
```

또는:

```powershell
.\scripts\run_harness.ps1
```

### 방어 threshold 튜닝

```powershell
$env:PYTHONPATH = "src"
python -m dah_harness.cli `
  --scenario scenarios/uav_ugv_convoy.json `
  --set route_deviation_threshold_m=45 `
  --set link_loss_threshold_s=4 `
  --output output/tuned_summary.json
```

`output/harness_summary.json`의 `metrics` 필드에서 확인:

| 지표 | 의미 |
|---|---|
| `detection_rate` | 공격 탐지율 |
| `mean_detection_latency_s` | 평균 탐지 지연 |
| `false_positive_actions` | 오탐 수 |
| `mission_progress` | 미션 진행률 |

### DAH 훈련 시나리오 패키징

```bash
# 단일 시나리오 검증
PYTHONPATH=src python -m uas_utm.scenario_report \
  --scenario scenarios/dah_training/mavlink_telemetry_monitoring.json \
  --markdown-output output/reports/mavlink_telemetry_monitoring.md

# 단일 시나리오 패키징
PYTHONPATH=src python -m uas_utm.scenario_package \
  --scenario scenarios/dah_training/mavlink_telemetry_monitoring.json \
  --output-dir output/scenario-packages

# 전체 훈련 시나리오 일괄 패키징
PYTHONPATH=src python -m uas_utm.scenario_batch \
  --scenario-dir scenarios/dah_training \
  --output-dir output/scenario-packages
```

---

## 로그 확인

```bash
docker compose logs -f dah-gcs
docker compose logs -f dah-dashboard
docker compose logs -f dah-tactical-router
docker compose logs -f dah-defense-agent
```

---

## 테스트

```bash
python -m unittest discover -s tests
```

Docker 구성 검증:

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
docker compose down
```

---

## 안전·윤리 경계

이 저장소는 **로컬 Docker 환경 내 방어 시뮬레이션**만 수행합니다.

- 실제 군 통신망(TICN, TMMR, C2/BMS)과 연결하지 않습니다.
- 실제 드론 액추에이터 명령을 실행하지 않습니다.
- 외부 IP·무선망을 대상으로 하는 공격 트래픽을 생성하지 않습니다.
- 폴트 주입은 allowlist에 등록된 시나리오만 허용하며, 모두 시뮬레이션 전용입니다.
- 모든 커맨드는 기본 `dry_run=true`로 처리됩니다.
- 컨테이너는 기본적으로 privileged 모드, host 네트워킹, raw socket, NET_ADMIN 권한을 사용하지 않습니다.

---

## 제출 패키지 구성 (DAH 예선)

```text
README.md
src/                     ← 에이전트·하네스·서비스 코드
scenarios/               ← 공격/방어 검증 시나리오 JSON
tests/                   ← 회귀 테스트
docs/                    ← 아키텍처·서비스 맵·갭 분석·취약점 문서
requirements.txt
Dockerfile
docker-compose.yml
```

| 일정 | 날짜 |
|---|---|
| 보고서 제출 마감 | 2026-07-10 23:59 KST |
| 본선 진출팀 발표 | 2026-07-31 |
| 오프라인 본선 | 2026-08-21 |

---

## 향후 확장

| 항목 | 내용 |
|---|---|
| PX4/ArduPilot SITL 어댑터 | `dah_harness` 입출력을 SITL과 연결하는 adapter 추가 |
| ROS2/Gazebo UGV 어댑터 | `dah-ugv-sim`을 실제 ROS2 토픽으로 교체 |
| LLM planner + rule executor 분리 | 방어 에이전트를 LLM 계획자와 규칙 기반 실행자로 분리 |
| Prometheus/Grafana/Loki 연동 | 메트릭·로그 시각화 대시보드 추가 |
| Scenario replay/record | 텔레메트리 및 공격 이벤트 리플레이 기능 |
| 멀티소스 트랙 융합 | 여러 엣지 소스의 트랙 데이터를 융합하는 fusion stage 확장 |

---

## 참고 문서

| 문서 | 내용 |
|---|---|
| [`docs/repo_gap_analysis.md`](docs/repo_gap_analysis.md) | 현재 레포 vs 참고 레포 구조 비교 |
| [`docs/service_map.md`](docs/service_map.md) | Docker 서비스 역할 매핑 |
| [`docs/docker_desktop_runbook.md`](docs/docker_desktop_runbook.md) | Docker Desktop 운용 상세 가이드 |
| [`docs/scenarios.md`](docs/scenarios.md) | DAH 훈련 시나리오 실행 흐름·AI 레이블 |
| [`docs/vulnerabilities.md`](docs/vulnerabilities.md) | 방어 취약점 케이스 및 폴트 프로파일 |
| [`docs/stack_and_harness_plan.md`](docs/stack_and_harness_plan.md) | 스택 설계 및 하네스 계획 |
