# DAH 2026 사이버 공격 시나리오 문서

> **보안 경계**: 모든 시나리오는 폐쇄형 Docker 로컬 환경(`dah-ops-net` / `dah-asset-net`)의  
> fault/anomaly injection으로만 구현됩니다. 실제 드론·군 장비·외부 IP 대상 공격은 생성하지 않습니다.

---

> **출처 상세**: 각 시나리오의 학술 출처·판단 근거 전체 → [`docs/attack_references.md`](./attack_references.md) 참조

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────┐
│  dah-ops-net / dah-asset-net (Docker 내부)  │
│                                             │
│  ┌─────────────────┐    ┌────────────────┐  │
│  │  dah-gcs:8080   │◄───│ 공격 컨테이너  │  │
│  │  (GCS REST API) │    │ (외부 공격자   │  │
│  └────────┬────────┘    │  역할 수행)    │  │
│           │             └────────────────┘  │
│  ┌────────▼────────┐                        │
│  │  dah-dashboard  │  ← 침입 탐지 경보      │
│  └─────────────────┘                        │
└─────────────────────────────────────────────┘
```

- 공격 컨테이너는 `profiles: ["cyber-attack"]` 로 격리
- GCS healthy 조건 확인 후 실행 (depends_on healthcheck)
- 대시보드 침입 탐지(IDS)가 5초 간격으로 `/api/tracks`, `/api/commands/list` 폴링

---

## 실행 방법

```bash
# 단일 dah-attack 컨테이너로 전체 18개 시나리오 실행
docker compose --profile cyber-attack up dah-attack

# 특정 시나리오만 실행 (환경변수 오버라이드)
DAH_ATTACK_SCENARIOS=recon,fdi-fusion,mimicry \
  docker compose --profile cyber-attack up dah-attack

# 사용 가능한 시나리오 이름 확인
docker run --rm dah-attack python -m dah_attacks.attack_runner --list

# 개별 시나리오 실행
docker compose --profile cyber-attack up dah-attack-gnss-drift
docker compose --profile cyber-attack up dah-attack-link-degrade
docker compose --profile cyber-attack up dah-attack-dynamic-spoof
docker compose --profile cyber-attack up dah-attack-sync-disrupt
docker compose --profile cyber-attack up dah-attack-cmd-inject

# 공격 컨테이너만 중지
docker compose --profile cyber-attack stop \
  dah-attack-gnss-drift dah-attack-link-degrade \
  dah-attack-dynamic-spoof dah-attack-sync-disrupt dah-attack-cmd-inject

# 로그 확인
docker logs dah-attack-gnss-drift -f
```

---

## 공통 탐지 시그니처 (IDS)

대시보드(`app.js` → `_idsCheckTelemetry`, `_idsCheckCommand`)가 감지하는 필드:

| 필드 | 공격 값 | 탐지 경보 등급 |
|------|---------|--------------|
| `source_authority` | `"EXTERNAL-ATTACKER"` | critical |
| `source` | `"GNSS-SPOOF"` | critical |
| `source` | `"DYN-SPOOF"` | critical |
| `source` | `"SYNC-DISRUPT"` | critical |
| `source_id` | `edge-attack-*` 접두사 | critical |
| `link_quality` | < 0.3 | warning |
| `track_confidence` | < 0.6 | warning |
| `requested_by` | `"ATTACKER:*"` 접두사 | critical |

---

## 시나리오 1: GNSS Drift 누적 공격

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `gnss-drift`)
- **코드**: `src/dah_attacks/gnss_drift_attack.py`
- **주요 출처**: Tippenhauer et al., "On the Requirements for Successful GPS Spoofing Attacks," ACM CCS 2011 · arXiv:2507.11173
- **PDF 유사**: ✅ PDF 시나리오 #2/#7

### 원리

```
정상 텔레메트리:  pos=[200.0, -220.0, 95.0]
1틱 후:          pos=[200.5, -219.6, 95.1]  (drift +0.5, +0.4, +0.1)
10틱 후:         pos=[205.3, -214.8, 94.7]  (drift 누적 ~5m)
120s 후:         pos=[234.1, -188.2, 93.5]  (drift 누적 ~40m)
```

- 매 틱 `(random() - 0.44) * drift_rate` 로 X/Y 방향 편향 누적
- 단일 틱 변화량은 탐지 임계값 이하 유지 (기본 0.6m/틱)
- `track_confidence`는 시간에 따라 `0.92 → 0.55` 선형 하락
- GCS가 좌표 급변이 아닌 **점진적 이탈**로 인식해 알림 우선순위 낮음

### 탐지 신호
- `source: "GNSS-SPOOF"`
- `source_authority: "EXTERNAL-ATTACKER"`
- `source_id: "edge-attack-gnss-01"` (미인가 엣지)
- `track_confidence` 0.6 이하 도달 시 warning 경보

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--drift-rate` | `0.6` | 틱당 최대 드리프트 (m) |
| `--interval-s` | `0.8` | 텔레메트리 전송 간격 (s) |
| `--duration-s` | `120` | 공격 지속 시간 (s) |
| `--target-asset` | `small-dronebot-01` | 대상 자산 ID |

---

## 시나리오 2: 전술 링크 저하 Fail-safe 유도

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `link-degrade`)
- **코드**: `src/dah_attacks/link_degrade_attack.py`
- **주요 출처**: Bakhshi & Shahidi, "Link Quality Degradation Attacks," IEEE WCNC 2012 · RUSI, "Electronic Warfare in the Ukrainian Conflict," 2023
- **PDF 유사**: ✅ PDF 시나리오 #1

### 원리

```
link_quality 변화:
  0s:   1.000  (정상)
 10s:   0.750  (경고 시작)
 30s:   0.250  ← GCS Fail-safe 정책 트리거 구간
 60s:   0.040  (최솟값 clamp)
 90s:   0.040  (공격 종료)
```

- GCS heartbeat 엔드포인트(`/api/edge/devices/heartbeat`)에 **등록된 실제 엣지 ID로 위장**하여 전송
- `link_quality = max(0.04, 1.0 - elapsed * degrade_rate + noise)`
- 완전 차단(0)이 아닌 **저하(degraded)**로 GCS의 RTL/HOLD Fail-safe 정책 유도
- 링크 품질 0.25 미만 + 30% 확률로 추가 지연 삽입 (패킷 손실 시뮬레이션)
- `cpu_load`, `temperature_c` 도 동반 상승시켜 하드웨어 고장처럼 위장

### 탐지 신호
- `link_quality < 0.3` → warning 경보
- 실제 edge 위장이므로 `source_id` 탐지는 불가 → **링크 품질 이상 지표가 주요 탐지 근거**

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target-edge` | `edge-dronebot-01` | 위장 대상 엣지 ID |
| `--degrade-rate` | `0.025` | 초당 link_quality 감소율 |
| `--interval-s` | `1.2` | heartbeat 전송 간격 (s) |
| `--duration-s` | `90` | 공격 지속 시간 (s) |

---

## 시나리오 3: 동역학 일치 GPS 스푸핑

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `dynamic-spoof`)
- **코드**: `src/dah_attacks/dynamic_spoof_attack.py`
- **주요 출처**: Kerns et al., "Unmanned Aircraft Capture via GPS Spoofing," Journal of Field Robotics 2014 · Zeng et al., arXiv:2501.07597 (2025)
- **PDF 유사**: ✅ PDF 시나리오 #10

### 원리

```
단순 위치 스푸핑의 약점:
  velocity, heading이 위조 경로와 불일치 → 물리 법칙 위반 탐지

동역학 일치 스푸핑:
  원형 궤도 angle = elapsed * orbit_speed
  position.x = base_x + cos(angle) * radius
  position.y = base_y + sin(angle) * radius
  velocity.x = -sin(angle) * radius * orbit_speed  ← 원운동 접선 속도
  velocity.y =  cos(angle) * radius * orbit_speed
  heading    = degrees(angle + π/2)                ← 진행 방향 일치
