# DAH Training Scenarios

These scenarios are local, repeatable UAS/UGV simulation packages for briefing, protocol-log review, and AI-agent dataset preparation. They do not connect to real Korean defense services, real tactical radios, real TICN/TMMR systems, or real vehicle actuators.

Scenario files live under `scenarios/dah_training/`.

## Common Run Pattern

Validate a scenario:

```bash
PYTHONPATH=src python -m uas_utm.scenario_report --scenario scenarios/dah_training/mavlink_telemetry_monitoring.json --markdown-output output/reports/mavlink_telemetry_monitoring.md
```

Package scenario evidence:

```bash
PYTHONPATH=src python -m uas_utm.scenario_package --scenario scenarios/dah_training/mavlink_telemetry_monitoring.json --output-dir output/scenario-packages
```

Package all DAH training scenarios at once:

```bash
PYTHONPATH=src python -m uas_utm.scenario_batch --scenario-dir scenarios/dah_training --output-dir output/scenario-packages
```

Generate or refresh briefing templates from the package index:

```bash
PYTHONPATH=src python -m uas_utm.scenario_briefing --index output/scenario-packages/index.json
```

Run the dashboard stack:

```bash
docker compose up -d --build
```

Open:

```text
http://localhost:9000
```

Useful APIs:

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/service-status
curl http://localhost:8080/api/chain
curl http://localhost:8080/api/protocol-monitor?limit=20
curl http://localhost:8080/api/logs/verify
```

## Scenario 1: MAVLink Telemetry Monitoring

File: `scenarios/dah_training/mavlink_telemetry_monitoring.json`

Goal:

- Build a normal telemetry baseline for one UAV and one UGV.
- Exercise edge registration, heartbeat, telemetry ingest, and protocol monitoring.
- Use `mavlink_plaintext_warning` as a local defensive marker for unauthenticated/mock plaintext telemetry paths.

Recommended local flow:

1. Start the Docker stack.
2. Use the dashboard protocol buttons or REST calls to register the UGV edge and emit telemetry.
3. Open Protocol Log, Docker Service Status, Telemetry Snapshot, and Tactical Protocol Chain.
4. Inject `mavlink_plaintext_warning` from the Safe Fault Injection control.
5. Export or copy `/api/protocol-monitor?limit=80`, `/api/chain`, `/api/service-status`, and `/api/logs/verify` outputs.

Expected evidence:

- telemetry ingest events linked to `telemetry-uav-01` and `telemetry-ugv-01` during offline report generation,
- C2 Data Link state transitions to `degraded` after the local fault,
- alert category `simulated_tactical_fault`,
- recommendation to preserve evidence and move to authenticated transport in a future real profile.

AI-agent labels:

- baseline class: `normal_telemetry`,
- event class: `telemetry_trust_gap`,
- affected component: `c2_link`,
- response class: `preserve_and_require_authenticated_transport`.

## Scenario 2: Mission Upload Guard

File: `scenarios/dah_training/mission_upload_guard.json`

Goal:

- Practice mission upload request, approval, gateway polling, and edge ACK review.
- Exercise the GCS approval queue without sending a real actuator command.
- Use `mission_count_reset_attempt` as a local defensive marker for mission sequence review.

Recommended local flow:

1. Start the Docker stack.
2. Request mission upload for `mission-upload-local-recon`.
3. Approve the pending upload only after checking the dashboard queue.
4. Poll edge work and ACK the received mission work item.
5. Inject `mission_count_reset_attempt`.
6. Review Mission Upload Approval, Command Log, Audit Timeline, Recommended Responses, and Protocol Log.

Expected evidence:

- `utm.mission_upload.request`,
- `utm.mission_upload.approve`,
- gateway mission upload queue status,
- edge work ACK,
- GCS chain node marked `degraded` with `mission_sequence_guard=hold_for_operator_review`,
- audit hash verification remains valid.

AI-agent labels:

- baseline class: `mission_upload_approved`,
- event class: `mission_sequence_guard`,
- affected component: `gcs`,
- response class: `hold_upload_and_require_operator_confirmation`.

## Scenario 3: Tactical Chain Degradation

File: `scenarios/dah_training/tactical_chain_degradation.json`

Goal:

- Practice triage when local emulator metrics degrade the tactical chain.
- Use the chain panel to separate real/local-capable components from emulator-only components.
- Exercise one or more of `c2_link_delay`, `tmmr_queue_overflow`, and `ticn_route_metric_change`.

Recommended local flow:

1. Start the Docker stack.
2. Confirm all role containers are visible in Docker Desktop.
3. Open Tactical Protocol Chain and Docker Service Status.
4. Inject one allowlisted fault at a time.
5. Compare chain status, service status, tactical message log, and recommended responses.
6. Do not combine this with real network manipulation; keep the cyber-lab profile local and simulation-only.

Expected evidence:

- `tmmr_queue_overflow`: TMMR status `critical`, queue depth, dropped messages, priority starvation.
- `ticn_route_metric_change`: TICN-like status `degraded`, route metric, route change count.
- `c2_link_delay`: C2 Data Link status `degraded`, latency metric.
- dashboard recommendations stay operator-advisory and do not execute real commands.

AI-agent labels:

- baseline class: `normal_chain`,
- event class: `chain_degradation`,
- affected components: `c2_link`, `tmmr`, `ticn`,
- response class: `degraded_link_or_queue_playbook`.

## Reporting Template

For each scenario run, capture:

- scenario file and git commit,
- Docker container list,
- selected fault profile,
- initial `/api/service-status`,
- post-fault `/api/chain`,
- protocol log extract,
- audit verification result,
- operator response summary,
- AI-agent features and labels,
- residual risk and next tuning item.
