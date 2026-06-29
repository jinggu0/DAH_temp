# DAH 2026 공격 시나리오 종합 평가 및 순위

> **평가 기준**: 현실성(Realism) · 위험도(Impact) · 신뢰성(Reliability)  
> **비교 기준**: DAH 예선 안내서 PDF 유사 시나리오 존재 여부 ✅ = PDF에 유사 항목 있음  
> **환경**: 폐쇄형 Docker 로컬 환경 (fault/anomaly injection 전용)  
> **작성일**: 2026-06-29 | 총 시나리오: 18개 (전체 구현 완료 ✅)

---

## 평가 기준 정의

| 기준 | 설명 | 점수 범위 |
|------|------|----------|
| **현실성** | 실제 UAS 운용 환경에서 발생 가능한 공격인가 (학술 레퍼런스, 실전 사례 기반) | 1-10 |
| **위험도** | 공격 성공 시 임무·인명·장비에 미치는 영향 규모 | 1-10 |
| **신뢰성** | 이 시뮬레이션 환경에서 재현 가능한 정도 (GCS 코드 취약점 직결 여부) | 1-10 |
| **탐지 난이도** | 방어자(Blue Team)가 탐지하기 어려운 정도 | 1-10 |

---

## 종합 순위표

> 종합 점수 = (현실성 × 0.30) + (위험도 × 0.35) + (신뢰성 × 0.25) + (탐지 난이도 × 0.10)

| 순위 | # | 시나리오 | PDF 유사 | 구현 | 현실성 | 위험도 | 신뢰성 | 탐지 난이도 | 종합 점수 |
|------|---|---------|---------|------|-------|-------|-------|-----------|---------|
| 🥇 1 | 18 | Multi-Vector Blitz | — | ✅ | 9.5 | 10.0 | 9.0 | 9.5 | **9.6** |
| 🥈 2 | 7  | Track Fusion FDI | — | ✅ | 9.0 | 9.5 | 9.5 | 9.5 | **9.4** |
| 🥉 3 | 16 | Mimicry 공격 | — | ✅ | 9.0 | 8.5 | 9.0 | 10.0 | **9.1** |
| 4 | 8  | Alert Fatigue | — | ✅ | 8.5 | 8.5 | 9.0 | 8.5 | **8.7** |
| 5 | 11 | Silent Recon | — | ✅ | 9.5 | 7.0 | 10.0 | 10.0 | **8.7** |
| 6 | 1  | GNSS Drift | ✅ | ✅ | 9.0 | 8.5 | 8.5 | 8.0 | **8.7** |
| 7 | 3  | 동역학 GPS 스푸핑 | ✅ | ✅ | 8.5 | 8.5 | 8.5 | 8.5 | **8.5** |
| 8 | 14 | Audit Hash Chain 단절 | — | ✅ | 8.0 | 8.5 | 8.5 | 7.5 | **8.3** |
| 9 | 6  | Sybil 유령 함대 | — | ✅ | 8.0 | 8.0 | 9.0 | 7.0 | **8.2** |
| 10 | 17 | 지오펜스 위반 유발 | — | ✅ | 8.5 | 7.5 | 8.5 | 7.0 | **8.1** |
| 11 | 12 | Edge Work Snooping | — | ✅ | 8.0 | 8.0 | 8.0 | 9.0 | **8.1** |
| 12 | 9  | Timestamp Rollback | — | ✅ | 7.5 | 7.5 | 9.0 | 7.0 | **7.9** |
| 13 | 2  | 링크 저하 Fail-safe | ✅ | ✅ | 9.0 | 8.0 | 7.5 | 6.0 | **7.9** |
| 14 | 4  | 협동 임무 동기화 교란 | ✅ | ✅ | 8.0 | 7.5 | 8.0 | 6.5 | **7.6** |
| 15 | 15 | Priority 탈취 | — | ✅ | 7.0 | 7.5 | 8.5 | 6.5 | **7.5** |
| 16 | 5  | Command Injection | ✅ | ✅ | 8.5 | 7.5 | 8.0 | 4.0 | **7.5** |
| 17 | 10 | Battery Crisis | — | ✅ | 7.5 | 7.0 | 8.5 | 5.5 | **7.3** |
| 18 | 13 | Mission Queue 고갈 | — | ✅ | 6.5 | 6.5 | 9.0 | 5.0 | **7.0** |

---

## 시나리오별 상세 평가

---

