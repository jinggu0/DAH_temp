# Defensive Vulnerability Notes for DAH UAS/UGV Simulation

This document is for local defensive simulation, briefing, and AI-agent training. It does not describe real exploitation steps, real radio procedures, real Korean defense network integration, or real actuator control. Tactical Router, TMMR, TICN-like Network, and Upper C2/BMS are emulator roles only.

## Scope

Real/local-capable surfaces in this repository:

- REST JSON UAS/UTM API for scenario, telemetry, command approval, mission upload approval, edge registration, audit logs, and protocol logs.
- MAVLink-compatible local UDP parsing for telemetry and dry-run command/mission gateway workflows.
- Dashboard protocol execution buttons and Docker role status views.
- JSONL audit/runtime/protocol logs for repeatable analysis.

Emulator-only surfaces:

- Tactical Router/TIPS role.
- TMMR role.
- TICN-like Network role.
- Upper C2/BMS role.
- Fault injection and tactical degradation events.

## Defensive Cases

| Case | Local Fault Profile | Defensive Question | Primary Evidence | Expected Response |
| --- | --- | --- | --- | --- |
| MAVLink telemetry trust gap | `mavlink_plaintext_warning` | Can the monitor flag unauthenticated or mock plaintext telemetry paths? | `/api/protocol-monitor`, protocol log, telemetry ingest events, C2 link status | Mark link degraded, preserve telemetry evidence, require authenticated/signed/encrypted transport in a future real profile. |
| Mission sequence guard | `mission_count_reset_attempt` | Can the GCS hold mission upload approval when sequence continuity is suspicious? | mission upload request/approve log, audit chain, alert, edge work ACK | Hold upload, compare mission sequence counters, require operator confirmation, keep command dispatch dry-run. |
| C2 delay | `c2_link_delay` | Can operators see delayed command/telemetry path impact before dispatching work? | chain metrics, service status, command queue timestamps | Degrade C2 state, prefer edge safety policy, avoid non-essential work dispatch. |
| C2 packet loss | `c2_link_packet_loss` | Can the dashboard separate a critical link condition from normal telemetry drift? | C2 link packet loss metric, alerts, tactical message log | Stop non-essential work dispatch and switch to degraded-link playbook. |
| TMMR queue pressure | `tmmr_queue_overflow` | Can the local tactical role emulator expose queue pressure and dropped-message metrics? | TMMR queue depth, dropped messages, priority starvation flag | Throttle low-priority tactical messages and preserve queue metrics for after-action review. |
| TICN-like route metric drift | `ticn_route_metric_change` | Can route metric changes be tracked as controlled emulator events? | TICN-like route metric, route change count, chain status | Freeze route baseline and compare route metric deltas against allowlisted changes. |
| Upper C2 command mismatch | `upper_c2_command_mismatch` | Can the approval chain require dual review before any command leaves the queue? | Upper C2 mismatch count, command queue, audit log | Require dual approval and keep execution dry-run until the mismatch is resolved. |

## Log Interpretation

Use these fields as stable AI-agent features:

- `timestamp_utc`: order events and calculate dwell time.
- `message_type` / `event_type`: classify telemetry, command, mission, fault, alert, and ACK events.
- `trace_id` / `message_id`: correlate request and response envelopes.
- `asset_id` / `edge_id`: bind events to UAV or UGV edge devices.
- `status`: distinguish `pending_approval`, `approved`, `rejected`, `acked`, `degraded`, and `critical` states.
- `simulation_only`: separate emulator evidence from real/local-capable telemetry and API events.
- `effects` / `metrics`: extract queue depth, packet loss, latency, route metric, and mismatch counters.

## AI Agent Framing

Attack-simulation agent input should stay limited to choosing one of the allowlisted local fault profiles and timing it during a scenario replay. It must not generate exploit payloads or external traffic.

Defense agent input should include:

- Recent protocol log window.
- Current chain snapshot.
- Service status snapshot.
- Command and mission upload queues.
- Audit integrity verification result.

Defense agent output should be a recommendation only:

- classify severity,
- identify affected component,
- cite evidence IDs,
- recommend operator action,
- keep real command execution disabled unless explicitly approved in a separate safe test environment.

## Contest Use

For DAH preparation, pair each case with one scenario from `docs/scenarios.md` and export the logs after each run. The scoreable artifact should include scenario intent, exact local command sequence, selected fault profile, alert evidence, response recommendation, and residual risk.