```

- 반경을 즉시 최대로 늘리지 않고 `min(radius, elapsed * 3.0)` 으로 **점진적 확대**
- `track_confidence: 0.87` — 정상 범위 내로 유지해 임계값 기반 탐지 우회
- 속도·방향이 위조 위치와 물리적으로 일관성 있어 단순 kinematic 탐지 우회

### 탐지 신호
- `source: "DYN-SPOOF"`
- `source_authority: "EXTERNAL-ATTACKER"`
- `source_id: "edge-attack-dynspoof-01"` (미인가 엣지)

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--orbit-radius` | `120` | 목표 궤도 반경 (m) |
| `--orbit-speed` | `0.4` | 각속도 (rad/s) |
| `--interval-s` | `0.9` | 텔레메트리 전송 간격 (s) |
| `--duration-s` | `100` | 공격 지속 시간 (s) |

---

## 시나리오 4: UAV/UGV 협동 임무 동기화 교란

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `sync-disrupt`)
- **코드**: `src/dah_attacks/sync_disrupt_attack.py`
- **주요 출처**: Zhang et al., "Cyber Attacks on Multi-UAV Collaborative Mission Systems," arXiv:2312.03787 (2023)
- **PDF 유사**: ✅ PDF 시나리오 #4/#16

### 원리

```
정상 협동 임무:
  UAV: mission_id="dronebot-local-recon",       waypoint=3
  UGV: mission_id="ugv-convoy-route-clearance", waypoint=2

공격 후:
  UAV: mission_id="dronebot-local-recon",       waypoint=3  (정상)
  UGV: mission_id="dronebot-local-recon",       waypoint=0  ← 잘못된 미션 주입
       position=[210.0, -240.0, 95.0]                       ← UAV 미션 시작 좌표로 강제 이동
```

- UGV를 UAV의 미션 경유점으로 이동시켜 **GCS가 두 플랫폼이 다른 임무 단계에 있다고 판단**하게 만듦
- 협동 타이밍 붕괴 → UAV 선행 정찰 없이 UGV 진입, 또는 반대
- `waypoint_id`를 매 틱 순환(`tick % 3`)해 정상적으로 임무를 수행하는 것처럼 위장

### 탐지 신호
- `source: "SYNC-DISRUPT"`
- `source_authority: "EXTERNAL-ATTACKER"`
- `source_id: "edge-attack-sync-01"` (미인가 엣지)
- `mission_id`가 자산 타입과 불일치 (UGV에 UAV 미션 ID)

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target-asset` | `ground-convoy-01` | 교란 대상 자산 |
| `--interval-s` | `1.0` | 텔레메트리 전송 간격 (s) |
| `--duration-s` | `90` | 공격 지속 시간 (s) |

---

## 시나리오 5: 임무 상태 불일치 Command Injection

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `cmd-inject`)
- **코드**: `src/dah_attacks/cmd_inject_attack.py`
- **주요 출처**: Javed et al., "Command and Control Security Vulnerabilities in Open-Source UAS," arXiv:2501.18874 (2025) · Rodday et al., "MAVLink Protocol Security," IEEE ICCST 2016
- **PDF 유사**: ✅ PDF 시나리오 #3/#9

### 원리

```
주입 시퀀스 (3회 반복):
  1. land             ← 임무 진행 중 강제 착륙
  2. return_to_launch ← 웨이포인트 이동 중 귀환
  3. hold_position    ← 표적 접근 단계 정지
  4. land             ← 복귀 경로 중 재착륙
  5. return_to_launch ← 재착륙 직후 귀환 재주입
```

- 커맨드 타입 자체는 정상(`LAND`, `RTL`, `HOLD`) → **명령 타입 화이트리스트 방어 우회**
- `requested_by: "ATTACKER:mission_state_mismatch"` 로 요청
- 주입 즉시 `/api/commands/approve` 자동 승인 시도 → 방어 체계가 없으면 게이트웨이 도달
- 주입 간격에 불규칙 jitter 적용 (`interval * [0.7, 1.3]`) → 패턴 탐지 회피
- `dry_run: true` — 실제 actuator 명령은 생성하지 않음

### 탐지 신호
- `requested_by: "ATTACKER:mission_state_mismatch"` 접두사 `ATTACKER:` 로 탐지
- 비정상적 시점의 반복 커맨드 패턴 (임무 중 LAND × 3)

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target-asset` | `small-dronebot-01` | 대상 자산 ID |
| `--repeat` | `3` | 시퀀스 반복 횟수 |
| `--interval-s` | `4.0` | 커맨드 간격 기준값 (s) |

---

## 시나리오별 비교

| 시나리오 | 탐지 난이도 | 주요 목표 | 탐지 지표 |
|----------|-----------|---------|---------|
| GNSS Drift | 높음 (점진적) | 경로 이탈 유도 | track_confidence 하락, 미인가 엣지 |
| 링크 저하 | 중간 (실 엣지 위장) | Fail-safe 강제 발동 | link_quality < 0.3 |
| 동역학 스푸핑 | 높음 (물리 일관성) | 위치 위조 | 미인가 엣지, DYN-SPOOF 소스 |
| 동기화 교란 | 중간 | 협동 임무 붕괴 | 자산-미션 불일치, 미인가 엣지 |
| 커맨드 인젝션 | 낮음 (즉발성) | 임무 중단 | ATTACKER: requested_by |

---

## 새 공격 시나리오 추가 가이드

1. `src/dah_attacks/` 에 `{이름}_attack.py` 파일 생성
2. `GcsClient`, `wait_for_gcs` 를 `common.py` 에서 import
3. `main(argv)` 함수와 `argparse` 정의 (최소: `--service-url`, `--duration-s`)
4. `source`, `source_authority: "EXTERNAL-ATTACKER"` 필드 포함
5. `docker-compose.yml` 에 `profiles: ["cyber-attack"]` 서비스 추가
6. `app.js` `IDS_SIGNATURES` 에 탐지 시그니처 추가
7. **이 문서(`docs/attack_scenarios.md`)에 시나리오 섹션 추가**

---

---

## 시나리오 6: Sybil Phantom Fleet (유령 함대 주입)

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `sybil-fleet`)
- **코드**: `src/dah_attacks/sybil_fleet_attack.py`
- **주요 출처**: Sedjelmaci et al., "Sybil Attacks on Unmanned Aerial Vehicle Swarm C2," IEEE Internet of Things Journal 2023

### 원리

```
GCS 취약점: state.py ingest_telemetry()가 asset_id 존재 여부를 검증하지 않음
  → 임의 asset_id로 텔레메트리를 주입하면 GCS external_frames에 등록됨

파급 효과 체인:
  ingest_telemetry(asset_id="sybil-scout-0379")
    → external_frames["edge-sybil-00:sybil-scout-0379"] = frame
    → _known_asset_ids()에 "sybil-scout-0379" 추가
    → tracks_payload()에 유령 항적 등장
    → request_command(asset_id="sybil-scout-0379")가 성공 ← 커맨드 주입 가능
```

- 12개 유령 자산 × 1틱마다 배치 전송 → 초당 12개 유령 항적 생성
- 각 자산 위치는 황금각(137.5°) 분산으로 그럴듯하게 작전 구역 내 배치
- `track_confidence: 0.70±0.05` — 탐지 임계(0.6) 위, 의심 범위 아래
- 매 10틱마다 유령 자산에 `hold_position` 커맨드 주입 (GCS가 허용함을 증명)

### 탐지 신호
- `source: "SYBIL-FLEET"` → critical
- `source_authority: "EXTERNAL-ATTACKER"` → critical
- `source_id: "edge-sybil-*"` 패턴 → critical
- `/api/tracks` track_count 급증 (정상 2-3개 → 14-15개)

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--fleet-size` | `12` | 유령 자산 수 |
| `--interval-s` | `1.0` | 배치 전송 간격 (s) |
| `--duration-s` | `120` | 공격 지속 시간 (s) |
| `--also-inject-commands` | `true` | 유령 자산 커맨드 주입 여부 |

---

## 시나리오 7: Track Fusion FDI (허위 데이터 주입 — 트랙 융합 탈취)

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `fdi-fusion`)
- **코드**: `src/dah_attacks/fdi_fusion_attack.py`
- **주요 출처**: Liu et al., "False Data Injection Attacks Against State Estimation in CPS," IEEE Trans. Signal Processing (arXiv:2104.09907) 2021 · Kong et al., USENIX Security 2023

### 원리

```
GCS 취약점 1: source_registry 기반 신뢰도 분기
  state.py _source_sample_from_external():
    registry = source_registry.get(source_id, {})
    base_confidence = registry.get("base_confidence", 0.65)
    # "mavlink-udp-adapter" → base_confidence = 0.92