### 🥇 1위 · 시나리오 18: Coordinated Multi-Vector Blitz

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-multi-vector-blitz`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 9.5/10 | 실전 APT 킬체인 구조 (Stuxnet, NotPetya 사례와 동일한 다중 벡터 접근) |
| 위험도 | 10.0/10 | 상황인식 붕괴 + IDS 무력화 + 포렌식 파괴가 동시 발생 → 임무 전면 실패 |
| 신뢰성 | 9.0/10 | 각 구성 공격이 이미 개별 검증됨. 조율 타이밍만 변수 |
| 탐지 난이도 | 9.5/10 | 여러 공격이 동시에 진행되므로 IDS가 근본 원인 식별 불가 |

**공격 기대 효과**:
- 30~180초 내 운용자 상황인식 완전 붕괴
- 경보 포화 + 유령 함대 + 배터리 위기로 시선 분산
- FDI로 위치 위조된 상태에서 RTL 커맨드가 승인
- 감사 로그 hash chain 단절로 사후 포렌식 불가

**실행 방법**:
```bash
# 오케스트레이터 단일 컨테이너 (내장 킬체인)
docker compose --profile cyber-attack up dah-attack-multi-vector-blitz

# 또는 기존 컨테이너 시간차 실행
docker compose --profile cyber-attack up -d dah-attack-recon
sleep 30 && docker compose --profile cyber-attack up -d \
  dah-attack-alert-fatigue dah-attack-sybil-fleet \
  dah-attack-battery-crisis dah-attack-fdi-fusion \
  dah-attack-timestamp-rollback dah-attack-cmd-inject
```

---

### 🥈 2위 · 시나리오 7: Track Fusion FDI

> **PDF 유사**: 없음 (독창) — PDF에 단순 GPS 스푸핑은 있으나 source_registry 탈취는 없음  
> **컨테이너**: `dah-attack-fdi-fusion`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 9.0/10 | ICS/SCADA FDI는 Stuxnet 이후 검증된 공격 클래스. UAV C2 적용은 arXiv:2104.09907 |
| 위험도 | 9.5/10 | fused_position 탈취 = 자산의 표시 위치를 완전히 제어. 충돌·금지구역 진입 유발 가능 |
| 신뢰성 | 9.5/10 | source_registry 조회 코드(`state.py`) 직접 분석 후 설계. 재현 가능 |
| 탐지 난이도 | 9.5/10 | `source_id="mavlink-udp-adapter"` 위장 시 IDS 시그니처 없음. source 필드 노출 없으면 완전 은닉 |

**공격 기대 효과**:
- 운용자 대시보드의 자산 위치가 공격자 지정 좌표로 교체
- `track_confidence=0.97`로 정상 소스(0.92)를 압도 → 자동으로 primary 소스 탈취
- 점진적 이동(`_smooth_move`)으로 kinematic 탐지 회피
- 실전에서는 source 필드를 정상값으로 바꾸면 IDS 완전 우회

---

### 🥉 3위 · 시나리오 16: Mimicry 공격

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-mimicry`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 9.0/10 | ML 이상 탐지 우회용 mimicry 공격은 arXiv:2301.14345에서 실험적으로 검증 |
| 위험도 | 8.5/10 | 30분 지속 시 54m 위치 이탈. 정밀 타격 임무에서 작전 실패로 직결 |
| 신뢰성 | 9.0/10 | 단순 필드 복사 + 미세 편향이므로 구현 실패 요소 없음. 가장 안정적 |
| 탐지 난이도 | 10.0/10 | 모든 IDS 시그니처가 정상. 규칙 기반 탐지 완전 우회 |

**공격 기대 효과**:
- IDS 경보 0건 (완전 은닉)
- 120초 운용 시 6m 이탈 (탐지 임계 이하)
- 장기 운용일수록 누적 피해 증가 (선형 성장)
- Blue Team에게 ML 이상 탐지 도입의 필요성을 가장 명확히 시연

---

### 4위 · 시나리오 8: Alert Fatigue + Masked Command Injection

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-alert-fatigue`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.5/10 | 병원·원전 ICS에서 실증된 경보 피로 공격. USENIX Security 2024 논문 기반 |
| 위험도 | 8.5/10 | 경보 포화 상태에서 숨겨진 RTL 주입 → 임무 중단. IDS를 무기로 역이용 |
| 신뢰성 | 9.0/10 | IDS dedup window(10s), 50개 cap 취약점 코드에서 직접 확인 |
| 탐지 난이도 | 8.5/10 | Phase 1 경보는 정상 트리거. Phase 2 커맨드는 경보 목록 하단에 묻힘 |

---

### 5위 · 시나리오 11: Silent Reconnaissance

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-recon`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 9.5/10 | REST API 무인증 열거는 모든 실제 공격의 1단계. USENIX 2023 기반 |
| 위험도 | 7.0/10 | 직접 피해 없음. 그러나 모든 후속 공격의 정확도를 극대화 |
| 신뢰성 | 10.0/10 | 실제로 구동하여 모든 15개 엔드포인트 열거 성공 확인 |
| 탐지 난이도 | 10.0/10 | GET 요청만 사용 → 감사 로그에 기록 없음. 탐지 완전 불가 |

