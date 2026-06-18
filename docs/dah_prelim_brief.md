# DAH 2026 예선 브리프

출처: `DAH 예선_안내서.pdf` 추출 기준.

## 핵심 일정

| 단계 | 날짜 | 비고 |
| --- | --- | --- |
| 예선 시작 | 2026-06-15 | 온라인 보고서 심사 |
| 보고서 제출 마감 | 2026-07-10 23:59 KST | 최종본만 심사, 마감 후 수정 불가 |
| 본선 진출팀 발표 | 2026-07-31 | 상위 10개 팀, 변동 가능 |
| 오프라인 본선 | 2026-08-21 | AI 공방전 |

## 제출물

| 항목 | 형식 | 필수 여부 | 메모 |
| --- | --- | --- | --- |
| 예선 보고서 | PDF, 최대 50MB | 필수 | `DAH2026_예선보고서_[팀명].pdf` |
| 부가자료 | 외부 클라우드 다운로드 링크 | 필수 | 소스 코드, 실행 매뉴얼, 데모 링크 |

부가자료 권장 ZIP 구성:

```text
README.md
src/
requirements.txt 또는 Dockerfile
docs/
```

## 보고서 필수 목차

1. 표지: 팀명, 팀원 목록, 제출일
2. 목차
3. 팀 구성 및 역할 분배, 전문성
4. 방산 분야 공격 시나리오 설계
5. 공격 시나리오 대응 방어 아키텍처 수립
6. AI 에이전트 설계 및 구현
7. 결론 및 향후 계획
8. 참고문헌

권장 분량은 본문 25-40페이지입니다. 표지, 목차, 참고문헌은 본문 분량에서 제외합니다.

## 평가 배점

| 항목 | 배점 | 요구되는 증거 |
| --- | ---: | --- |
| 공격 시나리오 설계 | 30 | 현실적인 공격 표면, 방산 도메인 이해, 기술적 완성도 |
| 방어 전략 수립 | 25 | 탐지, 차단, 복구 설계와 구현 가능성 |
| AI 에이전트 아키텍처 | 25 | 역할 정의, 협력 구조, 기술 스택, 프로토타입 로그 |
| 팀 역량 소개 | 10 | 팀원 전문성, 역할 분배, 관련 경험 |
| 문서 완성도 | 10 | 구성 완결성, 가독성, 표/그림/코드 출처, 참고문헌 |

## 본 저장소의 대응 전략

예선 안내서는 본선 UAV/UGV 시뮬레이터 인터페이스가 본선 진출 후 별도 공지된다고 명시합니다.
따라서 예선 단계에서는 특정 시뮬레이터 종속 구현보다 다음 증거를 만드는 데 집중합니다.

- UAV/UGV 운용 환경에 맞춘 공격 표면 정의
- 공격별 탐지, 차단, 복구 로직의 연결성
- AI 에이전트의 역할 분해와 협력 구조
- 프로토타입 실행 로그, 테스트 결과, 튜닝 결과
- 본선 인터페이스 공개 후 교체 가능한 adapter boundary

## 보고서에 넣을 기술 근거

- UAV: GNSS/GPS spoofing, telemetry link jamming, MAVLink command abuse, sensor trust boundary
- UGV: route deviation, command injection, local navigation override, link degradation
- 공통 방어: anomaly detection, command validation, fail-safe mode, recovery workflow
- AI 역할: attacker planner, defender monitor, response recommender, evaluator
- 하네스 역할: repeatable scenario, attack injection, telemetry replay, metric scoring

## 바로 필요한 작업

1. 팀명과 팀원별 역할 확정
2. 보고서 공격 시나리오 2-3개 선정
3. 하네스 실행 결과를 스크린샷/JSON 로그로 저장
4. 스택 다이어그램 작성
5. 부가자료 ZIP과 외부 클라우드 링크 준비