GCS 취약점 2: tracks_payload() 융합 로직 — 최고 신뢰도 소스가 fused_position 결정
  sources.sort(key=lambda x: (x["stale"], -x["confidence"], x["source_id"]))
  primary = sources[0]  # 최고 신뢰도

공격 전략:
  source_id = "mavlink-udp-adapter"    ← source_registry 합법 ID 위장
  track_confidence = 0.97              ← 시뮬레이션(0.82)·MAVLink(0.92)보다 높음
  → 대시보드의 fused_position이 공격자가 원하는 좌표로 교체됨

이동 경로 (위장 경유점):
  [350, -400, 95] → [420, -450, 80] → [480, -500, 60] → [500, -520, 20]
  (실제 작전 구역 밖 → 금지 공역 방향 → 지상 접근)
```

- `_smooth_move()`: alpha = clamp(t * 0.12, 0, 1) — 점진적 이동으로 kinematic 이상 탐지 회피
- 속도·heading도 이동 방향에 맞춰 계산 (물리적 일관성 유지)
- `source_authority: "C2 / Ground Control"` — source_registry 실제 값 그대로 사용

### 탐지 신호
- `source: "FDI-FUSION"` → critical (source 필드에 공격 마커 노출)
- 실제 배치에서는 source를 `"mavlink-adapter-001"` 등으로 바꿔 숨길 수 있음 → 탐지 어려움
- fused_position이 허용 구역 밖으로 이탈 시 geofence 경보

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target-asset` | `small-dronebot-01` | 위치 위조 대상 자산 |
| `--hijack-source` | `mavlink-udp-adapter` | 위장할 source_registry ID |
| `--interval-s` | `0.8` | 텔레메트리 전송 간격 (s) |
| `--duration-s` | `100` | 공격 지속 시간 (s) |

---

## 시나리오 8: Alert Fatigue + Masked Command Injection (경보 포화 복합 공격)

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `alert-fatigue`)
- **코드**: `src/dah_attacks/alert_fatigue_attack.py`
- **주요 출처**: Wang et al., "Alarm Fatigue in Cyber-Physical System IDS," USENIX Security 2024 · Target 사고 사후 분석 (2014)

### 원리

```
2단계 복합 공격:

Phase 1 (45s) — 경보 포화:
  5개 위장 엣지에서 IDS 임계값 경계에서 오르내리는 신호를 1.5s 간격으로 전송
    track_confidence ≈ N(0.60, 0.04)  ← IDS warning 임계 0.6 근처
    link_quality     ≈ N(0.30, 0.03)  ← IDS warning 임계 0.3 근처

  결과:
    - 대시보드 intrusionAlertList에 warning 경보 50개 축적 (최대치)
    - 운용자: "또 노이즈야" → 경보 무시 행동 패턴 형성

Phase 2 (45~105s) — 은폐 커맨드 주입:
  노이즈 유지 + 매 5틱(7.5s)마다 실제 return_to_launch 커맨드 주입
    requested_by = "ATTACKER:masked_under_alert_fatigue"
  Phase 1이 경보 목록을 포화시킨 상태 → 새 critical 경보가 목록 하단으로 밀림
```

IDS 취약점 (`app.js _idsRaiseAlerts`):
- 중복 방지 window = 10초 → 10.1초마다 동일 코드 경보 재삽입 가능
- `intrusionAlerts.length > 50` 시 오래된 경보 삭제 → 최신 경보로 갱신 필요

### 탐지 신호
- Phase 1: `source: "ALERT-NOISE"` warning 경보 다수 (IDS가 경보를 내지만 운용자가 무시)
- Phase 2: `requested_by: "ATTACKER:*"` critical 경보 → 하지만 경보 목록 하단에 묻힘
- 방어 패턴: 경보 발생 빈도 급증 자체를 이상으로 감지 (Rate-of-Alert anomaly)

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target-asset` | `small-dronebot-01` | Phase 2 커맨드 대상 |
| `--phase1-duration` | `45` | Phase 1 지속 시간 (s) |
| `--interval-s` | `1.5` | 노이즈 배치 간격 (s) |
| `--inject-every` | `5` | Phase 2 커맨드 주입 주기 (틱) |

---

## 시나리오별 비교 (전체)

| 시나리오 | 탐지 난이도 | 공격 벡터 | 주요 목표 | 탐지 지표 |
|----------|-----------|---------|---------|---------|
| GNSS Drift | 높음 (점진적) | 텔레메트리 위조 | 경로 이탈 유도 | track_confidence 하락, 미인가 엣지 |
| 링크 저하 | 중간 (실 엣지 위장) | heartbeat 조작 | Fail-safe 발동 | link_quality < 0.3 |
| 동역학 스푸핑 | 높음 (물리 일관성) | 텔레메트리 위조 | 위치 위조 | DYN-SPOOF 소스, 미인가 엣지 |
| 동기화 교란 | 중간 | 텔레메트리 위조 | 협동 임무 붕괴 | 자산-미션 불일치 |
| 커맨드 인젝션 | 낮음 (즉발성) | 커맨드 API | 임무 중단 | ATTACKER: requested_by |
| **Sybil 유령 함대** | **중간** | **API 입력 검증 부재** | **운용자 혼란 + 커맨드 주입** | **SYBIL-FLEET 소스, edge-sybil-* ID** |
| **Track Fusion FDI** | **매우 높음** | **source_registry 위장** | **fused_position 탈취** | **FDI-FUSION 소스** (실전엔 탐지 극히 어려움) |
| **Alert Fatigue** | **높음** | **IDS 설계 한계 악용** | **실제 공격 은폐** | **경보 발생률 급증** |

---

---

# 2차 어드벤스드 공격 시나리오 (시나리오 9~18)

> 아래 시나리오들은 GCS 소스코드(`state.py`, `log_store.py`, `server.py`)의  
> 설계 취약점을 직접 코드 레벨에서 분석하여 도출한 것입니다.  
> ✅ = Docker 컨테이너 구현 완료, 📋 = 설계·연구 단계

---

## 시나리오 9: Timestamp Rollback — 트랙 노후화 포이즈닝 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `timestamp-rollback`)
- **코드**: `src/dah_attacks/timestamp_rollback_attack.py`
- **주요 출처**: Mo & Sinopoli, "Time-Based Replay Attacks on Cyber-Physical State Estimation," IEEE TIFS 2022

### 취약 코드 (state.py:767-769)
```python
frame_time_s = int(frame.get("time_s", requested_time_s))
age_s  = abs(requested_time_s - frame_time_s)
stale  = age_s > max(10, self.scenario.step_s * 3)   # ← 이 조건만으로 stale 판정
```

### 원리
```
공격자가 합법적 엣지와 동일한 asset_id로 time_s=0 텔레메트리 주입:

  requested_time_s  ≈  100   (현재 타임라인)
  frame_time_s      =   0    (공격자 주입값)
  age_s             = 100    → stale = True (임계 10s 초과)

tracks_payload() 정렬:
  sources.sort(key=lambda x: (x["stale"], -x["confidence"], x["source_id"]))
  stale=True  소스는 stale=False 소스보다 항상 뒤로 밀림
  → 공격자 주입 소스가 primary_source 자리 잠식 불가 (의도된 교란)
  → 정상 외부 소스도 모두 stale로 오염되면 시뮬레이션 소스만 남음
```

### 공격 기대 효과
| 단계 | 효과 |
|------|------|
| 주입 직후 | 해당 자산 외부 소스 전체 stale 표시 → 대시보드 "신호 노후" 경보 |
| 지속 주입 | external_frames에 stale 소스 누적 → 운용자의 실시간 위치 신뢰 불가 |
| 복합 사용 | FDI 공격 전 사전 오염 — 정상 소스를 stale로 만든 뒤 공격 소스를 primary로 |

### 탐지 신호
- `source: "TS-ROLLBACK"` → critical
- `source_id: "edge-attack-tsroll-01"` → critical
- 트랙 `stale=true` 상태에서 외부 소스 수 증가 → 비정상 패턴

---

## 시나리오 10: Battery Crisis Spoofing — 배터리 위기 동시 스푸핑 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `battery-crisis`)
- **코드**: `src/dah_attacks/battery_crisis_attack.py`
- **주요 출처**: Hayajneh et al., "Coordinated Battery Status Spoofing in Multi-UAV C2," IEEE AERO 2023 · Hartmann & Steup, DASC 2023

### 취약 코드 (state.py:443)
```python
"battery_wh": primary["battery_wh"],  # 검증 없이 그대로 노출
```
GCS는 `battery_wh` 값의 범위·변화율 검증 없이 트랙에 그대로 기록함.

### 원리
```
2단계 공격:
  Phase 1 (Warmup, 8틱): battery_wh = 690 × 0.98^tick
                          → 자연스러운 소모 패턴으로 신뢰 구축
  Phase 2 (Crisis):       battery_wh = 1.5 Wh (전 자산 동시)
                          → 정상 UAV(690 Wh), UGV(3725 Wh) 대비 0.04% 수준

