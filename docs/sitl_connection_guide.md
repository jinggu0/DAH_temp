# PX4/ArduPilot SITL Connection Guide

## Goal

Use SITL as an external UAV/UGV endpoint for the DAH UAS/UTM service.
The recommended path is the bidirectional gateway on UDP `14551`.

## Run DAH Services

```bash
docker compose up --build uas-utm-service uas-utm-bidir-gateway
```

Open:

```text
http://127.0.0.1:8080
```

## Connect SITL

Find the Kali host IP:

```bash
hostname -I
```

Send MAVLink to the bidirectional gateway:

```bash
mavproxy.py --master=udp:127.0.0.1:14540 --out=udp:<kali-ip>:14551
```

For a serial autopilot or companion computer:

```bash
mavproxy.py --master=/dev/ttyACM0,57600 --out=udp:<kali-ip>:14551
```

With mavlink-router:

```bash
mavlink-routerd -e <kali-ip>:14551 /dev/ttyACM0:57600
```

## Verify

```bash
curl http://127.0.0.1:8080/api/tracks
curl http://127.0.0.1:8080/api/edge/devices
curl http://127.0.0.1:8080/api/baseline/export
```

## Expected Flow

1. SITL sends `HEARTBEAT` and `GLOBAL_POSITION_INT`.
2. `uas-utm-bidir-gateway` maps system id to scenario asset id.
3. UTM track fusion updates `/api/tracks`.
4. Operator requests a command.
5. Approver approves the command.
6. Gateway sends `COMMAND_LONG` to the last endpoint for that asset.
7. SITL/autopilot returns `COMMAND_ACK`.
8. UTM audit records edge acknowledgement.

## Notes

- Unsigned MAVLink2 is the default.
- Use `--signing-key-hex` only when both sides share the same MAVLink2 signing key.
- Do not put real signing keys in Git, screenshots, logs, or DAH reports.