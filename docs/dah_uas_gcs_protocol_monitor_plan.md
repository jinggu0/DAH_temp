# DAH UAS/UGV GCS Protocol Monitor Implementation Plan

## Safety and Scope Boundary

- Do not connect to real Korean military TICN, TMMR, C2, BMS, or non-public defense systems.
- Real-implementable areas are UAS/UGV telemetry ingest, MAVLink-compatible parsing, GCS/UTM approval queues, audit logs, and defensive monitoring UI.
- TICN, TMMR, and upper C2/BMS are role-based emulators only. The dashboard and API must mark them as `SIMULATED / NOT REAL MILITARY SYSTEM`.
- Fault injection is limited to local Docker simulation and anomaly generation. It must not generate real attack traffic, wireless attacks, or actuator commands.

## Phase 0: Baseline Freeze

- Preserve the current Docker service, UAS/UTM API, MAVLink UDP gateway, edge registration, heartbeat, work queue, and JSONL audit log.
- Hide default temporary test edges and sample missions from the operational map.
- Show only telemetry from edge devices registered through the protocol workflow.
- Competition extension: use this phase as the normal baseline for blue-team monitoring and AI agent normal-profile training.

## Phase 1: GCS Protocol Monitor Dashboard

- Rename the dashboard to `DAH UAS/UGV GCS Protocol Monitor`.
- Add status cards for UAV, UGV, C2 Data Link, TMMR Emulator, TICN-like Network, and Defense Agent.
- Add a central chain view: `UAV/UGV -> C2 Data Link -> GCS -> Virtual Tactical Router/TIPS -> TMMR Emulator -> TICN-like Network -> Upper C2/BMS`.
- Add an Alert / Detection / Response panel.
- Add a safe local fault injection control backed by an allowlist.
- Competition extension: use this screen as the GCS briefing view, blue-team situation board, and AI agent observation surface.

## Phase 2: Protocol Monitoring Models

- Split reusable models for `VehicleTelemetry`, `CommandEvent`, `TacticalMessage`, `LinkState`, and `AlertEvent`.
- Keep MAVLink mock mode as the default.
- If `pymavlink` is available, support optional UDP receive for HEARTBEAT, SYS_STATUS, GLOBAL_POSITION_INT, COMMAND_ACK, and mission messages.
- Keep command transmission disabled or dry-run only.
- Competition extension: attach PX4/ArduPilot SITL or ROS2/Gazebo UGV adapters through the same interface.

## Phase 3: Tactical Emulator and Safe Fault Injection

- Implement Virtual Tactical Router, TMMR Emulator, TICN-like Network, and Upper C2/BMS Simulator roles.
- Allow only these simulated fault types: `mavlink_plaintext_warning`, `mission_count_reset_attempt`, `c2_link_delay`, `c2_link_packet_loss`, `tmmr_queue_overflow`, `ticn_route_metric_change`, `upper_c2_command_mismatch`.
- Each fault creates an alert and chain degradation only. No real exploit, payload, or external traffic is produced.
- Competition extension: use these events for attack/defense AI planning, detection, response, and reporting workflows.

## Phase 4: Vulnerability and Scenario Documentation

- Add `docs/vulnerabilities.md` with defensive vulnerability descriptions, detection signals, expected logs, and response notes.
- Add `docs/scenarios.md` and scenario JSON files for MAVLink Telemetry Monitoring, Mission Reset Attempt, and Tactical Chain Degradation.
- Competition extension: convert these into team briefing material, log-analysis reports, and response playbooks.

## Phase 5: Tests and Runbook

- Test dashboard snapshot APIs, mock telemetry, allowlisted fault-to-alert mapping, chain degradation, and mock-mode operation without real MAVLink.
- Update README with execution steps, safety boundaries, real-vs-emulator separation, and DAH report structure.
- Competition extension: use the runbook as the reproducible contest-day environment checklist.
## Implemented in Phase 2

- Added `src/dah_harness/protocol_monitor.py` with dataclass models for `VehicleTelemetry`, `CommandEvent`, `TacticalMessage`, `LinkState`, and `AlertEvent`.
- Added `MockMavlinkAdapter` as the default MAVLink monitor adapter. It reports `mock` mode when `pymavlink` is absent and `udp_receive_available` when the package is installed.
- Added `GET /api/protocol-monitor` to expose model-shaped telemetry, command, tactical message, link, alert, and adapter status data.
- Added dashboard `Protocol Monitor Models` summary so the operator can see model counts and the dry-run MAVLink safety boundary.
- Added tests in `tests/test_protocol_monitor.py` covering model serialization, mock adapter fallback, command/frame conversion, and service payload shape.

## Next Step: Phase 3 Entry Point

- Convert the current chain/fault status into explicit tactical emulator runtime components: Virtual Tactical Router, TMMR Emulator, TICN-like Network, and Upper C2/BMS Simulator.
- Move fault effects from simple status mapping into component-local state transitions and queue metrics.
- Keep all fault injection allowlisted and simulation-only.
## Implemented in Phase 3

- Added `src/dah_harness/tactical_emulator.py` with explicit runtime components for Virtual Tactical Router / TIPS, TMMR Emulator, TICN-like Network, and Upper C2/BMS Simulator.
- Fault injection now updates component-local state and metrics such as C2 latency, packet loss, TMMR queue depth, TICN route metric, and upper C2 command mismatch counters.
- Added `GET /api/tactical-emulator` for direct runtime inspection.
- `/api/chain`, `/api/alerts`, and `/api/protocol-monitor` now derive tactical state from the emulator runtime instead of loose status mapping.
- Dashboard chain nodes show component metrics so operators can see why a component is normal, degraded, or critical.
- Safety boundary remains unchanged: all tactical network behavior is local simulation only and does not connect to or emulate real classified/proprietary systems.

## Next Step: Phase 4 Entry Point

- Add defensive vulnerability documentation for MAVLink plaintext/auth gaps, mission count reset attempts, TMMR queue overflow, and TICN-like route metric manipulation.
- Add scenario documentation and JSON scenarios that produce repeatable logs for briefing and AI agent training.