실제 배터리 소모율: 690 Wh → 0 Wh는 수십 분 소요
이 공격은 수 초 만에 임계값 이하로 급락 → rate-of-change 이상
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| 1차 직접 효과 | 전 자산 대시보드 배터리 위기 경보 동시 발생 |
| 2차 간접 효과 | 운용자가 실물 장비 배터리 확인에 주의 분산 |
| Diversion 활용 | 이 교란 중 실제 Command Injection 등 본 공격 실행 |
| Fail-safe 유도 | GCS 자동 RTL 정책이 있을 경우 전 자산 동시 귀환 |

### 탐지 신호
- `battery_wh` 변화율 이상: 수 틱 내 98% 급락
- `source: "BATTERY-CRISIS"` → critical
- 복수 자산 동시 critical 배터리 (통계적 이상)

---

## 시나리오 11: Passive MAVLink Reconnaissance — 수동 텔레메트리 정찰 ✅

### 파일
- **컨테이너**: `dah-attack-passive-mavlink` (시나리오명: `passive-mavlink-recon`)
- **코드**: `src/dah_attacks/passive_mavlink_recon.py`
- **브로드캐스터**: `src/uas_utm_service/mavlink_broadcaster.py` (GCS 측 신설)
- **주요 출처**: MAVLink Message Signing 공식 문서 (mavlink.io) · Rodday et al., "Hacking a Professional Drone," RSA Conference 2016 · MITRE ATT&CK T1040 (Network Sniffing)

### 핵심 주장 (논쟁 검증 완료)

> **Passive MAVLink Recon은 MAVLink v2 signing의 보안 범위 밖에 있는 수동 정찰 시나리오다.**
> MAVLink signing은 메시지 인증과 무결성을 제공하지만, payload 기밀성이나 message snooping 방지는 제공하지 않는다.
> 공격자가 평문 MAVLink가 관측 가능한 세그먼트에 위치하면, GCS API를 호출하지 않고도 전술 정보를 수집할 수 있다.
> 이 수신 행위는 **GCS 애플리케이션 감사로그만으로는 식별하기 어렵다.**

### 왜 Silent REST Recon을 대체하는가

```
Silent REST Recon의 문제점:
  ① 방산 GCS는 REST API를 내부망 격리 + 인증으로 보호 → 접근 전제가 비현실적
  ② "미인증 API 열거"는 범용 웹 취약점 → 방산 특수성 평가 기준 미충족
  ③ REST 호출은 GCS 감사로그(route handler, runtime log)에 기록 → 흔적 역추적 가능

Passive MAVLink Recon의 개선 근거:
  ① MAVLink 프로토콜 구조 이해 필수 (msg_id, CRC_EXTRA, x25 체크섬, 필드 스케일)
     → 방산 특수성 평가 기준 직접 부합
  ② UDP 수신만 수행, GCS에 어떤 요청도 송신하지 않음
     → GCS 애플리케이션 감사로그(JSONL audit trail)에 수신 행위 기록 없음
  ③ MAVLink signing이 기밀성을 제공하지 않음 — 공식 문서 명시:
     "Signing does not prevent replay attacks, man-in-the-middle attacks
      or message snooping." (mavlink.io/en/guide/message_signing.html)
  ④ ArduPilot·PX4·STANAG 4586 미서명 또는 서명-only 채널에 동일하게 적용
```

### 공격 성립 조건 (AND 조건)

이 공격은 다음 조건이 **동시에** 충족되어야 성립한다.

```
[조건 1] 공격자가 평문 MAVLink가 유통되는 네트워크 세그먼트에 위치
          → 무선 링크 복호화 이후 내부 구간, 지상 전술 LAN, 시험평가망,
            정비망, 상용 UAS 연동망

[조건 2] 해당 세그먼트가 broadcast/multicast 또는 관측 가능한 packet path 제공
          → UDP 브로드캐스트(255.255.255.255)는 기본적으로 동일 서브넷 전체 전달
          → 유니캐스트 전환 또는 스위치 포트 보안 없으면 충족

[조건 3] 송출 메시지에 유의미한 전술 정보 포함
          → UAS 텔레메트리 목적으로 MAVLink를 운용하는 한 항상 충족
            (HEARTBEAT: 무장 상태, GLOBAL_POSITION_INT: 좌표, SYS_STATUS: 배터리)

[조건 4] 수신 인터페이스가 브로드캐스트 패킷 수신을 허용
          → SO_BROADCAST 소켓 옵션으로 충족; 별도 차단 설정 없으면 기본 허용
```

> **조건 1·2가 핵심 제약이다.** 조건 3·4는 MAVLink UAS 운용 시 기본적으로 충족된다.
> 네트워크 접근통제(802.1X, NAC, VLAN 격리)는 조건 1을 성립 불가능하게 만들 수 있다.
> 단, 내부자·공급망 위협 또는 물리 접근 시나리오에서는 이 통제가 우회된 이후를 가정한다.

### MAVLink Signing vs 기밀성 — 계층 구분

```
MAVLink v2 Signing이 제공하는 것:
  ✓ 송신자 인증 (신뢰된 출처 검증)
  ✓ 메시지 무결성 (위조 여부 탐지)
  ✓ Replay 공격 부분 억제 (timestamp 포함)

MAVLink v2 Signing이 제공하지 않는 것:
  ✗ Payload 기밀성 (암호화 아님, 평문 그대로 전송)
  ✗ Message snooping 방지 (공식 문서 명시)
  ✗ 수신자 제한 (브로드캐스트 수신은 서명과 무관)

Signed frame 구조:
  [STX][LEN][incompat=0x01][compat][SEQ][SYS_ID][COMP_ID][MSG_ID×3]
  [PAYLOAD — 평문]   ← 서명이 있어도 이 구간은 읽힌다
  [CRC×2]
  [LINK_ID][TIMESTAMP×6][SIGNATURE×6]

링크/네트워크 레이어 암호화(IPsec, MACsec, WPA3)는 payload를 숨길 수 있다.
단, 암호화 종단(복호화 이후) 내부 구간에는 링크 암호화의 보호 범위가 미치지 않으므로
해당 구간에는 별도 통제(애플리케이션 암호화, zero-trust segmentation)가 필요하다.
```

### 아키텍처

```
dah-gcs (GCS 서버)
  └─ MavlinkBroadcaster 스레드
       │  1초마다 추적 중인 자산 상태를 MAVLink v2 프레임으로 방출
       ▼
  UDP 브로드캐스트 255.255.255.255:14549 (dah-asset-net)
       │
  ┌────┴────────────────────────────────────────┐
  │  dah-mavlink-gateway    (합법 수신자)        │  ← 정상 운용
  │  dah-attack-passive-mavlink (공격자)        │  ← 동일 패킷 수신
  └─────────────────────────────────────────────┘
         ↑
  GCS는 이 방향을 관측할 수 없음 (요청이 없으므로)
  → GCS 애플리케이션 감사로그에 수신 행위 기록 없음
```

### 수신 메시지 및 수집 정보

