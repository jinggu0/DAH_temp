# Source Learning Notes

작업공간 `source/`의 PDF를 빠르게 스캔해 UAV/UGV 테스트 환경에 반영할 포인트를 정리했습니다.
보고서에 인용할 때는 원문 PDF의 제목, 저자, 발행처, 연도를 참고문헌에 별도로 기재합니다.

## 자료별 활용 포인트

| 자료 | 하네스 반영 포인트 | 보고서 활용 위치 |
| --- | --- | --- |
| `Unmanned Aircraft System Traffic Management - Concept of Operations.pdf` | UAS 운용은 저고도 공역, 정적/동적 제약, BVLOS/통제 절차를 고려해야 함 | 방산 운용 환경, 정상 mission model |
| `MAVLink in a Nutshell.pdf` | MAVLink는 telemetry와 command 교환의 핵심 프로토콜이며 GPS, mission, command 메시지가 공격 표면이 될 수 있음 | UAV interface, command/telemetry threat model |
| `Empirical Analysis of MAVLink Protocol Vulnerability.pdf` | MAVLink 기반 UAV 공격 연구에서 spoofing, jamming, command/telemetry abuse가 주요 실험 축으로 제시됨 | 공격 시나리오 기술 근거 |
| `CNPC Waveform Trade Studies.pdf` | CNPC는 control and non-payload communication 링크의 신뢰성, 보안성, 운용 제약을 설계해야 함 | link jamming, fail-safe, recovery 설계 |
| `DAH 예선_안내서.pdf` | 예선 평가는 공격 시나리오, 방어 전략, AI 에이전트 아키텍처가 핵심 | 전체 보고서 구성과 제출 전략 |

## 하네스에 반영한 위협 축

### 1. GPS/GNSS Spoofing

- 위치 보고값이 실제/예상 경로에서 점진적으로 이탈하는 상황을 모델링합니다.
- `gps_spoof` 공격은 `reported_position`만 변조하고, 실제 기체 위치와 계획 경로를 분리합니다.
- 방어 로직은 위치 급변(`gps_jump`)과 계획 경로 이탈(`route_deviation`)을 모두 봅니다.

### 2. Command Injection

- 정상 mission target과 다른 command target이 유입되는 상황을 모델링합니다.
- `command_injection` 공격은 UGV의 실제 이동 목표를 바꾸도록 설계했습니다.
- 방어 로직은 nominal target 대비 command target 거리를 검증하고 `reject_command` 또는
  `quarantine_asset_channel`로 대응합니다.

### 3. Telemetry/Control Link Jamming

- telemetry/control link가 확률적으로 끊기는 상황을 모델링합니다.
- `link_jam` 공격은 deterministic seed를 사용해 재현 가능한 link loss 패턴을 만듭니다.
- 방어 로직은 연속 link loss 시간을 기준으로 fail-safe 대응을 생성합니다.

## 현재 테스트 시나리오와 자료 근거 연결

| Scenario field | 자료 근거 | 설명 |
| --- | --- | --- |
| `uav-01` | UAS/UTM, MAVLink | 공중 asset의 mission route, GPS/telemetry 공격 표면 |
| `ugv-01` | UGV convoy assumption, command validation | 지상 asset의 command injection과 경로 이탈 |
| `gps_spoof` | MAVLink vulnerability papers | 위치 신뢰 경계 공격 |
| `command_injection` | MAVLink command/mission attack surface | 임무 명령 변조 |
| `link_jam` | CNPC communication link | 제어/비임무 통신 링크 교란 |

## AI 에이전트 설계에 반영할 제약

- LLM은 직접 제어 명령을 실행하지 않고 planner/recommender 역할로 제한합니다.
- 실제 명령 차단, fail-safe, quarantine은 deterministic executor가 수행합니다.
- 모든 action은 telemetry frame, active attack id, threshold와 함께 로그로 남깁니다.
- 보고서에는 "AI가 의사결정 보조와 시나리오 생성에 기여하고, 안전 제어는 검증 가능한 코드가 수행한다"는 구조로 설명합니다.

## 본선 확장 시 추가 학습 항목

1. 본선 UAV/UGV simulator API와 message schema
2. PX4/ArduPilot SITL의 MAVLink message replay 방식
3. ROS2 DDS security, topic remapping, `/tf`/`/odom` 변조 방어
4. 실제 GPS/INS/odometry sensor fusion anomaly score
5. multi-agent 협업에서 asset isolation이 mission success에 주는 영향
