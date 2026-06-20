# Korean Defense Contractor Alignment

사용자 지침에 따라 앞으로 서비스 구현은 한국 공식 방산 업체들이 공개한 체계 구조를 우선
참고합니다. 단, 공개 자료만 사용하며 실제 업체 시스템, 운용망, 세부 성능을 복제하지 않습니다.

## 기준 구조

| 구조 축 | 구현 기준 |
| --- | --- |
| Platform | UAV/UGV asset, system id, component id, endurance, mission envelope |
| Mission Payload | EO/IR, SAR, video downlink, GPS/INS 등 임무장비 요구사항 |
| C2 / Ground Control | operator, approver, C2 node, command authority |
| Datalink | MAVLink, LOS, SATCOM, tactical LTE, ship LOS profile |
| Operation Support | audit log, MRO/upgrade-friendly module boundary, Docker deployment |

## 현재 반영 상태

- KAI 공개 UAV 구조: 군단급 UAV, 차기 군단급 무인기, VTOL/UCAV 선행연구, ISR/지상통제/운용지원 축
- 서비스 구현: UAS/UTM core, MAVLink gateway, mission/command approval queue, audit log
- 향후 업체별 공개 자료가 추가되면 scenario profile과 문서에만 반영하고 실제 명칭/성능은 가상값으로 유지

## 사용한 공식 자료

- KAI UAV business page: https://www.koreaaero.com/EN/Business/UAV.aspx