```
HEARTBEAT (msg_id=0, 1초 간격):
  system_id     → 자산 식별자 (후속 공격 타겟 지정에 사용)
  type          → MAV_TYPE_QUADROTOR(2)=UAV / GROUND_ROVER(10)=UGV
  base_mode     → 무장(0x80 비트) / 유도비행(0x08 비트) 여부
  system_status → STANDBY(3) / ACTIVE(4) / CRITICAL(5)

GLOBAL_POSITION_INT (msg_id=33, 1초 간격):
  lat/lon       → WGS84 degE7 → 실좌표 (7자리 정밀도)
  alt           → MSL 고도 mm → m 변환
  vx/vy/vz      → 속도 cm/s → m/s → 지상속도·이동방향 산출
  hdg           → 기수방향 cdeg → deg

SYS_STATUS (msg_id=1, 5초 간격):
  battery_remaining → 배터리 잔량 %
  drop_rate_comm    → 패킷 손실률 (링크 품질 역산)
  voltage_battery   → 배터리 전압 mV

추가 수신 가능 (실제 군용 환경):
  COMMAND_ACK (msg_id=77)      → 명령 수락/거부 → 운용 의사결정 패턴
  MISSION_CURRENT (msg_id=42)  → 현재 웨이포인트 번호 → 임무 경로 추론
  MISSION_REQUEST_INT (msg_id=51) → 진행 중인 임무 업로드 포착
  UTM_GLOBAL_POSITION (msg_id=340) → ADS-B 트랜스폰더 위치
```

### 동작 흐름

```
0s    UDP 소켓 바인딩 (0.0.0.0:14549, SO_REUSEADDR)
      HTTP 요청 0건, TCP 연결 0건
      → GCS 측에 어떤 네트워크 이벤트도 발생하지 않음

1s~   HEARTBEAT 수신
        → 자산 수, 플랫폼 타입, 무장 상태 파악
        → sys_id 목록 수집 (후속 공격 타겟 풀 확보)

2s~   GLOBAL_POSITION_INT 수신
        → 각 자산 실좌표·속도·방위 파악
        → 이동 경로(trail) 추적 시작 (최근 20개 위치 유지)

10s~  SYS_STATUS 수신
        → 배터리 잔량 파악 → Battery Crisis 임계 타이밍 계산
        → 링크 손실률 파악 → Link Degrade 현재 기준선 설정

120s  수집 종료, IntelligenceReport 출력 + JSON 저장
      parse_errors, msg_type_counts, gcs_audit_trace=false 포함
      → /app/output/passive_mavlink_intel.json
```

### 수집 정보 → 후속 공격 매핑

| 수집 정보 | 활용 공격 | 정찰 없을 때 문제점 |
|-----------|----------|-------------------|
| 자산 WGS84 좌표 | GNSS Drift (S01), 동역학 스푸핑 (S03) | 엉뚱한 좌표에서 drift 시작 → 즉시 이상 탐지 |
| 자산 속도·방위 | 동역학 일치 스푸핑 (S03) | 물리 일관성 계산 불가 → 탐지 확률 상승 |
| system_id 목록 | Battery Crisis 전 자산 동시 (S10) | 공격 대상 sys_id 미확보 → 단일 자산만 가능 |
| 배터리 잔량 | Battery Crisis 임계 타이밍 (S10) | 이미 낮은 배터리에 공격 → 효과 없음 |
| 링크 손실률 기준선 | Link Degrade (S02) | 정상 대비 저하 폭 계산 불가 |
| 이동 경로 trail | Mimicry 패턴 학습 (S16) | 정상 비행 패턴 모방 불가 |
| mission_seq | Mission Upload Race | 업로드 타이밍 특정 불가 |

### 탐지 계층별 분석

| 탐지 계층 | 탐지 가능 여부 | 상세 |
|-----------|--------------|------|
| **GCS 애플리케이션 감사로그** | **어렵다** | UDP 수신은 GCS route handler를 통과하지 않음. audit trail에 수신자 기록 없음 |
| 네트워크 IDS / 패킷 캡처 | 부분 가능 | 브로드캐스트 송출은 관측되나, **수신자 IP를 특정할 수 없음** (브로드캐스트 정의상) |
| 스위치 포트 보안 / NAC | 사전 차단 가능 | 허가되지 않은 호스트가 세그먼트에 참여하는 시점에 차단 가능 |
| 호스트 EDR / eBPF | 탐지 가능 | 공격자 호스트의 소켓 바인딩, 프로세스 실행 기록 관측 가능 |
| 컨테이너 런타임 로그 | 탐지 가능 | Docker logs, 프로세스 실행 기록 — 단, 공격자가 제어하는 영역 |
| RF TSCM | 탐지 가능 | 무선 구간 수신 장비 방향 탐지 (물리적 대응 수단) |

> **결론**: 완전한 탐지를 위해서는 네트워크 센서 + 스위치 포트 보안 + EDR/eBPF의
> **복합 배포**가 필요하다. GCS 애플리케이션 감사로그 단독으로는 식별하기 어렵다.

### 방어 수단 및 한계

```
[효과적인 방어]
  ① 네트워크 접근통제 (802.1X, NAC, VLAN 격리)
     → 공격자가 세그먼트에 참여하지 못하게 함 (조건 1 차단)
     → 한계: 내부자·공급망 위협, 물리 접근 시나리오에서 우회 가능

  ② 링크/네트워크 레이어 암호화 (IPsec, MACsec, WPA3)
     → 공격자 관측 구간의 payload를 숨김
     → 한계: 암호화 종단(복호화 후) 내부 LAN 구간은 보호 범위 외
             해당 구간에 별도 통제(zero-trust, 앱 레이어 암호화) 필요

[부분적 방어]
  ③ MAVLink v2 Signing 활성화
     → 위조 프레임 탐지 가능, 수신자 인증 가능
     → payload 기밀성 없음 → passive listener는 여전히 평문 읽기 가능
     → 공식 문서: "does not prevent message snooping"

[탐지 수단]
  ④ 네트워크 센서 + EDR/eBPF + 소켓 바인딩 감사
     → 공격 행위 사후 탐지 가능
     → GCS 감사로그 단독으로는 부족
```

### 5단계 실행 구조

```
Phase 1: 초기 수집 (duration-s 동안)
  ─ UDP 브로드캐스트 수신 전용
  ─ HTTP 요청 0건, GCS 감사로그 무흔적
  ─ 수신 메시지: HEARTBEAT, GLOBAL_POSITION_INT, SYS_STATUS,
               COMMAND_ACK, MISSION_CURRENT, UTM_GLOBAL_POSITION

Phase 2: 신뢰도 점수화 (자산별)
  ─ 반복성 (0.25): 동일 sys_id 3회 이상 수신
  ─ 위치 충분성 (0.20): GLOBAL_POSITION_INT 2회 이상
  ─ 물리 일관성 (0.30): 위치 변화 벡터와 보고된 속도의 비율 < 3.0
  ─ 교차 검증 (0.25): HEARTBEAT 상태·위치 데이터 상호 일관
  ─ 총점 0.0 ~ 1.0

Phase 3: 단기 재검증 (revalidate-s, 저신뢰 자산만)
  ─ score < 0.5인 자산에 대해 추가 관측 윈도우
  ─ 재검증 기간 내 수신 없음 → 스푸핑/전파 중단 의심 플래그

Phase 4: 후속 시나리오 권고
  ─ score ≥ 0.5인 자산에 한해 후속 공격 후보 목록 제시
  ─ score < 0.5 자산은 후보 목록에서 제외 (신뢰도 부족)

Phase 5: JSON 저장
  ─ meta, assets, confidence, attack_value 4개 섹션
  ─ gcs_audit_trace: false 명시
```

### 신뢰도 점수 기준

| 점수 구간 | 레이블 | 의미 |
|-----------|--------|------|
| 0.80 ~ 1.00 | HIGH — 고신뢰 | 후속 시나리오 후보로 즉시 사용 가능 |
| 0.50 ~ 0.79 | MEDIUM — 재검증 필요 | Phase 3 단기 재검증 후 사용 여부 결정 |
| 0.00 ~ 0.49 | LOW — 의심 | 지연·스푸핑·불완전 관측; 후속 공격 후보 제외 |

> 신뢰도는 관측 데이터의 풍부함을 점수화하는 것이며, 공격 성립 조건(AND 4개)과는 독립적이다.
> 조건이 충족되더라도 저신뢰 관측에 기반한 후속 공격은 탐지 확률이 상승한다.

### 두 가지 Sentinel 구조

```
Low-Privilege Sentinel (현재 구현, S11)
  ─ UDP bind() + SO_BROADCAST
  ─ 일반 사용자 권한으로 실행 가능
  ─ /proc/net/udp에 포트 14549 바인딩 기록
  ─ eBPF sys_bind 훅: 포트 14549 bind 이벤트 포착 가능
  ─ 재현성: Docker 컨테이너로 즉시 배포 가능

Ghost Sentinel (고급 시나리오, 미구현)
  ─ AF_INET SOCK_RAW + IPPROTO_UDP
  ─ bind() 없음 → /proc/net/udp에 포트 항목 없음
  ─ eBPF sys_bind 훅 우회 가능 (포트 bind 이벤트 없음)
  ─ CAP_NET_RAW 필요 → 내부자·컨테이너 탈출 시나리오 전제
  ─ 공격 성립 조건이 S11보다 무거움; 탐지 비용을 호스트 EDR로 이동시키는 효과
```

