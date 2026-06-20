# Korea Defense UAS/UTM Upgrade Notes

이 문서는 공개 자료를 바탕으로 UAS/UTM 가상환경을 한 단계 높인 근거와 구현 범위를 정리합니다.
현재 단계는 정상 운용 baseline이며, 취약점 분석이나 공격/방어 절차는 포함하지 않습니다.

## 조사 요약

| 공개 운용 맥락 | 가상환경 반영 |
| --- | --- |
| 한국군은 정찰/감시 목적의 군단급 UAV, 중고도/고고도 ISR, 소형 드론 운용 개념을 보유한 것으로 공개 자료에서 확인됨 | `corps_recon_uav`, `male_isr`, `small_uas`, `shipborne_vtol_uas` platform class 추가 |
| 군 운용은 지상 통제소, 항공작전 통제, 해상 통제 등 복수 C2 노드가 필요함 | `C2Node`와 link coverage 모델 추가 |
| ISR 임무는 EO/IR, SAR, 영상 하향링크, GPS/INS 등 payload 제약을 동반함 | mission별 `required_payloads`와 asset별 `sensor_payloads` 검증 추가 |
| 장거리/중고도 UAV는 LOS뿐 아니라 SATCOM 계열 링크가 필요함 | `los_c_band`, `satcom_ka`, `lte_tactical`, `ship_los` link profile 추가 |
| 정상 UTM은 공역 구역, 고도 제한, corridor 충돌 회피, C2 연결 가능성을 같이 판단해야 함 | UTM 승인 서비스에 payload/link/C2 coverage/trajectory conflict 검증 추가 |

## MAVLink 반영 범위

MAVLink 공식 common message set과 mission protocol을 기준으로 정상 운용 메시지만 모델링했습니다.

| MAVLink 메시지 | 가상환경 역할 |
| --- | --- |
| `HEARTBEAT` | asset 생존/상태 heartbeat |
| `GLOBAL_POSITION_INT` | 위치, 고도, 속도, heading telemetry |
| `SYS_STATUS` | 배터리 잔량과 통신 상태 요약 |
| `MISSION_CURRENT` | 현재 수행 중인 mission 식별 |
| `MISSION_ITEM_INT` | 승인된 waypoint mission plan 표현 |
| `UTM_GLOBAL_POSITION` | UTM 서비스에 제공되는 UAS 식별자, 위치, 속도, 다음 waypoint |

구현 파일:

- `src/uas_utm/mavlink_adapter.py`
- `src/uas_utm/models.py`
- `src/uas_utm/simulator.py`

## 업그레이드된 정상 시나리오

시나리오 파일:

- `scenarios/korea_defense_uas_utm_ops.json`

포함 asset:

- `rq101-corps-recon-01`: 군단급 정찰 UAV 가정
- `muav-male-isr-01`: 중고도 장기체공 ISR UAV 가정
- `small-dronebot-01`: 소형 드론봇/전술 정찰 UAS 가정
- `maritime-vtol-01`: 해상/연안 VTOL UAS 가정

포함 C2 node:

- `ground-control-east`: 지상 통제소
- `air-ops-satcom`: 항공작전 SATCOM gateway
- `naval-control-coast`: 해상 통제소

정상 검증 항목:

- payload 요구사항 만족 여부
- required link 지원 여부
- C2 coverage 여부
- no-fly zone/고도 제한 침범 여부
- mission corridor 충돌 여부
- MAVLink telemetry message 생성 수
- link coverage rate와 C2 utilization

## 대회 확장 방향

1. 본선 simulator API가 공개되면 `TelemetryFrame` 생성부를 실제 simulator adapter로 교체합니다.
2. MAVLink가 직접 제공되면 `mavlink_adapter.py`를 mock generator에서 parser/replayer로 확장합니다.
3. 보고서에는 본 문서와 `output/korea_defense_uas_summary.json`을 정상 운용 baseline 증거로 사용합니다.
4. 이후 취약점 분석 단계에서는 같은 시나리오에 대해서만 비정상 입력을 추가해 baseline 대비 차이를 측정합니다.
5. UGV가 본선 범위에 포함되면 C2 node와 mission schema는 유지하고, platform class와 route validator만 지상 경로로 확장합니다.

## 사용한 공개 자료

- MAVLink common message set: https://mavlink.io/en/messages/common.html
- MAVLink mission protocol: https://mavlink.io/en/services/mission.html
- MAVLink message signing guide: https://mavlink.io/en/guide/message_signing.html
- PX4 MAVLink messaging: https://docs.px4.io/main/en/mavlink/
- RQ-101, KUS-FS/MUAV, RQ-4 Global Hawk 등 공개 UAS 운용 정보는 공개 웹 자료를 참고하되, 수치와 운용 세부는 시뮬레이션용 가정으로 단순화했습니다.
