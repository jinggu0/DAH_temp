# Docker Desktop Runbook

## Purpose

Run the DAH UAV/UGV UAS cyber-security simulation as visible Docker Desktop role containers while keeping all tactical network behavior local, mocked, and simulation-only.

## Default Run

```bash
docker compose up -d --build
```

Open the dashboard through the gateway:

```text
http://localhost:9000
```

Compatibility endpoint for the existing UAS/UTM service:

```text
http://localhost:8080
```

## Dashboard Checks

The dashboard title is `DAH UAS/UGV Tactical Chain Dashboard`. Use the top role cards and the tactical chain panel to confirm that real/local-capable pieces and emulator-only pieces are visibly separated.

Useful local checks:

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/service-status
curl http://localhost:8080/api/chain
curl http://localhost:8080/api/protocol-monitor?limit=20
```

The right-side panels show alerts, defense decisions, fault injection events, and recommended responses. The bottom panels show Docker service status, command log, tactical message log, protocol log, runtime log, telemetry, and fused tracks.

## Logs

```bash
docker compose logs -f dah-gcs
docker compose logs -f dah-dashboard
docker compose logs -f dah-tactical-router
docker compose logs -f dah-defense-agent
```

## Stop

```bash
docker compose down
```

## Cyber Lab Profile

The cyber-lab profile is simulation-only. It is intended for local fault injection demos, not real attack traffic.

```bash
docker compose --profile cyber-lab up -d --build
```

## Sample Edge Profile

The sample-edge profile preserves the previous sample Dronebot edge behavior separately from the default dashboard demo.

```bash
docker compose --profile sample-edge up -d --build
```

## Default Containers

- `dah-gateway`: single browser entrypoint at `localhost:9000`.
- `dah-dashboard`: dashboard proxy to the GCS dashboard.
- `dah-gcs`: current UAS/UTM service, exposed at `localhost:8080`.
- `dah-uav-sim`: UAV mock telemetry edge agent.
- `dah-ugv-sim`: UGV mock telemetry edge agent.
- `dah-mavlink-gateway`: MAVLink UDP ingest gateway on `14550/udp`.
- `dah-bidir-mavlink-gateway`: bidirectional MAVLink gateway on `14551/udp`.
- `dah-tactical-router`: local tactical router role status service.
- `dah-tmmr-emulator`: local TMMR emulator role status service.
- `dah-ticn-emulator`: local TICN-like network role status service.
- `dah-upper-c2`: local Upper C2/BMS simulator role status service.
- `dah-telemetry-collector`: local telemetry/log collector role status service.
- `dah-defense-agent`: local defense agent role status service.

## Networks

- `dah-asset-net`: UAV/UGV/mock telemetry side.
- `dah-ops-net`: GCS, dashboard, gateway, collector, defense agent side.
- `dah-tactical-net`: tactical router, TMMR emulator, TICN-like emulator, Upper C2 side.

## Safety Boundary

Default Compose does not use privileged mode, host networking, raw sockets, or `NET_ADMIN`. Fault injection is represented as application-level emulator metrics and alerts. It does not manipulate the host OS network stack.

## Scenario Briefing Pack

Use the training pack to prepare repeatable DAH activity evidence:

```bash
PYTHONPATH=src python -m uas_utm.scenario_report --scenario scenarios/dah_training/mavlink_telemetry_monitoring.json --markdown-output output/reports/mavlink_telemetry_monitoring.md
PYTHONPATH=src python -m uas_utm.scenario_report --scenario scenarios/dah_training/mission_upload_guard.json --markdown-output output/reports/mission_upload_guard.md
PYTHONPATH=src python -m uas_utm.scenario_report --scenario scenarios/dah_training/tactical_chain_degradation.json --markdown-output output/reports/tactical_chain_degradation.md
```

Package all DAH training scenarios at once:

```bash
PYTHONPATH=src python -m uas_utm.scenario_batch --scenario-dir scenarios/dah_training --output-dir output/scenario-packages
```

Generate or refresh briefing templates from the package index:

```bash
PYTHONPATH=src python -m uas_utm.scenario_briefing --index output/scenario-packages/index.json
```

The matching briefing guide is `docs/scenarios.md`. Defensive case notes are in `docs/vulnerabilities.md`.

## Test

```bash
python -m unittest discover -s tests
```
