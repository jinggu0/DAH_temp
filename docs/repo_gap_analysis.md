# Repository Gap Analysis

## Scope

This document compares the current DAH_temp repository with the role-oriented structure observed in the reference repository `EncryH/unmanned-systems-uav-ugv`. The reference repository is used only for architecture and Docker operation ideas. No code is copied.

## Summary

The current repository already has a working UAS/UTM service, MAVLink UDP gateways, edge device registration, protocol monitoring, tactical emulator models, JSONL audit logs, and unit tests. The main gap is operational packaging: Docker Desktop users should see role-specific containers for UAV, UGV, GCS, Tactical Router, TMMR Emulator, TICN-like Network, Upper C2/BMS, Telemetry Collector, Defense Agent, Dashboard, and Gateway.

## Comparison Table

| Area | Current DAH_temp | Reference-style target | Gap / Phase 1-2 action |
| --- | --- | --- | --- |
| Directory structure | `src/dah_harness`, `src/uas_utm`, `src/uas_utm_service`, `src/uas_utm_gateway`, `src/uas_utm_edge` | Separate role folders such as UAV, UGV, GCS, dashboard, tactical router, collector, defense agent | Keep current code; document role mapping in `docs/service_map.md`. |
| Docker Compose services | Existing service/gateway/edge names centered on `uas-utm-*` | Role names visible in Docker Desktop | Rename/expand Compose services with `dah-*` role names while preserving `localhost:8080`. |
| Dashboard entrypoint | Served by current UAS/UTM service on `8080` | Single gateway/dashboard entrypoint | Add `dah-gateway` at `localhost:9000`, proxying to dashboard/GCS. |
| UAV/UGV split | Edge agent can register assets and emit telemetry | Separate UAV and UGV simulator services | Add `dah-uav-sim` and `dah-ugv-sim` services using existing edge agent in mock mode. |
| GCS role split | `uas_utm_service` provides telemetry ingest, command queue, mission upload, audit APIs | Dedicated GCS/Ground Gateway | Map current service to `dah-gcs`; preserve `8080`. |
| Tactical Router/TMMR/TICN | `TacticalEmulatorRuntime` exists inside service state | Separate visible tactical containers | Add lightweight role containers for router/TMMR/TICN/Upper C2 status in Compose; keep real logic inside current emulator for now. |
| Telemetry Collector / LogDB | JSONL audit log and runtime/protocol log APIs exist | Collector/LogDB container | Add `dah-telemetry-collector` role container; current log storage remains JSONL under `logs/`. |
| Attack/Defense Agent split | Rule-based defense and fault injection paths exist in harness/service | Separate agents | Add `dah-defense-agent` role container. Cyber-lab fault injector is profile-gated. |
| README readability | Existing README is partially garbled and harness-focused | Docker Desktop oriented quickstart | Add an ASCII Docker Desktop section with service names, ports, boundaries, and commands. |
| Docker Desktop container names | Existing names are Compose defaults or `uas-utm-*` | Clear names such as `dah-gcs`, `dah-dashboard` | Add explicit `container_name` values. |

## Real vs Emulator Boundary

Real-implementable in this repository:

- UAS/UGV telemetry ingest over REST JSON.
- MAVLink-compatible UDP telemetry parsing through local gateway code.
- GCS/UTM command queue and mission upload approval queue.
- Audit, runtime, protocol, and tactical emulator logs.

Emulator/simulation-only:

- TMMR Emulator.
- TICN-like Network.
- Upper C2/BMS Simulator.
- Tactical Router/TIPS role.
- Fault injection and anomaly injection.

Not implemented and intentionally out of scope:

- Real TICN/TMMR protocol implementation.
- Real Korean military C2/BMS integration.
- Real wireless attacks, raw socket attacks, privileged network manipulation, or actuator commands.

## Phase 1-2 Decision

For Phase 1-2, keep the current Python codebase and tests intact. Improve documentation and Docker Compose role visibility first. Defer deeper service boundary extraction to a later phase.