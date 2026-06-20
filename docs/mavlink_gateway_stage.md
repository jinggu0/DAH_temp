# MAVLink Gateway Stage

이 단계는 실제 UAS 시스템으로 가기 위한 telemetry gateway 경계입니다. 목표는 autopilot 또는
시뮬레이터가 송신하는 MAVLink UDP stream을 UAS/UTM 서비스의 live ingest API로 연결하는 것입니다.

## 구현 범위

- UDP listener: `src/uas_utm_gateway/udp_gateway.py`
- MAVLink v1/v2 frame parser: `src/uas_utm_gateway/mavlink_parser.py`
- scenario 기반 `system_id -> asset_id` 변환: `src/uas_utm_gateway/translator.py`
- ingest client: `src/uas_utm_gateway/ingest_client.py`
- CLI entrypoint: `uas-utm-gateway`

## 지원 메시지

현재 gateway는 관제에 필요한 최소 MAVLink 메시지를 파싱합니다.

| MAVLink message | 사용 목적 |
| --- | --- |
| `HEARTBEAT` | asset 상태 추적 |
| `SYS_STATUS` | battery/link 상태 보강 |
| `GLOBAL_POSITION_INT` | 위치, 속도, heading telemetry ingest |
| `MISSION_CURRENT` | 현재 mission sequence 추적 |
| `UTM_GLOBAL_POSITION` | UTM 위치 공유 메시지 ingest 후보 |

CRC 검증과 full dialect 검증은 아직 하지 않습니다. 본선 환경에서 실제 MAVLink 연결이 확정되면
pymavlink 또는 생성된 dialect library를 붙여 검증 계층을 강화합니다.

## 실행

서비스를 먼저 실행합니다.

```powershell
.\scripts\run_uas_utm_service.ps1
```

다른 터미널에서 gateway를 실행합니다.

```powershell
$env:PYTHONPATH = "src"
python -m uas_utm_gateway.udp_gateway `
  --listen-host 0.0.0.0 `
  --listen-port 14550 `
  --scenario scenarios/korea_defense_uas_utm_ops.json `
  --ingest-url http://127.0.0.1:8080/api/telemetry/ingest
```

## 입력 형식

1. MAVLink v1/v2 binary datagram
2. 테스트용 JSON datagram

JSON datagram 예:

```json
{
  "payload": {
    "asset_id": "external-uas-01",
    "time_s": 12,
    "position": [10, 20, 90],
    "status": "external-live"
  }
}
```

## 다음 확장

1. CRC extra 기반 MAVLink checksum 검증
2. MAVLink 2 signing 검증 상태 기록
3. pymavlink optional dependency 추가
4. TCP endpoint와 serial endpoint 추가
5. gateway를 Docker Compose 별도 service로 분리
