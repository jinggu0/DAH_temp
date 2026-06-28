# DAH_temp — Claude Code Project Instructions

## 프로젝트 목표

DAH 2026 UAV/UGV UAS 사이버 방어 시뮬레이션을 위한 Docker 기반 로컬 사이버 레인지.

모델링 대상 체인:
```
UAV/UGV → C2 Data Link → GCS / Ground Gateway
        → Tactical Router / TIPS → TMMR Emulator
        → TICN-like Network → Upper C2/BMS Simulator
        → Defense Agent / Dashboard
```

필수 지원 기능:
- UAV/UGV mock 텔레메트리
- MAVLink 호환 텔레메트리 모니터링
- GCS 대시보드
- Tactical Emulator
- TMMR/TICN 역할 기반 에뮬레이션
- Defense Agent 알림 및 권장 대응
- Docker Desktop 기반 서비스 운용
- 안전한 로컬 전용 폴트 주입 시나리오

---

## 구현 범위 경계 (SCOPE BOUNDARY)

### 허용
- 실제 UAS/MAVLink 호환 텔레메트리 파싱
- Mock UAV/UGV 텔레메트리
- Docker 로컬 C2 링크 에뮬레이션
- TMMR 역할 에뮬레이터
- TICN-like 라우트 에뮬레이터
- Upper C2/BMS 시뮬레이터
- 로컬 전용 폴트 주입
- 대시보드 시각화
- 방어 모니터링 및 알림

### 금지
- 실제 군 네트워크 연동
- 실제 TICN/TMMR 프로토콜 구현
- 실제 라디오/RF 공격 로직
- 외부 네트워크 공격 로직
- 실제 시스템에 영향을 주는 페이로드
- 기본값으로 실제 드론 액추에이터 명령 실행
- 로컬 개발 환경 외부에서의 명령 실행

> 잠재적으로 위험한 모든 명령은 dry-run, simulation-only, 또는 운영자 명시 승인 필요.

---

## 아키텍처 — 목표 서비스 구성

| 서비스 | 역할 |
|---|---|
| `dah-uav-sim` | UAV mock 텔레메트리 에이전트 |
| `dah-ugv-sim` | UGV mock 텔레메트리 에이전트 |
| `dah-gcs` | GCS / UTM 서비스 (port 8080) |
| `dah-dashboard` | 대시보드 프록시 |
| `dah-tactical-router` | Tactical Router / TIPS 에뮬레이터 |
| `dah-tmmr-emulator` | TMMR 에뮬레이터 |
| `dah-ticn-emulator` | TICN-like 네트워크 에뮬레이터 |
| `dah-upper-c2` | Upper C2/BMS 시뮬레이터 |
| `dah-telemetry-collector` | 텔레메트리 수집 로그 역할 |
| `dah-defense-agent` | 규칙 기반 방어 에이전트 |
| `dah-gateway` | 통합 진입점 (port 9000) |

모든 에뮬레이터 컴포넌트는 반드시 `EMULATED / NOT REAL MILITARY SYSTEM` 표시.

---

## 대시보드 표시 요구사항

필수 패널:
- 서비스 카드 (UAV·UGV·GCS·C2·TMMR·TICN·Upper C2·Defense Agent·Telemetry Collector)
- 전술 체인 다이어그램 (`UAV/UGV → C2 → GCS → Router → TMMR → TICN → Upper C2`)
- 알림, 폴트 이벤트, 텔레메트리 로그, 커맨드 로그, 전술 메시지 로그
- Docker 서비스 상태

상태 레이블 (색상 + 텍스트 병용):
- `normal` / `degraded` / `critical` / `emulated` / `mock mode` / `real-MAVLink-capable`

---

## 취약점 시나리오 규칙

### 허용 시나리오
| 시나리오 | 폴트 프로파일 |
|---|---|
| MAVLink 평문/인증 부재 | `mavlink_plaintext_warning` |
| 미션 시퀀스 조작 | `mission_count_reset_attempt` |
| C2 링크 지연 | `c2_link_delay` |
| C2 패킷 손실 | `c2_link_packet_loss` |
| TMMR 큐 오버플로 | `tmmr_queue_overflow` |
| TICN 라우트 메트릭 변화 | `ticn_route_metric_change` |
| Upper C2 커맨드 불일치 | `upper_c2_command_mismatch` |

각 시나리오에 포함할 항목: 영향 레이어, 원인, 로컬 시뮬레이션 이벤트, 예상 대시보드 효과, 탐지 로직, 대응 로직, 테스트 케이스.

### 금지
- 실제 exploit 페이로드
- 실제 군 네트워크 절차
- 실제 무선 공격 단계
- 외부 타겟 지시

---

## 코딩 규칙

- 명시적으로 변경 요청이 없으면 기존 동작 보존.
- 기존 테스트가 통과한 상태를 유지.
- 작고 점진적인 커밋 선호.
- 명시적 요청 없이 대규모 리팩터링 금지.
- Python 표준 라이브러리 우선; 기존 의존성이 있는 경우만 외부 패키지 사용.
- 기존 코드 스타일(dataclasses)과 일관성 유지.
- 새 동작에는 테스트 작성.
- 런타임 동작 변경 시 README와 docs 업데이트.
- 공격/폴트 로직은 반드시 allowlist 기반.
- API 응답은 가능한 한 하위 호환성 유지.

---

## Docker 규칙

- 기본 실행은 반드시 safe mock/demo 모드.
- 기본값으로 privileged 컨테이너 사용 금지.
- 기본값으로 host 네트워킹 사용 금지.
- 기본값으로 raw socket / NET_ADMIN 권한 사용 금지.
- 필요한 포트만 노출.
- 통합 대시보드 진입점: `localhost:9000`
- 기존 UTM 서비스 `localhost:8080` 호환성 유지.

---

## 테스트 명령

코딩 작업 완료 전 반드시 실행:

```bash
python -m unittest discover -s tests
```

Docker 파일 변경 시 추가 확인:

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
docker compose down
```

---

## 작업 스타일 (Work Style)

코드 수정 전 순서:
1. 관련 파일 검토
2. 현재 구현 요약
3. 소규모 계획 제안
4. 최소한의 변경 적용
5. 테스트 실행
6. 변경된 파일, 동작, 남은 TODO 보고

큰 작업은 단계(phase)로 분리하고 요청된 단계 완료 후 중단.
