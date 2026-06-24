# Bidirectional MAVLink Gateway Stage

## 목적

외부 UAV/UGV 디바이스가 Docker로 실행 중인 UAS/UTM 서버와 MAVLink UDP로 양방향 통신할 수 있게 한다.
기존 `uas-utm-gateway`는 `14550/udp`에서 telemetry를 수신해 `/api/telemetry/ingest`로 전달하는 단방향 gateway였다.
이번 단계의 `uas-utm-bidir-gateway`는 `14551/udp`에서 telemetry를 수신하고, 같은 endpoint로 승인된 command/mission을 다시 송신한다.

## 통신 흐름

```text
External UAV/UGV/PX4/ArduPilot/SITL
        |  MAVLink telemetry, COMMAND_ACK
        v
uas-utm-bidir-gateway :14551/udp
        |  /api/telemetry/ingest
        |  /api/gateway/commands
        |  /api/gateway/mission-uploads
        |  /api/edge/work/ack
        v
uas-utm-service :8080
        |  Track fusion, approval queue, audit
        v
UTM UI/API
```

## 지원 메시지

수신:

- `HEARTBEAT`
- `SYS_STATUS`
- `GLOBAL_POSITION_INT`
- `MISSION_CURRENT`
- `UTM_GLOBAL_POSITION`
- `COMMAND_ACK`

송신:

- `COMMAND_LONG`
- `MISSION_ITEM_INT`

현재 builder는 MAVLink v2 header, common.xml CRC extra 기반 X.25 checksum, 선택적 MAVLink2 signing trailer를 생성한다. `--signing-key-hex`를 지정하지 않으면 unsigned MAVLink2 frame을 송신한다.

## 실행

Docker Compose:

```bash
docker compose up --build uas-utm-service uas-utm-bidir-gateway
```

외부 디바이스 또는 SITL은 Kali/Docker host IP의 UDP 14551로 MAVLink를 보낸다.

```text
udp://<kali-ip>:14551
```

PowerShell 개발 실행:

```powershell
.\scripts\run_uas_utm_service.ps1
.\scripts\run_uas_utm_bidir_gateway.ps1
```

## 외부 디바이스 연결 예시

MAVProxy:

```bash
mavproxy.py --master=/dev/ttyACM0,57600 --out=udp:<kali-ip>:14551
```

mavlink-router:

```bash
mavlink-routerd -e <kali-ip>:14551 /dev/ttyACM0:57600
```

## 안전 경계

- UTM에서 승인된 command와 mission upload만 송신한다.
- gateway는 마지막으로 telemetry를 보낸 endpoint를 asset별 송신 대상으로 기억한다.
- `COMMAND_ACK`를 받으면 `/api/edge/work/ack`로 감사 로그에 남긴다.
- 실제 장비 actuation 전 local safety interlock은 외부 edge/autopilot 계층에서 검증해야 한다.