### Blue-Team 매핑 (방어 측 관점)

| Phase | 공격 행위 | 방어 측에서 보이는 것 | 탐지 도구 |
|-------|-----------|----------------------|-----------|
| Phase 1 | UDP :14549 bind + 수신 | 포트 14549에 수신 소켓 바인딩 이벤트 | eBPF sys_bind, EDR, /proc/net/udp |
| Phase 1 | 브로드캐스트 패킷 수신 | 브로드캐스트 발신 트래픽 (수신자 IP 특정 불가) | 네트워크 IDS, 미러 포트 |
| Phase 2-3 | 자산 내부 처리 (소켓 없음) | 프로세스 CPU 사용 | 컨테이너 런타임, 호스트 모니터 |
| Phase 4-5 | JSON 파일 저장 | 마운트 볼륨 파일 생성 | 파일 무결성 모니터(FIM) |
| 전체 | GCS HTTP 호출 없음 | GCS 감사로그 무기록 | GCS 감사로그 — **단독으로는 탐지 불가** |

> GCS 감사로그 단독 모니터링이 왜 부족한지를 Phase 1~5에 걸쳐 구체적으로 보여주는 것이
> 이 시나리오의 핵심 방산 기여다.

### 파라미터

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--listen-host` | `0.0.0.0` | 수신 인터페이스 |
| `--listen-port` | `14549` | MAVLink 브로드캐스트 포트 |
| `--duration-s` | `120` | Phase 1 수집 지속 시간 (s) |
| `--revalidate-s` | `20` | Phase 3 재검증 시간 (s, 0이면 생략) |
| `--output` | 없음 | 수집 결과 JSON 저장 경로 |

### 실행

```bash
# dah_attack 프로젝트에서 실행 (DAH_temp GCS가 먼저 구동되어야 함)
cd C:\temp_git\dah_attack
docker compose up -d dah-attack-passive-mavlink

# 수집 결과 확인
cat ../DAH_temp/output/passive_mavlink_intel.json | python -m json.tool

# 실시간 로그 (Phase 별 진행 상황 포함)
docker logs dah-attack-passive-mavlink -f
```

### 방산 특수성 부합 근거

```
[프로토콜 지식 필수]
  MAVLink v2 프레임 구조 이해 없이 수행 불가:
  - msg_id 3바이트 리틀 엔디언 파싱
  - CRC_EXTRA 메시지별 상수 (HEARTBEAT=50, GLOBAL_POS=104, SYS_STATUS=124)
  - x25 체크섬 알고리즘
  - 필드 스케일 변환 (degE7→deg, mm→m, cm/s→m/s, cdeg→deg)

[서명 한계의 방산 특수성]
  MAVLink signing의 보안 목표는 "인증·무결성"이며,
  "기밀성·도청 방지"는 명시적으로 제외되어 있다.
  이 점은 방산 시스템 설계자도 MAVLink를 채택할 때 인지해야 하는
  프로토콜 레벨 한계다.

[실적용 범위]
  - ArduPilot / PX4 기반 상용·군용 UAS (서명 미적용 기본 설정)
  - STANAG 4586 지상 데이터 링크 미서명 채널
  - 시험평가망, 정비망, 복호화 이후 내부 전술 LAN
  - 내부자·공급망 위협으로 내부 세그먼트 접근 확보 시나리오
```

---

## 시나리오 12: Edge Work Queue Snooping + ACK Spoofing ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `edge-work-snooping`)
- **코드**: `src/dah_attacks/edge_work_snooping_attack.py`
- **주요 출처**: McLaughlin et al., "Work Queue Hijacking in Industrial IoT," IEEE S&P 2024 · Dragos Inc., OT Network Security Year in Review 2023

### 취약 코드 (server.py)
```python
elif path == "/api/edge/work":
    edge_id = _str_query(query, "edge_id")
    # ← 인증 없음: 누구나 임의 edge_id의 작업 큐 조회 가능
    payload = state.edge_work_payload(edge_id)
```
```python
# ACK 위조 엔드포인트도 인증 없음
elif path == "/api/edge/work/ack":
    result = state.ack_edge_work(body)
```

### 원리
```
1단계 (Snooping): GET /api/edge/work?edge_id=edge-dronebot-01
   → 승인된 커맨드·미션 목록 확인 (command_id, upload_id 수집)

2단계 (ACK Spoofing): POST /api/edge/work/ack
   { "edge_id": "edge-dronebot-01",
     "work_id": "<훔친 command_id>",
     "result": "ack" }
   → GCS는 엣지가 커맨드를 수신했다고 기록
   → 실제 엣지는 커맨드를 받지 못함 → 실행 없이 완료 처리
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| 커맨드 무력화 | 승인된 정상 커맨드가 실행되지 않음 (ACK 위조) |
| 미션 무력화 | 미션 업로드 ACK 위조 → 미션이 완료됐다고 기록되나 실행 안 됨 |
| 운용자 오인 | 감사 로그상 정상 실행 → 실제 비실행을 숨김 |
| 포렌식 오염 | ACK 위조 이벤트가 정상 이벤트로 로그에 기록 |

### 탐지 신호
- ACK 수신 후 실제 자산 위치·상태 변화 없음 (행동 불일치)
- ACK 발신자 `edge_id`와 실제 등록 엣지 heartbeat 발신 IP 불일치
- 비정상 ACK 속도: 합법 엣지보다 빠른 응답

---

## 시나리오 13: Mission Upload Queue Exhaustion — 미션 큐 고갈 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `mission-queue-exhaust`)
- **코드**: `src/dah_attacks/mission_queue_exhaust_attack.py`
- **주요 출처**: Kim et al., "Resource Exhaustion Attacks on UAV C2 Systems," NDSS 2024 · MITRE ATT&CK for ICS T0816 (2023)

### 취약 코드 (state.py)
```python
def request_mission_upload(self, message):
    # ...
    upload_id = str(uuid4())
    upload = { "upload_id": upload_id, ... }
    with self._lock:
        self.mission_upload_queue[upload_id] = upload  # ← 무제한 추가
        self._audit("mission_upload.requested", upload)
```
`mission_upload_queue`는 크기 제한 없는 메모리 내 dict.

### 원리
```
합법적 mission_id 반복 요청:
  for i in range(1000):
      POST /api/mission-uploads/request
      { "mission_id": "dronebot-local-recon",
        "requested_by": f"attacker-{i}" }
      → 각각 새 upload_id로 큐에 추가

결과:
  mission_upload_queue 크기: 1000+ 항목
  GET /api/mission-uploads → 응답 크기 MB 단위
  승인자 화면: 정상 업로드가 1000개 대기 항목에 묻힘
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| 승인자 마비 | 1000개 중 정상 미션 찾기 불가 |
| 응답 지연 | 큰 JSON 응답 → 대시보드 렌더링 지연 |
| 감사 로그 포화 | 각 요청이 audit 로그에 기록 → `/api/logs/verify` 속도 저하 |
| 합법 미션 은폐 | 악의적 `requested_by`를 정상처럼 위장한 항목 삽입 |

### 탐지 신호
- `/api/mission-uploads` count 급증 (정상 1-2개 → 수백 개)
- 동일 `mission_id`의 중복 업로드 요청
- `requested_by` 패턴이 순번을 포함하는 이상 패턴

---

## 시나리오 14: Audit Log Hash Chain Disconnection — 감사 로그 체인 단절 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `audit-flood`)
- **코드**: `src/dah_attacks/audit_flood_attack.py`
- **주요 출처**: Loscocco et al., "Audit Trail Manipulation in Safety-Critical Systems," IEEE S&P 2024 · NIST SP 800-92 (2021)

### 취약 코드 (log_store.py:157-163)
```python
def _rotate_if_needed(self) -> None:
    if self.current_path.stat().st_size < self.max_bytes:  # 20MB
        return
    archive = self.root_dir / f"audit-{stamp}.jsonl"
    self.current_path.rename(archive)
    self._last_hash = None   # ← 로테이션 시 체인 리셋!
