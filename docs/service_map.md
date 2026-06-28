# DAH Service Map

## Role Map

| Docker service | Container name | Current implementation | Network(s) | Boundary |
| --- | --- | --- | --- | --- |
| `dah-gateway` | `dah-gateway` | Local reverse proxy to dashboard | `dah-ops-net` | Local demo entrypoint |
| `dah-dashboard` | `dah-dashboard` | Local reverse proxy to `dah-gcs` dashboard | `dah-ops-net` | UI only |
| `dah-gcs` | `dah-gcs` | Existing `uas_utm_service.server` | `dah-ops-net`, `dah-asset-net`, `dah-tactical-net` | Real local UAS/UTM simulation service |
| `dah-uav-sim` | `dah-uav-sim` | Existing `uas-utm-edge` in UAV mock mode | `dah-asset-net`, `dah-ops-net` | Mock/SITL-ready telemetry only |
| `dah-ugv-sim` | `dah-ugv-sim` | Existing `uas-utm-edge` in UGV mock mode | `dah-asset-net`, `dah-ops-net` | Mock telemetry only |
| `dah-mavlink-gateway` | `dah-mavlink-gateway` | Existing `uas-utm-gateway` | `dah-asset-net`, `dah-ops-net` | Local MAVLink UDP ingest |
| `dah-bidir-mavlink-gateway` | `dah-bidir-mavlink-gateway` | Existing `uas-utm-bidir-gateway` | `dah-asset-net`, `dah-ops-net` | Local MAVLink queue bridge |
| `dah-tactical-router` | `dah-tactical-router` | Lightweight role status service | `dah-ops-net`, `dah-tactical-net` | EMULATED / NOT REAL MILITARY SYSTEM |
| `dah-tmmr-emulator` | `dah-tmmr-emulator` | Lightweight role status service | `dah-tactical-net` | EMULATED / NOT REAL MILITARY SYSTEM |
| `dah-ticn-emulator` | `dah-ticn-emulator` | Lightweight role status service | `dah-tactical-net` | EMULATED / NOT REAL MILITARY SYSTEM |
| `dah-upper-c2` | `dah-upper-c2` | Lightweight role status service | `dah-tactical-net` | EMULATED / NOT REAL MILITARY SYSTEM |
| `dah-telemetry-collector` | `dah-telemetry-collector` | Lightweight role status service; logs remain JSONL in `logs/` | `dah-ops-net` | Local log collection role |
| `dah-defense-agent` | `dah-defense-agent` | Lightweight role status service; detection logic remains in harness/service | `dah-ops-net` | Local rule-based defense role |
| `dah-fault-injector` | `dah-fault-injector` | Profile-gated role status service | `dah-ops-net` | cyber-lab simulation only |

## Existing API Compatibility

`dah-gcs` preserves the existing UAS/UTM HTTP API on `localhost:8080`, including:

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/chain`
- `GET /api/alerts`
- `GET /api/tactical-emulator`
- `GET /api/protocol-monitor`
- `POST /api/telemetry/ingest`
- `POST /api/faults/inject`

## Dashboard Confirmation Items

In Docker Desktop, confirm that the default stack shows these role containers:

1. `dah-gateway`
2. `dah-dashboard`
3. `dah-gcs`
4. `dah-uav-sim`
5. `dah-ugv-sim`
6. `dah-mavlink-gateway`
7. `dah-bidir-mavlink-gateway`
8. `dah-tactical-router`
9. `dah-tmmr-emulator`
10. `dah-ticn-emulator`
11. `dah-upper-c2`
12. `dah-telemetry-collector`
13. `dah-defense-agent`

## Future Phase Boundary

Phase 1-2 creates role visibility and documentation. Full service extraction, shared event bus, and per-service business APIs belong to later phases.
## Phase 3 Service Boundary

Phase 3 adds code-level service boundaries without breaking the existing monolithic UAS/UTM API.

Common runtime modules:

- `src/dah_runtime/service_contracts.py`: shared dataclass payloads for `ServiceStatus`, `TelemetryEvent`, `CommandEvent`, `TacticalMessage`, `FaultEvent`, and `AlertEvent`.
- `src/dah_runtime/health.py`: helpers for `/health` and `/status` payloads.
- `src/dah_runtime/jsonl_store.py`: small append-only JSONL store for future service-local logs.
- `src/dah_runtime/event_bus.py`: in-memory or JSONL-backed event bus for later service extraction.

Service wrapper modules:

- `src/dah_services/gcs_service.py`
- `src/dah_services/uav_sim_service.py`
- `src/dah_services/ugv_sim_service.py`
- `src/dah_services/dashboard_service.py`
- `src/dah_services/tactical_router_service.py`
- `src/dah_services/tmmr_emulator_service.py`
- `src/dah_services/ticn_emulator_service.py`
- `src/dah_services/upper_c2_service.py`
- `src/dah_services/telemetry_collector_service.py`
- `src/dah_services/defense_agent_service.py`
- `src/dah_services/fault_injector_service.py`

The wrappers are deliberately thin. They preserve the current working UAS/UTM service and edge agents while making each Docker role have an explicit code entrypoint.