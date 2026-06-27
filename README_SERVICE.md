# UAS/UTM Service Quick Start

## PowerShell

```powershell
.\scripts\run_uas_utm_service.ps1
```

Open:

- http://127.0.0.1:8080
- http://127.0.0.1:8080/api/summary
- http://127.0.0.1:8080/api/protocol

## Docker

Docker Desktop must be running.

```bash
docker build -t dah-uas-utm-service .
docker run --rm -p 8080:8080 dah-uas-utm-service
```

## Docker Compose

```bash
docker compose up --build
```

## Edge Device Agent

Run a simulated external UAV/UGV edge device against the service:

```powershell
.\scripts\run_uas_utm_edge.ps1 -Once -EmitSampleTelemetry
```

The agent registers with `/api/edge/devices/register`, sends heartbeat, can ingest edge telemetry, and polls `/api/edge/work` for approved command/mission queues. It does not actuate real hardware.

## Bidirectional MAVLink

Run the bidirectional MAVLink gateway when an external UAV/UGV should both send telemetry and receive approved commands or mission uploads over UDP:

```bash
docker compose up --build uas-utm-service uas-utm-bidir-gateway
```

External devices should send MAVLink UDP to `udp://<host-ip>:14551`. The legacy `uas-utm-gateway` on `14550/udp` remains telemetry-ingest only.
## Audit Log Storage

The service stores append-only JSONL audit logs under `logs/uas_utm` by default.

```bash
curl http://127.0.0.1:8080/api/logs/status
curl http://127.0.0.1:8080/api/logs/verify
curl "http://127.0.0.1:8080/api/logs?limit=50"
```

See `docs/log_storage_system.md` for the field schema, hash-chain verification model, redaction policy, and DAH evidence workflow.
Agent-oriented audit view:

```bash
curl "http://127.0.0.1:8080/api/logs/agent-view?limit=50"
```
## Briefing Materials

- `docs/server_operation_briefing.md`: presentation-oriented overview
- `docs/server_operation_detailed_briefing.md`: detailed operation, protocol, external communication, and log analysis guide