---

### 6위 · 시나리오 1: GNSS Drift 누적 공격 ✅ PDF 유사

> **PDF 유사**: ✅ (PDF 시나리오 #2/#7 — GPS 스푸핑·위치 조작)  
> **컨테이너**: `dah-attack-gnss-drift`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 9.0/10 | GPS 스푸핑은 실제 전장에서 이미 사용 중 (우크라이나 전선 GPD jamming/spoofing) |
| 위험도 | 8.5/10 | 120초 후 40m+ 누적 이탈 → 우방 자산과 충돌 또는 임무 실패 |
| 신뢰성 | 8.5/10 | 점진적 drift 로직이 GCS 위치 검증 부재 취약점에 직결 |
| 탐지 난이도 | 8.0/10 | 단일 틱 변화량이 임계 이하. 누적 분석 없으면 탐지 어려움 |

---

### 7위 · 시나리오 3: 동역학 일치 GPS 스푸핑 ✅ PDF 유사

> **PDF 유사**: ✅ (PDF 시나리오 #10 — GPS 스푸핑, 단 물리 일관성 유지는 독창)  
> **컨테이너**: `dah-attack-dynamic-spoof`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.5/10 | arXiv:2501.07597에서 동역학 일관성 스푸핑의 탐지 우회 능력 실험 검증 |
| 위험도 | 8.5/10 | velocity·heading도 위조 경로와 일치 → 물리 법칙 기반 탐지 우회 |
| 신뢰성 | 8.5/10 | 원형 궤도 공식이 수학적으로 일관. _smooth_move 버그 수정 완료 |
| 탐지 난이도 | 8.5/10 | 단순 kinematic 체크(속도-위치 불일치)로 탐지 불가 |

---

### 8위 · 시나리오 14: Audit Hash Chain 단절

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-audit-flood`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.0/10 | 포렌식 증거 파괴는 실제 사이버 범죄에서 표준 사후 처리 |
| 위험도 | 8.5/10 | /api/logs/verify가 valid=true 반환 → 감사 체계 신뢰성 완전 파괴 |
| 신뢰성 | 8.5/10 | log_store.py:157 _last_hash=None 코드가 직접 취약점 |
| 탐지 난이도 | 7.5/10 | 로테이션 자체는 이상 아님. 두 파일 간 체인 연결 부재가 탐지 핵심 |

---

### 9위 · 시나리오 6: Sybil Phantom Fleet

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-sybil-fleet`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.0/10 | 드론 swarm C2에서 Sybil 공격은 IEEE IoT-J 2023에서 실험 검증 |
| 위험도 | 8.0/10 | 12개 유령 항적 → 운용자 혼란 + 유령 자산 커맨드 주입 성공 |
| 신뢰성 | 9.0/10 | ingest_telemetry asset_id 미검증 취약점 코드에서 직접 확인 |
| 탐지 난이도 | 7.0/10 | SYBIL-FLEET source 필드가 IDS에 즉시 노출됨. 실전에서는 source 숨김 |

---

### 10위 · 시나리오 17: 지오펜스 위반 유발

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-geofence-inject`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.5/10 | UTM 시스템에서 지오펜스 위반 경보는 즉각 임무 중단 트리거 |
| 위험도 | 7.5/10 | 오탐 유발 → 임무 중단 → 실제 공격 창 확보 |
| 신뢰성 | 8.5/10 | 서버 측 위치-구역 검증 없음이 코드에서 확인 |
| 탐지 난이도 | 7.0/10 | 위치 급변 시 kinematic 이상으로 식별 가능 |

---

### 11위 · 시나리오 12: Edge Work Queue Snooping + ACK Spoofing

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-edge-work-snooping`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.0/10 | 산업 IoT 작업큐 하이재킹은 IEEE S&P 2024에서 실전 적용 사례 제시 |
| 위험도 | 8.0/10 | ACK 위조로 승인된 커맨드가 실행되지 않음 → 감사 로그에 정상으로 기록 |
| 신뢰성 | 8.0/10 | /api/edge/work, /api/edge/work/ack 모두 인증 없음이 코드에서 확인 |
| 탐지 난이도 | 9.0/10 | 행동 불일치(ACK 수신 후 자산 상태 변화 없음)로만 탐지 가능 |

---

### 12위 · 시나리오 9: Timestamp Rollback

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-timestamp-rollback`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 7.5/10 | 시간 기반 CPS 공격은 IEEE TIFS 2022에서 검증 |
| 위험도 | 7.5/10 | 정상 소스 전체 stale 표시 → 운용자 실시간 위치 신뢰 불가 |
| 신뢰성 | 9.0/10 | age_s = abs(t1 - t2) 코드가 직접 취약점. 재현 완벽 |
| 탐지 난이도 | 7.0/10 | TS-ROLLBACK source 필드가 IDS에 노출됨 |

---

### 13위 · 시나리오 2: 링크 저하 Fail-safe 유도 ✅ PDF 유사

> **PDF 유사**: ✅ (PDF 시나리오 #1 — C2 링크 저하/차단)  
> **컨테이너**: `dah-attack-link-degrade`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 9.0/10 | 전자전(EW)에서 링크 저하는 가장 오래된 전술. 우크라이나 전선 실제 사례 |
| 위험도 | 8.0/10 | GCS Fail-safe → 전 자산 RTL/HOLD 강제 발동 시 임무 전면 중단 |
| 신뢰성 | 7.5/10 | 실제 엣지 위장이므로 heartbeat 타이밍에 의존 |
| 탐지 난이도 | 6.0/10 | link_quality<0.3 → IDS warning 즉시 탐지 |

---

### 14위 · 시나리오 4: 협동 임무 동기화 교란 ✅ PDF 유사

> **PDF 유사**: ✅ (PDF 시나리오 #4/#16 — UAV/UGV 협동 임무 방해)  
> **컨테이너**: `dah-attack-sync-disrupt`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.0/10 | 다중 자산 협동 임무 교란은 arXiv:2312.03787에서 실전 적용 분석 |
| 위험도 | 7.5/10 | UAV 정찰 없이 UGV 진입 → 접촉 위험 또는 역할 역전 |
| 신뢰성 | 8.0/10 | mission_id 교차 주입이 GCS에서 허용됨 확인 |
| 탐지 난이도 | 6.5/10 | 자산-미션 타입 불일치로 탐지 가능 |

---

### 15위 · 시나리오 15: Command Priority 탈취

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-priority-escalation`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 7.0/10 | 우선순위 역전 공격은 RTOS 시스템에서 고전적 취약점. arXiv:2308.14203 |
| 위험도 | 7.5/10 | 운용자가 목록 상단 처리 습관으로 무의식 승인 유도 |
| 신뢰성 | 8.5/10 | priority=int() 범위 검증 없음이 코드에서 직접 확인 |
| 탐지 난이도 | 6.5/10 | priority 값 이상 여부로 탐지 가능 |

---

### 16위 · 시나리오 5: Command Injection ✅ PDF 유사

> **PDF 유사**: ✅ (PDF 시나리오 #3/#9 — 커맨드 위조/인젝션)  
> **컨테이너**: `dah-attack-cmd-inject`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 8.5/10 | 커맨드 인젝션은 가장 직접적인 공격. arXiv:2501.18874 UAV C2 분석 |
| 위험도 | 7.5/10 | LAND/RTL 주입으로 즉각적 임무 중단 |
| 신뢰성 | 8.0/10 | 인증 없는 /api/commands/request 엔드포인트에서 즉시 성공 |
| 탐지 난이도 | 4.0/10 | ATTACKER: requested_by 필드가 IDS에 즉시 탐지됨 |

---

### 17위 · 시나리오 10: Battery Crisis Spoofing

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-battery-crisis`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 7.5/10 | IEEE AERO 2023에서 다중 UAV 배터리 스푸핑 실험 검증 |
| 위험도 | 7.0/10 | 전 자산 동시 배터리 위기 경보 → Diversion 효과 |
| 신뢰성 | 8.5/10 | battery_wh 무검증 코드에서 직접 확인 |
| 탐지 난이도 | 5.5/10 | rate-of-change 이상으로 탐지 가능. 동시 다발성이 통계적 이상 |

---

### 18위 · 시나리오 13: Mission Queue 고갈

> **PDF 유사**: 없음 (독창)  
> **컨테이너**: `dah-attack-mission-queue-exhaust`

| 항목 | 점수 | 근거 |
|------|------|------|
| 현실성 | 6.5/10 | 큐 고갈은 고전적 DoS 변형. NDSS 2024 기반 |
| 위험도 | 6.5/10 | 승인자 마비 + 응답 지연. 직접 임무 실패 아님 |
| 신뢰성 | 9.0/10 | 크기 제한 없는 dict 코드 직접 확인. 구현 실패 요소 없음 |
| 탐지 난이도 | 5.0/10 | 큐 크기 급증으로 탐지 용이 |

---

## PDF 유사 시나리오 매핑

| DAH PDF 시나리오 번호 | PDF 내용 (추정) | 본 시뮬레이션 대응 |
|---------------------|----------------|-----------------|
| #1 | C2 링크 저하/차단 | ✅ 시나리오 2: 링크 저하 Fail-safe 유도 |
| #2 / #7 | GPS/GNSS 위치 조작 | ✅ 시나리오 1: GNSS Drift 누적 공격 |
| #3 / #9 | 커맨드 위조/인젝션 | ✅ 시나리오 5: Command Injection |
| #4 / #16 | 협동 임무 방해 | ✅ 시나리오 4: 협동 임무 동기화 교란 |
| #10 | GPS 스푸핑 (단순 좌표 위조) | ✅ 시나리오 3: 동역학 일치 GPS 스푸핑 (고도화 버전) |
| 없음 | — | 시나리오 6-18: PDF에 없는 독창 고급 시나리오 |

---

## 구현 현황 요약

| 구분 | 컨테이너 수 | 시나리오 |
|------|-----------|---------|
| PDF 유사 (구현) | 5개 | #1, 2, 3, 4, 5 |
| 독창 어드벤스드 (구현) | 13개 | #6~18 |
| **합계** | **18개** | **전체 완료** |

```bash
# 전체 18개 공격 컨테이너 일괄 실행
docker compose --profile cyber-attack up -d

# 개별 실행
docker compose --profile cyber-attack up dah-attack-multi-vector-blitz
docker compose --profile cyber-attack up dah-attack-fdi-fusion
docker compose --profile cyber-attack up dah-attack-mimicry
docker compose --profile cyber-attack up dah-attack-alert-fatigue
docker compose --profile cyber-attack up dah-attack-recon
docker compose --profile cyber-attack up dah-attack-gnss-drift
docker compose --profile cyber-attack up dah-attack-dynamic-spoof
docker compose --profile cyber-attack up dah-attack-audit-flood
docker compose --profile cyber-attack up dah-attack-sybil-fleet
docker compose --profile cyber-attack up dah-attack-geofence-inject
docker compose --profile cyber-attack up dah-attack-edge-work-snooping
docker compose --profile cyber-attack up dah-attack-timestamp-rollback
docker compose --profile cyber-attack up dah-attack-link-degrade
docker compose --profile cyber-attack up dah-attack-sync-disrupt
docker compose --profile cyber-attack up dah-attack-priority-escalation
docker compose --profile cyber-attack up dah-attack-cmd-inject
docker compose --profile cyber-attack up dah-attack-battery-crisis
docker compose --profile cyber-attack up dah-attack-mission-queue-exhaust
```

---

## Blue Team 방어 우선순위 (공격 순위 기반)

| 우선순위 | 대응 대상 공격 | 권고 조치 |
|---------|-------------|---------|
| P1 (즉시) | Mimicry (#16), Silent Recon (#11) | ML 이상 탐지 도입, API 전체 인증 |
| P1 (즉시) | Track Fusion FDI (#7) | source_registry 서명 (HMAC-SHA256) |
| P2 (단기) | Alert Fatigue (#8) | Rate-of-Alert 이상 탐지, 경보 우선순위 동적 조정 |
| P2 (단기) | Audit Hash Chain (#14) | 로테이션 시 cross-reference 해시 유지 |
| P3 (중기) | Edge Work Snooping (#12) | 엣지 인증 (mTLS), /api/edge/work 접근 제한 |
| P3 (중기) | Priority Escalation (#15) | priority 범위 검증 (1-5 외 거부) |
| P4 (장기) | Mission Queue 고갈 (#13) | 큐 최대 크기 제한, 중복 요청 거부 |
| P4 (장기) | Battery Crisis (#10) | rate-of-change 검증 (틱당 최대 변화율 임계) |

---

*작성: 2026-06-29 | DAH 2026 UAS/UGV 사이버 방어 시뮬레이션*  
*전체 18개 시나리오 구현 완료 — 모두 `profiles: ["cyber-attack"]` 컨테이너로 격리*