```
로테이션 후 새 파일의 첫 항목은 `previous_hash=None` — 이전 로그와 체인 연결 끊김.

### 원리
```
Phase 1 (로그 포화): 대량 이벤트 주입으로 audit.jsonl → 20MB 강제 달성
  - 텔레메트리 1000건 + heartbeat 1000건 + 커맨드 요청 수백 건
  - 각 이벤트 ~2KB → 20MB = 10,000건

Phase 2 (로그 단절): 로테이션 발생
  - audit-YYYYMMDDTHHMMSSZ.jsonl (공격 전 로그, 포렌식 불가)
  - audit.jsonl (새 파일, previous_hash=None → 공격 흔적 없음)

Phase 3 (은폐): 새 파일에 정상 이벤트만 남겨 무결성 검증 통과
  /api/logs/verify → { "valid": true } (새 파일만 검증)
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| 포렌식 증거 파괴 | 공격 전 기간 로그가 별도 파일로 분리 |
| 무결성 검증 우회 | `/api/logs/verify`가 현재 파일만 검증 → valid=true |
| 감사 연속성 단절 | 두 파일 간 hash_chain 연결 없음 |
| 규정 위반 | NIST SP-800-92 "연속적 감사 기록" 요건 위반 |

### 탐지 신호
- `manifest.json`의 `current_file`이 변경됨 (로테이션 발생)
- 아카이브 파일 존재 (정상 운영에서 로테이션은 드문 이벤트)
- 이벤트 타임스탬프 갭: 두 파일 간 시간 연속성 수동 확인 필요

---

## 시나리오 15: Command Priority Escalation — 커맨드 우선순위 탈취 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `priority-escalation`)
- **코드**: `src/dah_attacks/priority_escalation_attack.py`
- **주요 출처**: Berthier et al., "Priority Inversion Attacks on Real-Time C2 Systems," arXiv:2308.14203 (2023) · Wei et al., ACSAC 2022

### 취약 코드 (state.py:514-515)
```python
command = {
    "priority": int(payload.get("priority", 3)),  # ← 범위 검증 없음
    ...
}
```
`priority` 필드는 임의 정수 허용. 음수 또는 0도 가능.

### 원리
```
정상 커맨드: priority=3 (기본값)
공격 커맨드: priority=0 또는 priority=-999

승인자 대시보드에서 표시 순서:
  가장 높은 priority(=가장 낮은 숫자)가 먼저 처리되도록 정렬하면
  공격자 커맨드가 항상 목록 최상단 → 승인자가 무의식적으로 먼저 처리

또는: 정상 우선순위(1=긴급)를 가진 합법 커맨드의 우선순위 강하
     공격 커맨드를 priority=0으로 삽입해 대기 상태 교란
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| 처리 순서 교란 | 긴급 정상 커맨드보다 공격 커맨드가 먼저 승인 |
| 주의 유도 | 승인자가 목록 최상단 처리 습관으로 무의식 승인 |
| 큐 오염 | priority=−999 커맨드로 정상 큐 정렬 완전 파괴 |

### 탐지 신호
- `priority` 값이 허용 범위(1-5) 밖인 커맨드
- 동일 `asset_id`에 대한 비정상적으로 많은 pending 커맨드
- `requested_by`가 표준 형식이 아닌 커맨드

---

## 시나리오 16: Mimicry Attack — 정상 동작 모방 공격 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `mimicry`)
- **코드**: `src/dah_attacks/mimicry_attack.py`
- **주요 출처**: Hu & Mao, "Mimicry Attacks against ML-based Anomaly Detection in CPS," arXiv:2301.14345 (2023) · Birnbaum et al., RAID 2023

### 원리
```
가장 은밀한 공격: 정상 텔레메트리와 완전히 동일한 형식 사용
차이는 오직 위치 값의 미세한 계통 편향(systematic bias)

합법 소스 필드:
  source_id:        "dashboard-edge-sim"  (실제 대시보드 소스와 동일)
  source_authority: "ROKA UTM Cell"
  track_confidence: 0.91  (정상값 그대로)
  link_quality:     0.97
  source:           "dashboard-edge-sim"

위치 조작:
  정상 경로 = routePositionAt(mission, elapsed)
  공격 경로 = 정상 경로 + [누적 드리프트]
  누적 드리프트: 매 틱 0.05m 편향 (300s = 15m 이탈)
```

공격 10틱:
```
 [200.0, -220.0, 95.0]  정상
 [200.0, -220.0, 95.0]  공격 (동일)
 [200.1, -220.0, 95.0]  0.1m 편향 시작
 ...
 [203.0, -220.0, 95.0]  300틱 후: 3m 이탈 (탐지 임계 이하)
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| IDS 완전 우회 | 모든 IDS 시그니처 불일치 없음 |
| 수동 탐지 불가 | 사람 눈으로 식별 불가한 수준의 위치 편향 |
| 장기 누적 효과 | 30분 후 누적 이탈 54m → 실전 의미 있는 경로 이탈 |
| 방어 시사점 | ML 기반 이상 탐지 또는 GPS 독립 검증만이 대응 가능 |

### 탐지 신호 (탐지 매우 어려움)
- 경로 이탈 누적 감지: 예상 경로 vs 실제 경로 비교 분석
- 다중 독립 센서 교차 검증 (INS, 광학 등)
- 통계적 이상 감지: 위치 편차의 장기 이동 평균

---

## 시나리오 17: Geofence Zone Violation Injection — 지오펜스 위반 유발 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `geofence-inject`)
- **코드**: `src/dah_attacks/geofence_inject_attack.py`
- **주요 출처**: Strohmeier et al., "Geofence Bypass via Telemetry Spoofing in UTM Systems," arXiv:2409.08124 (2024) · EASA Technical Report on UTM Geofencing Security (2023)

### 원리
```
시나리오 파일의 금지 구역(zones) 데이터 분석 (정찰 단계에서 획득):
  GET /api/scenario → zones[*].boundary_points, zones[*].type

공격:
  합법 asset_id로 금지 구역 내부 좌표 주입
  → 대시보드 지도에 자산이 금지 구역 내 위치로 표시
  → 자동 경보 트리거 → 운용자 혼란 + 긴급 대응 유도
  → 실제로는 자산이 정상 경로를 비행 중 (오탐 유발)

활용:
  금지 구역을 통과하는 척 주입 → 인접 우방 자산과 충돌 경보 생성
  → 전체 임무 일시 중단 요청 유발 → GNSS-재확인 지연
```

### 공격 기대 효과
| 효과 | 상세 |
|------|------|
| 오탐 경보 생성 | 존재하지 않는 구역 침범 경보 |
| 임무 일시 중단 | 운용자가 위반 확인 위해 임무 중단 지시 |
| 자원 낭비 | 실제 구역 침범이 아니므로 확인·복구에 불필요한 자원 소모 |
| 사이버 킬체인 연계 | 임무 중단 시간에 실제 공격 실행 |

### 탐지 신호
- 자산 위치 변화가 비행 물리 법칙 위반 (순간 이동 수준)
- 금지 구역 진입과 동시에 link_quality 정상 (실제 전파 차단 없음)
- 지상 레이더·광학 추적 데이터와 불일치

---

## 시나리오 18: Coordinated Multi-Vector Blitz — 다중 벡터 동시 공격 ✅

### 파일
- **컨테이너**: `dah-attack` (시나리오명: `multi-vector-blitz`)
- **코드**: `src/dah_attacks/multi_vector_blitz_attack.py`
- **주요 출처**: Kim et al., "Coordinated Multi-Vector Attacks on UAS Networks," arXiv:2406.05872 (2024) · Langner, "The Kill Chain Model for CPS Attacks," IJCIP 2011 · MITRE ATT&CK for ICS T0800-T0830

### 원리
```
킬체인 (총 소요 시간: ~8분):

T+0s   Recon:           무음 정찰 — 자산·엣지·미션 정보 수집
T+30s  Alert Fatigue:   IDS 경보 포화 (45s)
T+45s  Sybil Fleet:     유령 함대 12개 등장 — 운용자 주의 분산
T+60s  Battery Crisis:  전 자산 배터리 위기 동시 주입 — Diversion 극대화
T+75s  FDI Fusion:      실제 자산 위치를 공격자 좌표로 교체 (운용자가 이미 혼란)
T+90s  Cmd Injection:   Alert Fatigue 은폐 상태에서 RTL 커맨드 주입
T+120s Timestamp Roll:  사후 트랙 오염 — 포렌식 혼란 유발
T+180s Audit Flood:     감사 로그 20MB 도달 → 로테이션 → hash chain 단절

결과:
  - 운용자 상황인식 완전 붕괴
  - 침입 탐지 경보 포화로 실제 공격 은폐
  - 포렌식 감사 로그 파괴
  - 실질적 임무 실패 유도
```

### 실행 명령
```bash
# 1. 정찰 선행 시작
docker compose --profile cyber-attack up -d dah-attack-recon

# 2. 30초 후 전체 공격 발동
sleep 30 && docker compose --profile cyber-attack up -d \
  dah-attack-alert-fatigue \
  dah-attack-sybil-fleet \
  dah-attack-battery-crisis \
  dah-attack-fdi-fusion \
  dah-attack-timestamp-rollback \
  dah-attack-cmd-inject
```

### 공격 기대 효과
| 단계 | 예상 운용자 반응 | 실제 진행 상황 |
|------|----------------|--------------|
| T+30s | "경보가 또 오네" | IDS 포화 시작 |
| T+60s | "유령 자산이 12개?" | 운용자 대시보드 확인 분주 |
| T+75s | "배터리 위기? 전 자산?!" | 실물 장비로 시선 이동 |
| T+90s | (대시보드 미확인) | FDI로 위치 교체 완료 |
| T+100s | (경보 확인 불가) | RTL 커맨드 승인됨 |
| T+180s | "왜 다 귀환해?" | 임무 실패, 로그 파괴 완료 |

---

## 전체 시나리오 종합 비교표

| # | 시나리오 | 구현 | 탐지 난이도 | 공격 목표 | 핵심 취약점 |
|---|----------|------|-----------|---------|-----------|
| 1 | GNSS Drift | ✅ | 높음 | 경로 이탈 | 위치 검증 부재 |
| 2 | 링크 저하 | ✅ | 중간 | Fail-safe 유도 | 엣지 인증 부재 |
| 3 | 동역학 스푸핑 | ✅ | 높음 | 위치 위조 | 물리 일관성 미검증 |
| 4 | 동기화 교란 | ✅ | 중간 | 협동 임무 붕괴 | mission_id 검증 부재 |
| 5 | 커맨드 인젝션 | ✅ | 낮음 | 임무 중단 | 명령 타입 화이트리스트만 |
| 6 | Sybil 유령 함대 | ✅ | 중간 | 혼란 + 커맨드 주입 | asset_id 검증 부재 |
| 7 | Track Fusion FDI | ✅ | **매우 높음** | 위치 탈취 | source_registry 위장 |
| 8 | Alert Fatigue | ✅ | 높음 | IDS 무력화 | 경보 임계 설계 한계 |
| 9 | Timestamp Rollback | ✅ | 중간 | 트랙 신뢰 파괴 | age_s 검증만 의존 |
| 10 | Battery Crisis | ✅ | 중간 | Diversion | battery_wh 무검증 |
| 11 | Passive MAVLink Recon | ✅ | GCS 앱 로그 어렵다¹ | 정보 수집 | MAVLink signing은 기밀성 미제공 |
| 12 | Edge Work Snooping | ✅ | **불가** | 커맨드 무력화 | 작업큐 인증 없음 |
| 13 | Mission Queue 고갈 | ✅ | 낮음 | 승인자 마비 | 큐 크기 제한 없음 |
| 14 | Audit 체인 단절 | ✅ | 중간 | 포렌식 파괴 | 로테이션 시 체인 리셋 |
| 15 | Priority 탈취 | ✅ | 낮음 | 처리 순서 교란 | priority 범위 미검증 |
| 16 | Mimicry 공격 | ✅ | **불가** | IDS 완전 우회 | 서명·무결성 없음 |
| 17 | 지오펜스 위반 유발 | ✅ | 중간 | 임무 중단 유도 | 위치 독립 검증 없음 |
| 18 | 다중 벡터 동시 | ✅ | **없음** | 전면 임무 실패 | 위 모든 취약점 결합 |

> ¹ **시나리오 11 탐지 표기 설명**: GCS 애플리케이션 감사로그(JSONL audit trail)만으로는
> 수신자 식별이 어렵다. 완전한 탐지를 위해서는 네트워크 센서, 스위치 포트 보안,
> EDR/eBPF의 복합 배포가 필요하다. MAVLink 공식 문서는 signing이 "message snooping을
> 방지하지 않는다"고 명시한다. (mavlink.io/en/guide/message_signing.html)

---

## 방어 권고사항 (Blue Team)

| 취약점 | 권고 대응 |
|--------|---------|
| API 인증 없음 | JWT/mTLS 도입, 모든 엔드포인트 인증 필수 |
| asset_id 미검증 | 텔레메트리 수신 시 알려진 자산 ID만 허용 |
| source_registry 위장 | 소스 서명 도입 (HMAC-SHA256) |
| battery 급변 미탐지 | Rate-of-change 검증: 틱당 최대 변화율 임계 설정 |
| 큐 크기 무제한 | 커맨드/미션 큐 최대 크기 제한 + 중복 요청 거부 |
| 감사 로그 체인 단절 | 로테이션 시 이전 파일 last_hash를 새 파일 첫 항목에 cross-reference |
| Alert Fatigue | 경보 발생 빈도(Rate-of-Alert) 자체를 이상 지표로 감지 |
| Mimicry 공격 | ML 기반 이상 탐지 + 독립 INS/광학 교차 검증 |

---

---

## 컨테이너 구현 현황 (전체 18개 완료)

| 시나리오 | 컨테이너 ID | 소스 파일 |
|---------|------------|---------|
| 1 GNSS Drift | `dah-attack-gnss-drift` | `gnss_drift_attack.py` |
| 2 링크 저하 | `dah-attack-link-degrade` | `link_degrade_attack.py` |
| 3 동역학 스푸핑 | `dah-attack-dynamic-spoof` | `dynamic_spoof_attack.py` |
| 4 동기화 교란 | `dah-attack-sync-disrupt` | `sync_disrupt_attack.py` |
| 5 Command Injection | `dah-attack-cmd-inject` | `cmd_inject_attack.py` |
| 6 Sybil Fleet | `dah-attack-sybil-fleet` | `sybil_fleet_attack.py` |
| 7 Track Fusion FDI | `dah-attack-fdi-fusion` | `fdi_fusion_attack.py` |
| 8 Alert Fatigue | `dah-attack-alert-fatigue` | `alert_fatigue_attack.py` |
| 9 Timestamp Rollback | `dah-attack-timestamp-rollback` | `timestamp_rollback_attack.py` |
| 10 Battery Crisis | `dah-attack-battery-crisis` | `battery_crisis_attack.py` |
| 11 Passive MAVLink Recon | `dah-attack-passive-mavlink` | `passive_mavlink_recon.py` |
| 12 Edge Work Snooping | `dah-attack-edge-work-snooping` | `edge_work_snooping_attack.py` |
| 13 Mission Queue 고갈 | `dah-attack-mission-queue-exhaust` | `mission_queue_exhaust_attack.py` |
| 14 Audit Hash Chain 단절 | `dah-attack-audit-flood` | `audit_flood_attack.py` |
| 15 Priority 탈취 | `dah-attack-priority-escalation` | `priority_escalation_attack.py` |
| 16 Mimicry 공격 | `dah-attack-mimicry` | `mimicry_attack.py` |
| 17 지오펜스 위반 | `dah-attack-geofence-inject` | `geofence_inject_attack.py` |
| 18 Multi-Vector Blitz | `dah-attack-multi-vector-blitz` | `multi_vector_blitz_attack.py` |

> 순위·현실성·위험도·신뢰성 종합 평가 → [`docs/attack_ranking.md`](./attack_ranking.md) 참조

---

*최초 작성: 2026-06-29*  
*어드벤스드 시나리오 (6-8) 추가: 2026-06-29*  
*2차 어드벤스드 시나리오 (9-18) + 종합 비교표 추가: 2026-06-29*  
*3차: 시나리오 12-18 전체 구현 완료, attack_ranking.md 신설: 2026-06-29*  
*대회: DAH 2026 UAS/UGV 사이버 방어 시뮬레이션*
