const state = {
  scenario: null,
  summary: null,
  decisions: [],
  timeline: [],
  operationProfile: null,
  edgeDevices: null,
  commands: null,
  missionUploads: null,
  audit: null,
  logStatus: null,
  logIntegrity: null,
  protocolLogs: null,
  runtimeLogs: null,
  dashboard: null,
  chain: null,
  alerts: null,
  protocolMonitor: null,
  serviceStatus: null,
  scenarioPackages: null,
  protocolRuns: [],
  showProtocolHeartbeat: false,
  protocolLogLive: true,
  protocolLogTimer: null,
  tracks: null,
  tickIndex: 0,
  playing: false,
  live: false,
  eventSource: null,
  snapshot: null,
  edgeMotionStartedAt: null,
  edgeMotionTimer: null,
  edgeMotionBusy: false,
  intrusionAlerts: [],       // 탐지된 침입 경고 목록
};

const canvas = document.querySelector("#airspaceCanvas");
const ctx = canvas.getContext("2d");
const slider = document.querySelector("#timeSlider");
const playButton = document.querySelector("#playButton");
const liveButton = document.querySelector("#liveButton");

async function api(path, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(path, { cache: "no-store", signal: controller.signal });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") throw new Error(`타임아웃 (${timeoutMs / 1000}s): ${path}`);
    throw err;
  }
  clearTimeout(timer);
  let body = null;
  try {
    body = await response.json();
  } catch (error) {
    body = null;
  }
  if (!response.ok) throw new Error(body?.payload?.error ?? `${path}: ${response.status}`);
  return body;
}

async function postApi(path, payload, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") throw new Error(`타임아웃 (${timeoutMs / 1000}s): ${path}`);
    throw err;
  }
  clearTimeout(timer);
  let body = null;
  try {
    body = await response.json();
  } catch (error) {
    body = null;
  }
  if (!response.ok) throw new Error(body?.payload?.error ?? `${path}: ${response.status}`);
  return body;
}

async function bootstrap() {
  // /api/logs/verify 는 전체 해시체인 검증으로 느림 — bootstrap 에서 제외, 버튼 클릭 시만 호출
  const [health, protocol, scenario, summary, decisions, timeline, operationProfile, edgeDevices, commands, missionUploads, audit, logStatus, protocolLogs, runtimeLogs, dashboard, chain, alerts, protocolMonitor, serviceStatus, scenarioPackages] = await Promise.all([
    api("/api/health"),
    api("/api/protocol"),
    api("/api/scenario"),
    api("/api/summary"),
    api("/api/decisions"),
    api("/api/timeline"),
    api("/api/operation-profile"),
    api("/api/edge/devices"),
    api("/api/commands"),
    api("/api/mission-uploads"),
    api("/api/audit?limit=80"),
    api("/api/logs/status"),
    api("/api/protocol/logs?limit=80&include_heartbeat=false"),
    api("/api/runtime/logs?limit=80"),
    api("/api/dashboard"),
    api("/api/chain"),
    api("/api/alerts?limit=20"),
    api("/api/protocol-monitor?limit=20"),
    api("/api/service-status"),
    api("/api/scenario-packages"),
  ]);
  document.querySelector("#serviceStatus").textContent = health.payload.ok ? "API OK" : "API Error";
  document.querySelector("#protocolText").textContent =
    `${protocol.payload.profile} ${protocol.payload.version} / ${protocol.payload.transport.live_push}`;
  state.scenario = scenario.payload;
  state.summary = summary.payload;
  state.decisions = decisions.payload;
  state.timeline = timeline.payload.ticks;
  state.operationProfile = operationProfile.payload;
  state.edgeDevices = edgeDevices.payload;
  state.commands = commands.payload;
  state.missionUploads = missionUploads.payload;
  state.audit = audit.payload;
  state.logStatus = logStatus.payload;
  state.logIntegrity = null;
  state.protocolLogs = protocolLogs.payload;
  state.runtimeLogs = runtimeLogs.payload;
  state.dashboard = dashboard.payload;
  state.chain = chain.payload;
  state.alerts = alerts.payload;
  state.protocolMonitor = protocolMonitor.payload;
  state.serviceStatus = serviceStatus.payload;
  state.scenarioPackages = scenarioPackages.payload;
  document.title = state.dashboard?.title ?? document.title;
  slider.min = 0;
  slider.max = Math.max(0, state.timeline.length - 1);
  slider.value = 0;
  renderGcsSummary();
  renderChain();
  renderAlerts();
  renderDefenseDecisions();
  renderFaultEvents();
  renderRecommendedResponses();
  renderFaultControls();
  renderSummary();
  renderOperationProfile();
  renderEdgeDevices();
  renderEdgeLiveStatusTable();
  renderCommandPanel();
  renderMissionUploadPanel();
  renderAuditTimeline();
  renderLogStorage();
  renderProtocolRuns();
  renderProtocolLogs();
  renderRuntimeLogs();
  renderProtocolMonitorSummary();
  renderMavlinkState();
  renderDockerServiceStatus();
  renderCommandLog();
  renderTacticalMessageLog();
  renderScenarioPackages();
  await loadSnapshot(0);
  startProtocolLogLive();
  state.edgeMotionStartedAt = Date.now();
  startEdgeMotionLive();
}


function renderGcsSummary() {
  const node = document.querySelector("#dahSummaryCards");
  if (!node) return;
  const cards = state.dashboard?.cards ?? [];
  node.innerHTML = cards
    .map((card) => `
      <article class="gcs-card ${statusClass(card.status)}">
        <div class="gcs-card-label">${escapeHtml(card.label)}</div>
        <div class="gcs-card-status">${escapeHtml(card.status)}</div>
        <div class="gcs-card-detail">${escapeHtml(card.detail)}</div>
        <span class="sim-badge">${escapeHtml(card.mode)}</span>
      </article>`)
    .join("");
}

function renderChain() {
  const node = document.querySelector("#chainDiagram");
  const status = document.querySelector("#chainStatus");
  if (!node) return;
  const chain = state.chain ?? state.dashboard?.chain;
  if (!chain) {
    node.innerHTML = '<p class="protocol-text">No chain snapshot</p>';
    return;
  }
  if (status) {
    status.textContent = chain.overall_status;
    status.className = `protocol-pill ${statusClass(chain.overall_status)}`;
  }
  node.innerHTML = chain.nodes
    .map((item, index) => `
      <div class="chain-node ${statusClass(item.status)}" title="${escapeHtml(item.boundary)}">
        <strong>${escapeHtml(item.label)}</strong>
        <span>${escapeHtml(item.status)}</span>
        <small>${escapeHtml(item.boundary)}</small>
        <small class="chain-metrics">${escapeHtml(metricSummary(item.metrics))}</small>
      </div>
      ${index < chain.nodes.length - 1 ? '<div class="chain-arrow">-&gt;</div>' : ''}`)
    .join("");
}


function metricSummary(metrics) {
  const entries = Object.entries(metrics ?? {}).slice(0, 3);
  if (!entries.length) return "metrics: baseline";
  return entries.map(([key, value]) => `${key}=${value}`).join(" / ");
}
function renderAlerts() {
  const list = document.querySelector("#alertList");
  if (!list) return;
  const alerts = state.alerts?.alerts ?? state.dashboard?.alerts?.alerts ?? [];
  list.innerHTML = "";
  if (!alerts.length) {
    appendListText(list, "시뮬레이션 경보 없음");
    return;
  }
  for (const alert of alerts.slice().reverse()) {
    const item = document.createElement("li");
    item.className = alert.severity === "critical" ? "rejected" : "pending";
    item.textContent = `${alert.severity} / ${alert.title} / ${alert.target ?? "-"}`;
    item.title = alert.recommended_response ?? "";
    list.appendChild(item);
  }
}

function renderDefenseDecisions() {
  const list = document.querySelector("#defenseDecisionList");
  if (!list) return;
  list.innerHTML = "";
  const alerts = state.alerts?.alerts ?? [];
  if (!alerts.length) {
    appendListText(list, "정상 감시 중 / 대응 조치 없음");
    return;
  }
  for (const alert of alerts.slice().reverse()) {
    const item = document.createElement("li");
    item.className = alert.severity === "critical" ? "rejected" : "pending";
    item.textContent = `${alert.severity} decision / ${alert.target ?? "system"}`;
    item.title = alert.recommended_response ?? "Review simulated event";
    list.appendChild(item);
  }
}

function renderFaultEvents() {
  const list = document.querySelector("#faultEventList");
  if (!list) return;
  const faults = state.chain?.emulator?.recent_faults ?? [];
  list.innerHTML = "";
  if (!faults.length) {
    appendListText(list, "폴트 주입 이벤트 없음");
    return;
  }
  for (const fault of faults.slice().reverse()) {
    const item = document.createElement("li");
    item.className = fault.severity === "critical" ? "rejected" : "pending";
    item.textContent = `${fault.fault_type} / ${fault.target_component ?? fault.target ?? "system"}`;
    item.title = `${fault.safety_boundary ?? "simulation only"}\n${JSON.stringify(fault.effects ?? {})}`;
    list.appendChild(item);
  }
}

function renderRecommendedResponses() {
  const list = document.querySelector("#recommendedResponseList");
  if (!list) return;
  const alerts = state.alerts?.alerts ?? [];
  list.innerHTML = "";
  if (!alerts.length) {
    appendListText(list, "기본 감시 지속 중");
    return;
  }
  for (const alert of alerts.slice().reverse()) {
    const item = document.createElement("li");
    item.className = alert.severity === "critical" ? "rejected" : "pending";
    item.textContent = alert.recommended_response ?? "Review simulated event";
    item.title = `${alert.title ?? "alert"} / ${alert.target ?? "system"}`;
    list.appendChild(item);
  }
}

function renderDockerServiceStatus() {
  const node = document.querySelector("#dockerServiceStatusTable");
  if (!node) return;
  const rows = state.serviceStatus?.service_statuses ?? state.dashboard?.service_statuses ?? [];
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">Docker 서비스 상태 스냅샷 없음</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead><tr><th>서비스</th><th>컨테이너</th><th>상태</th><th>경계</th><th>지표</th><th>링크</th></tr></thead>
      <tbody>
        ${rows.map((row) => {
          const emBadge = row.emulated
            ? `<span class="sim-badge sim-badge-emulated">EMULATED</span>`
            : `<span class="sim-badge sim-badge-real">REAL/MOCK</span>`;
          const healthUrl = row.health_url ?? "/health";
          const statusUrl = row.status_url ?? "/status";
          return `
          <tr>
            <td><strong>${escapeHtml(row.label)}</strong><br><span class="muted-cell">${escapeHtml(row.role)}</span></td>
            <td><code>${escapeHtml(row.container_name ?? row.service_id)}</code><br>${emBadge}</td>
            <td><span class="protocol-pill ${statusClass(row.status)}">${escapeHtml(row.status)}</span></td>
            <td class="boundary-cell">${escapeHtml(row.boundary)}</td>
            <td>${escapeHtml(metricSummary(row.metrics))}</td>
            <td class="link-cell">
              <a href="${escapeHtml(healthUrl)}" target="_blank" rel="noreferrer">health</a>
              <a href="${escapeHtml(statusUrl)}" target="_blank" rel="noreferrer">status</a>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
}

function renderCommandLog() {
  const node = document.querySelector("#commandLogTable");
  if (!node) return;
  const rows = state.protocolMonitor?.commands ?? [];
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">No command events yet</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead><tr><th>Command</th><th>Asset</th><th>Status</th><th>Dry Run</th><th>Requested By</th></tr></thead>
      <tbody>
        ${rows.slice().reverse().map((row) => `
          <tr>
            <td>${escapeHtml(row.command_type)}<br><span class="muted-cell">${escapeHtml(row.command_id)}</span></td>
            <td>${escapeHtml(row.asset_id)}</td>
            <td><span class="protocol-pill ${statusClass(row.status)}">${escapeHtml(row.status)}</span></td>
            <td>${escapeHtml(row.dry_run)}</td>
            <td>${escapeHtml(row.requested_by)}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderTacticalMessageLog() {
  const node = document.querySelector("#tacticalMessageLogTable");
  if (!node) return;
  const rows = state.protocolMonitor?.tactical_messages ?? [];
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">No tactical messages yet</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead><tr><th>Message</th><th>Route</th><th>Layer</th><th>Priority</th><th>Payload</th></tr></thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.message_type)}<br><span class="muted-cell">${escapeHtml(row.message_id)}</span></td>
            <td>${escapeHtml(row.source)} -> ${escapeHtml(row.destination)}</td>
            <td>${escapeHtml(row.layer)}</td>
            <td>${escapeHtml(row.priority)}</td>
            <td>${escapeHtml(metricSummary(row.payload?.metrics ?? row.payload))}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderScenarioPackages() {
  const node = document.querySelector("#scenarioPackageTable");
  const summary = document.querySelector("#scenarioPackageStatus");
  if (!node) return;
  const payload = state.scenarioPackages ?? {};
  const rows = payload.scenarios ?? [];
  if (summary) {
    summary.textContent = `${rows.length} scenario(s) / index ${payload.index_available ? "available" : "not generated"}`;
  }
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">No DAH training scenarios found</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead><tr><th>Scenario</th><th>Fault Profile</th><th>Goal</th><th>Expected Logs</th><th>Package Command</th></tr></thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td><strong>${escapeHtml(row.scenario_name)}</strong><br><span class="muted-cell">${escapeHtml(row.scenario_file)}</span></td>
            <td>${escapeHtml(row.fault_profile)}</td>
            <td>${escapeHtml(row.training_goal)}</td>
            <td>${escapeHtml((row.expected_logs ?? []).join(", "))}</td>
            <td><code>${escapeHtml(row.package_command)}</code></td>
          </tr>`).join("")}
      </tbody>
    </table>
    <p class="protocol-text scenario-package-command">Batch: <code>${escapeHtml(payload.batch_command ?? "")}</code></p>
    <p class="protocol-text scenario-package-command">Briefing: <code>${escapeHtml(payload.briefing_command ?? "")}</code></p>`;
}
function renderFaultControls() {
  const select = document.querySelector("#faultTypeSelect");
  if (!select) return;
  const current = select.value;
  const faults = state.dashboard?.fault_allowlist ?? [];
  select.innerHTML = faults.map((fault) => `<option value="${escapeHtml(fault)}">${escapeHtml(fault)}</option>`).join("");
  if (current && faults.includes(current)) select.value = current;
}

async function refreshDahDashboard() {
  const [dashboard, chain, alerts, protocolMonitor, serviceStatus, scenarioPackages] = await Promise.all([
    api("/api/dashboard"),
    api("/api/chain"),
    api("/api/alerts?limit=20"),
    api("/api/protocol-monitor?limit=20"),
    api("/api/service-status"),
    api("/api/scenario-packages"),
  ]);
  state.dashboard = dashboard.payload;
  state.chain = chain.payload;
  state.alerts = alerts.payload;
  state.protocolMonitor = protocolMonitor.payload;
  state.serviceStatus = serviceStatus.payload;
  state.scenarioPackages = scenarioPackages.payload;
  document.title = state.dashboard?.title ?? document.title;
  renderGcsSummary();
  renderChain();
  renderAlerts();
  renderDefenseDecisions();
  renderFaultEvents();
  renderRecommendedResponses();
  renderDockerServiceStatus();
  renderCommandLog();
  renderTacticalMessageLog();
  renderScenarioPackages();
  renderFaultControls();
}

async function injectSelectedFault() {
  const select = document.querySelector("#faultTypeSelect");
  const faultType = select?.value;
  if (!faultType) return { skipped: true, reason: "No fault type selected" };
  const result = await postApi("/api/faults/inject", {
    fault_type: faultType,
    requested_by: "dashboard-operator",
  });
  await refreshDahDashboard().catch(console.error);
  await refreshWorkQueues().catch(console.error);
  return result;
}
function renderSummary() {
  document.querySelector("#scenarioName").textContent = state.scenario.name;
  document.querySelector("#assetCount").textContent = state.summary.asset_count;
  document.querySelector("#missionCount").textContent = state.summary.mission_count;
  document.querySelector("#approvedCount").textContent = state.summary.approved_missions.length;
  document.querySelector("#c2Count").textContent = state.summary.c2_node_count ?? state.scenario.c2_nodes.length;
  document.querySelector("#linkRate").textContent = `Link ${Math.round((state.summary.link_coverage_rate ?? 0) * 100)}%`;

  const decisionList = document.querySelector("#decisionList");
  decisionList.innerHTML = "";
  for (const decision of state.decisions.filter((item) => !isTemporaryMissionId(item.mission_id))) {
    const item = document.createElement("li");
    item.className = decision.approved ? "approved" : "rejected";
    item.textContent = `${decision.approved ? "Approved" : "Rejected"} / ${decision.mission_id}`;
    if (!decision.approved) item.title = decision.reasons.join("\n");
    decisionList.appendChild(item);
  }

  const counts = document.querySelector("#mavlinkCounts");
  counts.innerHTML = "";
  for (const [name, count] of Object.entries(state.summary.mavlink_message_counts ?? {})) {
    const node = document.createElement("div");
    node.innerHTML = `<strong>${name}</strong><br>${count.toLocaleString()} messages`;
    counts.appendChild(node);
  }
}

async function loadSnapshot(index) {
  state.tickIndex = Math.max(0, Math.min(index, state.timeline.length - 1));
  const time = state.timeline[state.tickIndex] ?? 0;
  const [snapshot, tracks] = await Promise.all([
    api(`/api/live/snapshot?time_s=${time}`),
    api(`/api/tracks?time_s=${time}`),
  ]);
  applySnapshot(snapshot.payload);
  applyTracks(tracks.payload);
  slider.value = state.tickIndex;
}

function applySnapshot(snapshot) {
  state.snapshot = snapshot;
  document.querySelector("#clockLabel").textContent = `T+${state.snapshot.time_s}s`;
  document.querySelector("#modeLabel").textContent = state.live ? "라이브" : "재생";
  drawMap();
  renderAssetTable();
  renderEdgeLiveStatusTable();
}

function applyTracks(tracks) {
  state.tracks = tracks;
  document.querySelector("#trackCount").textContent = tracks.track_count;
  document.querySelector("#fusionMode").textContent = tracks.mode;
  renderTrackTable();
}

function renderOperationProfile() {
  const list = document.querySelector("#domainList");
  list.innerHTML = "";
  for (const domain of state.operationProfile.domains) {
    const item = document.createElement("li");
    item.textContent = domain.domain.replaceAll("_", " ");
    item.title = domain.service_fields.join(", ");
    list.appendChild(item);
  }
}


function visibleEdgeDevices() {
  return (state.edgeDevices?.edge_devices ?? []).filter((device) => !isTemporaryEdgeDevice(device));
}

function isTemporaryEdgeDevice(device) {
  const edgeId = String(device?.edge_id ?? "").toLowerCase();
  const software = String(device?.software_version ?? "").toLowerCase();
  return edgeId.startsWith("edge-test-") || software === "edge-dev" || software.includes("sample");
}
function renderEdgeDevices() {
  const list = document.querySelector("#edgeDeviceList");
  if (!list) return;
  list.innerHTML = "";
  const devices = visibleEdgeDevices();
  if (!devices.length) {
    const item = document.createElement("li");
    item.textContent = "등록된 엣지 디바이스 없음";
    list.appendChild(item);
    return;
  }
  for (const device of devices) {
    const item = document.createElement("li");
    item.textContent = `${device.status} / ${device.edge_id} / ${device.device_type}`;
    item.title = `assets: ${(device.asset_ids ?? []).join(", ")}\nlink: ${(device.link_profiles ?? []).join(", ")}\nlast seen: ${device.last_seen_utc ?? "-"}`;
    list.appendChild(item);
  }
}

function renderLogStorage() {
  const node = document.querySelector("#logStorageState");
  if (!node) return;
  node.innerHTML = "";
  const entries = [
    ["이벤트", state.logStatus?.event_count ?? 0],
    ["무결성", state.logIntegrity == null ? "미조회" : state.logIntegrity?.valid ? "정상" : "이상"],
    ["프로파일", state.logStatus?.profile ?? "-"],
    ["해시", state.logStatus?.last_hash ? state.logStatus.last_hash.slice(0, 12) : "없음"],
  ];
  for (const [label, value] of entries) {
    const item = document.createElement("div");
    item.innerHTML = `<strong>${label}</strong><br>${value}`;
    node.appendChild(item);
  }
  const link = document.querySelector("#logStorageLink");
  if (link) link.textContent = state.logStatus?.current_file ?? "logs/uas_utm/audit.jsonl";
}

function renderProtocolMonitorSummary() {
  const node = document.querySelector("#protocolMonitorState");
  if (!node) return;
  const monitor = state.protocolMonitor;
  node.innerHTML = "";
  const entries = [
    ["스키마", monitor?.schema_version ?? "-"],
    ["MAVLink", monitor?.mavlink_adapter?.mode ?? "-"],
    ["텔레메트리", monitor?.telemetry?.length ?? 0],
    ["커맨드", monitor?.commands?.length ?? 0],
    ["전술 메시지", monitor?.tactical_messages?.length ?? 0],
    ["경보", monitor?.alerts?.length ?? 0],
  ];
  for (const [label, value] of entries) {
    const item = document.createElement("div");
    item.innerHTML = `<strong>${escapeHtml(label)}</strong><br>${escapeHtml(value)}`;
    node.appendChild(item);
  }
  const boundary = document.querySelector("#protocolMonitorBoundary");
  if (boundary) boundary.textContent = monitor?.safety_boundary ?? "프로토콜 모니터 미로드";
}
function renderMavlinkState() {
  const node = document.querySelector("#mavlinkState");
  if (!node) return;
  node.innerHTML = "";
  const entries = [
    ["TX/RX", "14551 UDP"],
    ["Ingress", "14550 UDP"],
    ["CRC", "X.25 + CRC_EXTRA"],
    ["Signing", "Optional MAVLink2"],
  ];
  for (const [label, value] of entries) {
    const item = document.createElement("div");
    item.innerHTML = `<strong>${label}</strong><br>${value}`;
    node.appendChild(item);
  }
}
function renderProtocolRuns() {
  const list = document.querySelector("#protocolRunList");
  if (!list) return;
  list.innerHTML = "";
  const rows = state.protocolRuns.slice(-8).reverse();
  if (!rows.length) {
    appendListText(list, "프로토콜 버튼을 클릭하여 실행하세요");
    return;
  }
  for (const run of rows) {
    const item = document.createElement("li");
    item.className = run.ok === false ? "rejected" : run.ok ? "approved" : "";
    const shortDetail = run.ok === false && run.detail ? ` / ${run.detail.slice(0, 90)}` : "";
    item.textContent = `${run.status} / ${run.label}${shortDetail}`;
    item.title = `${run.time}\n${run.detail || ""}`;
    list.appendChild(item);
  }
}

function renderProtocolLogs() {
  const node = document.querySelector("#protocolLogTable");
  if (!node) return;
  const rows = state.protocolLogs?.protocol_logs ?? [];
  const status = document.querySelector("#protocolLogStatus");
  if (status) {
    const heartbeat = state.protocolLogs?.include_heartbeat ? "포함" : "숨김";
    const mode = state.protocolLogLive ? "실시간" : "일시정지";
    status.textContent = `${state.protocolLogs?.count ?? 0}건의 프로토콜 이벤트 / 심박 ${heartbeat} / ${mode}`;
  }
  const toggle = document.querySelector("#toggleHeartbeatButton");
  if (toggle) toggle.textContent = state.showProtocolHeartbeat ? "심박 숨기기" : "심박 표시";
  const liveToggle = document.querySelector("#toggleProtocolLiveButton");
  if (liveToggle) liveToggle.textContent = state.protocolLogLive ? "실시간 일시정지" : "실시간 재개";
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">아직 프로토콜 로그 이벤트가 없습니다</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>시각</th><th>플로우</th><th>프로토콜</th><th>대상</th><th>상태</th><th>요약</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .slice()
          .reverse()
          .map((row) => {
            const target = row.asset_id || row.mission_id || row.object_id || "system";
            return `
          <tr title="${escapeHtml(row.event_id)}">
            <td>${escapeHtml(formatTime(row.timestamp_utc))}</td>
            <td><span class="protocol-pill ${flowClass(row.direction)}">${escapeHtml(row.direction)}</span></td>
            <td><strong>${escapeHtml(row.message_type)}</strong><br><span class="muted-cell">${escapeHtml(row.transport)}</span></td>
            <td>${escapeHtml(target)}</td>
            <td><span class="protocol-pill ${statusClass(row.status)}">${escapeHtml(row.status)}</span></td>
            <td>${escapeHtml(row.summary)}</td>
          </tr>`;
          })
          .join("")}
      </tbody>
    </table>`;
}

function renderRuntimeLogs() {
  const node = document.querySelector("#runtimeLogTable");
  if (!node) return;
  const rows = state.runtimeLogs?.runtime_logs ?? [];
  const status = document.querySelector("#runtimeLogStatus");
  if (status) status.textContent = `${state.runtimeLogs?.count ?? 0} service access logs / ${state.protocolLogLive ? "live" : "paused"}`;
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">No service runtime logs yet</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead>
        <tr><th>Time</th><th>Source</th><th>Level</th><th>Message</th></tr>
      </thead>
      <tbody>
        ${rows
          .slice()
          .reverse()
          .map(
            (row) => `
          <tr>
            <td>${escapeHtml(formatTime(row.timestamp_utc))}</td>
            <td>${escapeHtml(row.source)}</td>
            <td><span class="protocol-pill runtime-level">${escapeHtml(row.level)}</span></td>
            <td>${escapeHtml(row.message)}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").slice(0, 19);
}

function escapeHtml(value) {
  return String(value ?? "-").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}
function flowClass(value) {
  if (value === "operator_to_utm") return "flow-operator";
  if (value === "approver_to_utm") return "flow-approver";
  if (String(value).startsWith("edge_to_utm")) return "flow-edge";
  return "flow-service";
}

function statusClass(value) {
  const text = String(value ?? "").toLowerCase();
  if (text === "critical" || text.includes("reject") || text.includes("error")) return "status-critical";
  if (text === "degraded" || text.includes("warn") || text.includes("pending")) return "status-degraded";
  if (text === "normal" || text.includes("approved") || text.includes("accepted") || text.includes("received") || text.includes("online")) return "status-normal";
  return "status-neutral";
}

async function refreshProtocolLogsOnly() {
  const heartbeatParam = state.showProtocolHeartbeat ? "true" : "false";
  const [protocolLogs, runtimeLogs, logStatus] = await Promise.all([
    api(`/api/protocol/logs?limit=120&include_heartbeat=${heartbeatParam}`),
    api("/api/runtime/logs?limit=120"),
    api("/api/logs/status"),
  ]);
  state.protocolLogs = protocolLogs.payload;
  state.runtimeLogs = runtimeLogs.payload;
  state.logStatus = logStatus.payload;
  renderProtocolLogs();
  renderRuntimeLogs();
  renderLogStorage();
}

function startProtocolLogLive() {
  if (state.protocolLogTimer) clearInterval(state.protocolLogTimer);
  state.protocolLogTimer = setInterval(() => {
    if (!state.protocolLogLive) return;
    refreshProtocolLogsOnly().catch(console.error);
  }, 2000);
}
function actionDetail(result) {
  if (result === undefined || result === null) return "No response body";
  const value = result?.payload ?? result;
  if (value === undefined || value === null) return "No response body";
  if (typeof value === "string") return value.slice(0, 5000);
  try {
    const encoded = JSON.stringify(value, null, 2);
    return (encoded ?? String(value)).slice(0, 5000);
  } catch (error) {
    return String(value).slice(0, 5000);
  }
}
async function runProtocolAction(label, action) {
  const entry = { label, status: "실행 중", ok: null, time: new Date().toISOString(), detail: "" };
  state.protocolRuns.push(entry);
  renderProtocolRuns();
  try {
    const result = await action();
    entry.status = result?.skipped ? "건너뜀" : "완료";
    entry.ok = result?.skipped ? null : true;
    entry.detail = actionDetail(result);
    renderProtocolRuns();
    // 상태 UI 즉시 반영 후 백그라운드에서 큐 새로고침
    refreshWorkQueues().catch((refreshError) => {
      entry.status = "완료 (새로고침 실패)";
      entry.detail = `${entry.detail}\n\n새로고침 오류: ${refreshError.message}`;
      renderProtocolRuns();
      refreshProtocolLogsOnly().catch(console.error);
    });
  } catch (error) {
    entry.status = "오류";
    entry.ok = false;
    entry.detail = error.message;
    renderProtocolRuns();
  }
}
async function refreshWorkQueues() {
  const heartbeatParam = state.showProtocolHeartbeat ? "true" : "false";
  // /api/logs/verify 는 전체 해시 체인 검증으로 느림 — 별도 버튼으로만 호출
  const [commands, missionUploads, audit, logStatus, protocolLogs, edgeDevices] = await Promise.all([
    api("/api/commands"),
    api("/api/mission-uploads"),
    api("/api/audit?limit=80"),
    api("/api/logs/status"),
    api(`/api/protocol/logs?limit=80&include_heartbeat=${heartbeatParam}`),
    api("/api/edge/devices"),
  ]);
  state.commands = commands.payload;
  state.missionUploads = missionUploads.payload;
  state.audit = audit.payload;
  state.logStatus = logStatus.payload;
  state.protocolLogs = protocolLogs.payload;
  state.edgeDevices = edgeDevices.payload;
  renderCommandPanel();
  renderMissionUploadPanel();
  renderAuditTimeline();
  renderLogStorage();
  renderProtocolLogs();
  renderEdgeDevices();
  renderEdgeLiveStatusTable();
}

function renderCommandPanel() {
  const list = document.querySelector("#commandQueueList");
  if (!list) return;
  const commands = state.commands?.commands ?? [];
  list.innerHTML = "";
  if (!commands.length) {
    appendListText(list, "커맨드 요청 없음");
  } else {
    for (const command of commands.slice(-6).reverse()) {
      const item = document.createElement("li");
      item.className = command.status === "rejected" ? "rejected" : command.status === "approved_for_gateway" ? "approved" : "";
      item.textContent = `${command.status} / ${command.asset_id} / ${command.command_type}`;
      item.title = `command_id: ${command.command_id}\nrequested_by: ${command.requested_by}\ncreated_at: ${command.created_at}`;
      list.appendChild(item);
    }
  }
  setQueueCount("#pendingCommandCount", commands, "pending_approval");
  setQueueCount("#approvedCommandCount", commands, "approved_for_gateway");
}

function renderMissionUploadPanel() {
  const list = document.querySelector("#missionUploadQueueList");
  if (!list) return;
  const uploads = state.missionUploads?.mission_uploads ?? [];
  list.innerHTML = "";
  if (!uploads.length) {
    appendListText(list, "미션 업로드 없음");
  } else {
    for (const upload of uploads.slice(-6).reverse()) {
      const item = document.createElement("li");
      item.className = upload.status === "approved_for_gateway" ? "approved" : "";
      item.textContent = `${upload.status} / ${upload.mission_id} / ${upload.asset_id}`;
      item.title = `upload_id: ${upload.upload_id}\nitems: ${upload.mavlink_items?.length ?? 0}\ncreated_at: ${upload.created_at}`;
      list.appendChild(item);
    }
  }
  setQueueCount("#pendingUploadCount", uploads, "pending_approval");
  setQueueCount("#approvedUploadCount", uploads, "approved_for_gateway");
}

function renderAuditTimeline() {
  const list = document.querySelector("#auditTimelineList");
  if (!list) return;
  const rows = state.audit?.audit ?? [];
  list.innerHTML = "";
  if (!rows.length) {
    appendListText(list, "감사 이벤트 없음");
    return;
  }
  for (const event of rows.slice(-10).reverse()) {
    const item = document.createElement("li");
    const data = event.data ?? {};
    const target = data.command_id ?? data.upload_id ?? data.edge_id ?? data.asset_id ?? "system";
    item.textContent = `${event.event_type} / ${target}`;
    item.title = `${event.created_at}\n${JSON.stringify(data, null, 2)}`;
    list.appendChild(item);
  }
}

function setQueueCount(selector, rows, status) {
  const node = document.querySelector(selector);
  if (!node) return;
  node.textContent = rows.filter((row) => row.status === status).length;
}

function appendListText(list, text) {
  const item = document.createElement("li");
  item.textContent = text;
  list.appendChild(item);
}

function visibleMapC2Nodes(frames) {
  const c2Ids = new Set((frames ?? []).map((frame) => frame.c2_node_id).filter(Boolean));
  if (!c2Ids.size) return [];
  return (state.scenario?.c2_nodes ?? []).filter((node) => c2Ids.has(node.id));
}
function visibleMapMissions() {
  const edgeIds = new Set(registeredEdgeAssetIds());
  if (!edgeIds.size) return [];
  return visibleMissions().filter((mission) => edgeIds.has(mission.asset_id));
}

function visibleMapFrames() {
  const externalFrames = state.snapshot?.external_frames ?? [];
  const frameByEdgeAsset = new Map(
    externalFrames.map((frame) => [`${frame.source_id ?? frame.source ?? "external"}:${frame.asset_id}`, frame])
  );
  return registeredEdgeAssignments()
    .map((assignment) => {
      const frame = frameByEdgeAsset.get(`${assignment.edge_id}:${assignment.asset_id}`);
      if (!frame) return null;
      return {
        ...frame,
        edge_id: assignment.edge_id,
        edge_device_type: assignment.device_type,
        edge_status: assignment.status,
        edge_authority: assignment.authority,
      };
    })
    .filter(Boolean)
    .filter((frame) => !isTemporaryMissionId(frame.mission_id));
}
function visibleMissions() {
  return (state.scenario?.missions ?? []).filter((mission) => !isTemporaryMission(mission));
}

function isTemporaryMissionId(missionId) {
  const mission = (state.scenario?.missions ?? []).find((item) => item.id === missionId);
  return mission ? isTemporaryMission(mission) : false;
}

function isTemporaryMission(mission) {
  const haystack = `${mission.id ?? ""} ${mission.purpose ?? ""} ${mission.mission_type ?? ""}`.toLowerCase();
  return haystack.includes("invalid") || haystack.includes("sample") || haystack.includes("validation") || haystack.includes("test");
}
function defaultCommandAssetId() {
  return state.scenario.assets.find((asset) => asset.datalink_profiles.includes("mavlink_udp"))?.id ?? state.scenario.assets[0]?.id;
}

function defaultMissionId() {
  const approved = new Set(state.summary?.approved_missions ?? []);
  return visibleMissions().find((mission) => approved.has(mission.id))?.id ?? visibleMissions()[0]?.id;
}

async function requestHoldCommand() {
  const assetId = defaultCommandAssetId();
  if (!assetId) return { skipped: true, reason: "No command-capable asset found" };
  const result = await postApi("/api/commands/request", {
    asset_id: assetId,
    command_type: "hold_position",
    requested_by: "dashboard-operator",
    priority: 2,
    params: { param1: 0 },
  });
  await refreshWorkQueues().catch(console.error);
  return result;
}

async function approveNextCommand() {
  const command = (state.commands?.commands ?? []).find((item) => item.status === "pending_approval");
  if (!command) return { skipped: true, reason: "No pending command to approve" };
  const result = await postApi("/api/commands/approve", { command_id: command.command_id, approver: "dashboard-approver" });
  await refreshWorkQueues().catch(console.error);
  return result;
}

async function rejectNextCommand() {
  const command = (state.commands?.commands ?? []).find((item) => item.status === "pending_approval");
  if (!command) return { skipped: true, reason: "No pending command to reject" };
  const result = await postApi("/api/commands/reject", {
    command_id: command.command_id,
    rejector: "dashboard-approver",
    reason: "operator rejected from dashboard",
  });
  await refreshWorkQueues().catch(console.error);
  return result;
}

async function requestMissionUpload() {
  const missionId = defaultMissionId();
  if (!missionId) return { skipped: true, reason: "No approved mission available" };
  const result = await postApi("/api/mission-uploads/request", { mission_id: missionId, requested_by: "dashboard-operator" });
  await refreshWorkQueues().catch(console.error);
  return result;
}

async function approveNextMissionUpload() {
  const upload = (state.missionUploads?.mission_uploads ?? []).find((item) => item.status === "pending_approval");
  if (!upload) return { skipped: true, reason: "No pending mission upload to approve" };
  const result = await postApi("/api/mission-uploads/approve", { upload_id: upload.upload_id, approver: "dashboard-approver" });
  await refreshWorkQueues().catch(console.error);
  return result;
}

function missionIdForAsset(assetId) {
  const approved = new Set(state.summary?.approved_missions ?? []);
  return visibleMissions().find((mission) => mission.asset_id === assetId && approved.has(mission.id))?.id ?? defaultMissionId();
}

function edgeIdForAsset(assetId) {
  const device = visibleEdgeDevices().find((item) => (item.asset_ids ?? []).includes(assetId));
  if (device) return device.edge_id;
  if (assetId === "ground-convoy-01") return "edge-dashboard-ugv-01";
  if (assetId === "small-dronebot-01") return "edge-dronebot-01";
  return "edge-dashboard-01";
}

async function refreshEdgeDevicesOnly() {
  const edgeDevices = await api("/api/edge/devices");
  state.edgeDevices = edgeDevices.payload;
  renderEdgeDevices();
  drawMap();
  renderAssetTable();
  return edgeDevices;
}

async function deleteEdgeDevice(edgeId) {
  if (!confirm(`엣지 디바이스 "${edgeId}"를 삭제하시겠습니까?`)) return;
  try {
    const resp = await fetch(`/api/edge/devices/${encodeURIComponent(edgeId)}`, { method: "DELETE" });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body?.payload?.error ?? `HTTP ${resp.status}`);
    }
    await refreshEdgeDevicesOnly();
    renderEdgeLiveStatusTable();
  } catch (e) {
    alert(`삭제 실패: ${e.message}`);
  }
}

async function afterEdgeRegistration(result) {
  await refreshEdgeDevicesOnly().catch(console.error);
  emitRegisteredEdgeTelemetry().catch(console.error);
  return result;
}
async function registerDashboardUgv() {
  const result = await postApi("/api/edge/devices/register", {
    edge_id: "edge-dashboard-ugv-01",
    device_type: "ugv_edge",
    role: "edge_gateway",
    asset_ids: ["ground-convoy-01"],
    capabilities: ["telemetry_ingest", "approved_work_poll", "ack_work"],
    link_profiles: ["mavlink_udp", "mesh_ground"],
    authority: "ROKA Ground Robotics Cell",
    software_version: "dashboard-edge-0.1",
    public_key_fingerprint: "dashboard-demo",
  });
  return afterEdgeRegistration(result);
}

async function registerDashboardDronebot() {
  const result = await postApi("/api/edge/devices/register", {
    edge_id: "edge-dronebot-01",
    device_type: "uav_edge",
    role: "edge_gateway",
    asset_ids: ["small-dronebot-01"],
    capabilities: ["telemetry_ingest", "approved_work_poll", "ack_work"],
    link_profiles: ["mavlink_udp"],
    authority: "ROKA UTM Cell",
    software_version: "dashboard-edge-0.1",
    public_key_fingerprint: "dashboard-demo",
  });
  return afterEdgeRegistration(result);
}

async function ensureDashboardDronebotRegistered() {
  const devices = visibleEdgeDevices();
  if (devices.some((device) => device.edge_id === "edge-dronebot-01")) return null;
  const result = await registerDashboardDronebot();
  try {
    const edgeDevices = await api("/api/edge/devices");
    state.edgeDevices = edgeDevices.payload;
    renderEdgeDevices();
  } catch (error) {
    console.warn(error);
  }
  return result;
}
async function ensureDashboardUgvRegistered() {
  const devices = visibleEdgeDevices();
  if (devices.some((device) => device.edge_id === "edge-dashboard-ugv-01")) return null;
  const result = await registerDashboardUgv();
  try {
    const edgeDevices = await api("/api/edge/devices");
    state.edgeDevices = edgeDevices.payload;
    renderEdgeDevices();
  } catch (error) {
    console.warn(error);
  }
  return result;
}
async function heartbeatDashboardUgv() {
  await ensureDashboardUgvRegistered();
  return postApi("/api/edge/devices/heartbeat", {
    edge_id: "edge-dashboard-ugv-01",
    status: "online",
    cpu_load: 0.24,
    battery_wh: 3800,
    link_quality: 0.93,
    temperature_c: 39.1,
  });
}

function registeredEdgeAssignments() {
  const assignments = [];
  for (const device of visibleEdgeDevices()) {
    for (const assetId of device.asset_ids ?? []) {
      assignments.push({
        edge_id: device.edge_id,
        asset_id: assetId,
        device_type: device.device_type,
        status: device.status,
        authority: device.authority,
        link_profiles: device.link_profiles ?? [],
      });
    }
  }
  return assignments;
}

function registeredEdgeAssetIds() {
  return [...new Set(registeredEdgeAssignments().map((item) => item.asset_id))];
}

function missionForAsset(assetId) {
  const approved = new Set(state.summary?.approved_missions ?? []);
  return visibleMissions().find((mission) => mission.asset_id === assetId && approved.has(mission.id))
    ?? visibleMissions().find((mission) => mission.asset_id === assetId);
}

function routePositionAt(mission, elapsedS) {
  const route = mission?.route ?? [];
  if (route.length === 0) return [0, 0, 0];
  if (route.length === 1) return route[0];
  const segments = [];
  let total = 0;
  for (let index = 0; index < route.length - 1; index += 1) {
    const start = route[index];
    const end = route[index + 1];
    const length = Math.hypot(end[0] - start[0], end[1] - start[1], (end[2] ?? 0) - (start[2] ?? 0));
    segments.push({ start, end, length });
    total += length;
  }
  if (total <= 0) return route[0];
  const speed = Number(mission.nominal_speed_mps ?? 8);
  let distance = (elapsedS * Math.max(2, speed)) % total;
  for (const segment of segments) {
    if (distance > segment.length) {
      distance -= segment.length;
      continue;
    }
    const ratio = segment.length <= 0 ? 0 : distance / segment.length;
    return [
      segment.start[0] + (segment.end[0] - segment.start[0]) * ratio,
      segment.start[1] + (segment.end[1] - segment.start[1]) * ratio,
      (segment.start[2] ?? 0) + ((segment.end[2] ?? 0) - (segment.start[2] ?? 0)) * ratio,
    ];
  }
  return route[route.length - 1];
}

function edgeOffsetFor(edgeId, assetId) {
  const peers = registeredEdgeAssignments().filter((item) => item.asset_id === assetId).map((item) => item.edge_id).sort();
  const index = Math.max(0, peers.indexOf(edgeId));
  const count = Math.max(1, peers.length);
  if (count === 1) return [0, 0, 0];
  const angle = (Math.PI * 2 * index) / count;
  const radius = 18 + Math.min(18, count * 3);
  return [Math.cos(angle) * radius, Math.sin(angle) * radius, 0];
}

function offsetPositionForEdge(position, edgeId, assetId) {
  const offset = edgeOffsetFor(edgeId, assetId);
  return [
    Number(position[0] ?? 0) + offset[0],
    Number(position[1] ?? 0) + offset[1],
    Number(position[2] ?? 0) + offset[2],
  ];
}

function edgePhaseSeconds(edgeId) {
  let hash = 0;
  for (const ch of String(edgeId)) hash = (hash * 31 + ch.charCodeAt(0)) % 997;
  return (hash % 11) * 0.7;
}

function edgeTelemetryPayload(assetId, edgeId, assignmentIndex = 0, device = {}) {
  const mission = missionForAsset(assetId);
  const elapsedS = ((Date.now() - state.edgeMotionStartedAt) / 1000) + edgePhaseSeconds(edgeId) + assignmentIndex * 0.35;
  const basePosition = routePositionAt(mission, elapsedS);
  let position = offsetPositionForEdge(basePosition, edgeId, assetId);
  const isUgv = assetId.includes("ground") || assetId.includes("ugv") || String(device.device_type ?? "").includes("ugv");
  const linkProfile = (device.link_profiles ?? [])[0] ?? (isUgv ? "mesh_ground" : "mavlink_udp");

  const trackConfidence = 0.91;
  const linkQuality = isUgv ? 0.94 : 0.97;
  const missionId = mission?.id ?? null;
  const velocity = isUgv ? [5.5, 0.4, 0] : [14, 1.2, 0.1];

  return {
    asset_id: assetId,
    time_s: state.timeline[state.tickIndex] ?? Math.round(elapsedS),
    position,
    velocity_mps: velocity,
    heading_deg: (elapsedS * (isUgv ? 8 : 16)) % 360,
    mission_id: missionId,
    status: "edge-live",
    battery_wh: isUgv ? 3725 : 690,
    c2_node_id: isUgv ? "ground-control-west" : "ground-control-east",
    link_profile: linkProfile,
    link_quality: linkQuality,
    source: "dashboard-edge-sim",
    source_id: edgeId,
    source_type: device.device_type ?? "edge_gateway",
    source_authority: device.authority ?? (isUgv ? "ROKA Ground Robotics Cell" : "ROKA UTM Cell"),
    track_confidence: trackConfidence,
  };
}

async function emitRegisteredEdgeTelemetry() {
  const assignments = registeredEdgeAssignments();
  if (!assignments.length) return { skipped: true, reason: "No registered edge assets" };
  const accepted = [];
  for (const [index, assignment] of assignments.entries()) {
    const result = await postApi(
      "/api/telemetry/ingest",
      edgeTelemetryPayload(assignment.asset_id, assignment.edge_id, index, assignment)
    );
    accepted.push(result.payload ?? result);
  }
  const time = state.timeline[state.tickIndex] ?? 0;
  const [snapshot, tracks] = await Promise.all([
    api(`/api/live/snapshot?time_s=${time}`),
    api(`/api/tracks?time_s=${time}`),
  ]);
  applySnapshot(snapshot.payload);
  applyTracks(tracks.payload);
  return { accepted };
}

function startEdgeMotionLive() {
  if (state.edgeMotionTimer) clearInterval(state.edgeMotionTimer);
  state.edgeMotionTimer = setInterval(async () => {
    if (state.edgeMotionBusy) return;
    if (!registeredEdgeAssignments().length) return;
    state.edgeMotionBusy = true;
    try {
      await emitRegisteredEdgeTelemetry();
    } catch (error) {
      console.error(error);
    } finally {
      state.edgeMotionBusy = false;
    }
  }, 600);
}
async function ingestDashboardUgvTelemetry() {
  await ensureDashboardUgvRegistered();
  return emitRegisteredEdgeTelemetry();
}

async function ingestDashboardUgvTelemetryOnce() {
  return postApi("/api/telemetry/ingest", {
    asset_id: "ground-convoy-01",
    time_s: state.timeline[state.tickIndex] ?? 0,
    position: [-960, -520, 0],
    velocity_mps: [4.5, 0.6, 0],
    heading_deg: 82,
    mission_id: "ugv-convoy-route-clearance",
    status: "edge-live",
    battery_wh: 3725,
    c2_node_id: "ground-control-west",
    link_profile: "mesh_ground",
    source: "dashboard-edge-sim",
    source_id: "edge-dashboard-ugv-01",
    source_authority: "ROKA Ground Robotics Cell",
    track_confidence: 0.91,
  });
}

async function requestUgvHoldCommand() {
  return postApi("/api/commands/request", {
    asset_id: "ground-convoy-01",
    command_type: "hold_position",
    requested_by: "dashboard-operator",
    priority: 2,
    params: { param1: 0 },
  });
}

async function requestUgvMissionUpload() {
  return postApi("/api/mission-uploads/request", {
    mission_id: missionIdForAsset("ground-convoy-01"),
    requested_by: "dashboard-operator",
  });
}

async function ensureEdgeRegisteredForAsset(assetId) {
  if (assetId === "ground-convoy-01") return ensureDashboardUgvRegistered();
  if (assetId === "small-dronebot-01") return ensureDashboardDronebotRegistered();
  return null;
}
async function pollEdgeWork(edgeId) {
  if (edgeId === "edge-dashboard-ugv-01") await ensureDashboardUgvRegistered();
  if (edgeId === "edge-dronebot-01") await ensureDashboardDronebotRegistered();
  return api(`/api/edge/work?edge_id=${encodeURIComponent(edgeId)}`);
}

async function ackLatestApprovedWork() {
  const uploads = [...(state.missionUploads?.mission_uploads ?? [])].reverse();
  const upload = uploads.find((item) => item.status === "approved_for_gateway");
  if (upload) {
    await ensureEdgeRegisteredForAsset(upload.asset_id);
    return postApi("/api/edge/work/ack", {
      edge_id: edgeIdForAsset(upload.asset_id),
      object_type: "mission_upload",
      object_id: upload.upload_id,
      result: "received_by_dashboard_edge",
    });
  }
  const commands = [...(state.commands?.commands ?? [])].reverse();
  const command = commands.find((item) => item.status === "approved_for_gateway");
  if (command) {
    await ensureEdgeRegisteredForAsset(command.asset_id);
    return postApi("/api/edge/work/ack", {
      edge_id: edgeIdForAsset(command.asset_id),
      object_type: "command",
      object_id: command.command_id,
      result: "received_by_dashboard_edge",
    });
  }
  return { skipped: true, reason: "No approved command or mission upload to ACK" };
}
function connectLive() {
  if (state.eventSource) state.eventSource.close();
  state.live = true;
  state.playing = false;
  playButton.classList.remove("active");
  liveButton.classList.add("active");
  state.eventSource = new EventSource("/api/live/stream?interval_ms=1000&max_events=100000");
  state.eventSource.addEventListener("telemetry", (event) => {
    const message = JSON.parse(event.data);
    applySnapshot(message.payload);
    api(`/api/tracks?time_s=${message.payload.time_s}`).then((tracks) => applyTracks(tracks.payload));
    const index = state.timeline.indexOf(message.payload.time_s);
    if (index >= 0) {
      state.tickIndex = index;
      slider.value = index;
    }
  });
  state.eventSource.onerror = () => {
    document.querySelector("#serviceStatus").textContent = "Stream retry";
  };
}

function disconnectLive() {
  state.live = false;
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  liveButton.classList.remove("active");
  document.querySelector("#modeLabel").textContent = "Replay";
}

function drawMap() {
  const scenario = state.scenario;
  const frames = visibleMapFrames();
  const bounds = calculateBounds(scenario);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#dfeaf3";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawGrid();

  for (const zone of scenario.zones) drawZone(zone, bounds);
  for (const node of visibleMapC2Nodes(frames)) drawC2(node, bounds);
  for (const mission of visibleMapMissions()) drawRoute(mission, bounds);
  for (const frame of frames) drawAsset(frame, bounds);
  if (!frames.length) drawMapHint();
}

function drawMapHint() {
  ctx.fillStyle = "rgba(24,32,42,0.72)";
  ctx.font = "14px Segoe UI";
  ctx.fillText("엣지 텔레메트리 없음 — 엣지 디바이스를 등록 후 텔레메트리를 실행하세요", 24, canvas.height - 28);
}
function calculateBounds(scenario) {
  const xs = [];
  const ys = [];
  for (const zone of scenario.zones) {
    xs.push(zone.x_min, zone.x_max);
    ys.push(zone.y_min, zone.y_max);
  }
  for (const mission of visibleMapMissions()) {
    for (const point of mission.route) {
      xs.push(point[0]);
      ys.push(point[1]);
    }
  }
  const pad = 180;
  return {
    minX: Math.min(...xs) - pad,
    maxX: Math.max(...xs) + pad,
    minY: Math.min(...ys) - pad,
    maxY: Math.max(...ys) + pad,
  };
}

function project(point, bounds) {
  const x = ((point[0] - bounds.minX) / (bounds.maxX - bounds.minX)) * canvas.width;
  const y = canvas.height - ((point[1] - bounds.minY) / (bounds.maxY - bounds.minY)) * canvas.height;
  return [x, y];
}

function drawGrid() {
  ctx.strokeStyle = "rgba(24,32,42,0.12)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 10; i += 1) {
    const x = (canvas.width / 10) * i;
    const y = (canvas.height / 10) * i;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }
}

function drawZone(zone, bounds) {
  const [x1, y1] = project([zone.x_min, zone.y_min, 0], bounds);
  const [x2, y2] = project([zone.x_max, zone.y_max, 0], bounds);
  const x = Math.min(x1, x2);
  const y = Math.min(y1, y2);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);
  const color = zone.kind === "no_fly_zone" ? "#b42318" : zone.kind === "restricted_altitude" ? "#b06100" : "#146c94";
  ctx.fillStyle = `${color}22`;
  ctx.strokeStyle = color;
  ctx.lineWidth = zone.kind === "operating_area" ? 2 : 1.5;
  ctx.fillRect(x, y, w, h);
  ctx.strokeRect(x, y, w, h);
  ctx.fillStyle = color;
  ctx.font = "13px Segoe UI";
  ctx.fillText(zone.id, x + 8, y + 18);
}

function drawC2(node, bounds) {
  const [x, y] = project(node.location, bounds);
  ctx.fillStyle = "#2d7d46";
  ctx.beginPath();
  ctx.arc(x, y, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = "12px Segoe UI";
  ctx.fillText(node.id, x + 8, y - 8);
}

function drawRoute(mission, bounds) {
  ctx.strokeStyle = "rgba(20,108,148,0.38)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  mission.route.forEach((point, index) => {
    const [x, y] = project(point, bounds);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function drawAsset(frame, bounds) {
  const [x, y] = project(frame.position, bounds);
  const external = frame.source && frame.source !== "simulation";
  const active = frame.status === "active" || external;
  const isUgv = String(frame.edge_device_type ?? frame.asset_id ?? "").includes("ugv") || String(frame.asset_id ?? "").includes("ground");
  ctx.fillStyle = external ? (isUgv ? "#7a4e12" : "#7c3aed") : active ? "#146c94" : "#617080";
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(x, y, external ? 9 : active ? 8 : 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#18202a";
  ctx.font = "13px Segoe UI";
  ctx.fillText(frame.edge_id ?? frame.source_id ?? "unregistered-edge", x + 10, y + 4);
}

function renderAssetTable() {
  const rows = visibleMapFrames();
  const html = `
    <table>
      <thead>
        <tr>
          <th>엣지</th><th>자산</th><th>상태</th><th>미션</th><th>C2</th><th>링크</th><th>위치</th><th>배터리</th><th>소스</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (frame) => `
          <tr>
            <td>${escapeHtml(frame.edge_id ?? frame.source_id ?? "-")}</td>
            <td>${escapeHtml(frame.asset_id)}</td>
            <td>${escapeHtml(frame.status)}</td>
            <td>${escapeHtml(frame.mission_id ?? "-")}</td>
            <td>${escapeHtml(frame.c2_node_id ?? "-")}</td>
            <td>${escapeHtml(frame.link_profile ?? "-")}</td>
            <td>${frame.position.map((v) => Number(v).toFixed(1)).join(", ")}</td>
            <td>${Number(frame.battery_wh ?? 0).toFixed(1)} Wh</td>
            <td>${escapeHtml(frame.source_id ?? frame.source ?? "simulation")}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
  document.querySelector("#assetTable").innerHTML = html;
}

function renderEdgeLiveStatusTable() {
  const node = document.querySelector("#edgeLiveStatusTable");
  if (!node) return;
  const frames = visibleMapFrames();
  const frameByEdgeAsset = new Map(frames.map((frame) => [`${frame.edge_id ?? frame.source_id}:${frame.asset_id}`, frame]));
  const rows = registeredEdgeAssignments().map((assignment) => ({
    ...assignment,
    frame: frameByEdgeAsset.get(`${assignment.edge_id}:${assignment.asset_id}`),
  }));
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">등록된 엣지 디바이스 없음</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead><tr><th>엣지 ID</th><th>에셋 ID</th><th>유형</th><th>상태</th><th>텔레메트리</th><th>미션</th><th>링크</th><th>위치</th><th>권한</th><th></th></tr></thead>
      <tbody>
        ${rows.map(({ frame, ...edge }) => `
          <tr>
            <td><strong>${escapeHtml(edge.edge_id)}</strong></td>
            <td>${escapeHtml(edge.asset_id)}</td>
            <td>${escapeHtml(edge.device_type ?? "-")}</td>
            <td><span class="protocol-pill ${statusClass(edge.status)}">${escapeHtml(edge.status ?? "registered")}</span></td>
            <td>${frame ? "live" : "waiting"}</td>
            <td>${escapeHtml(frame?.mission_id ?? missionForAsset(edge.asset_id)?.id ?? "-")}</td>
            <td>${escapeHtml(frame?.link_profile ?? (edge.link_profiles ?? [])[0] ?? "-")}</td>
            <td>${frame ? frame.position.map((v) => Number(v).toFixed(1)).join(", ") : "-"}</td>
            <td>${escapeHtml(edge.authority ?? "-")}</td>
            <td><button class="edge-delete-btn" onclick="deleteEdgeDevice('${escapeHtml(edge.edge_id)}')" title="엣지 디바이스 삭제">✕</button></td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderTrackTable() {
  const rows = state.tracks?.tracks ?? [];
  const html = `
    <table>
      <thead>
        <tr>
          <th>트랙</th><th>기본 소스</th><th>신뢰도</th><th>권한</th><th>위치</th><th>소스 수</th><th>지연</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (track) => `
          <tr>
            <td>${track.asset_id}</td>
            <td>${track.primary_source_id}</td>
            <td>${Math.round(track.confidence * 100)}%</td>
            <td>${track.authority ?? "-"}</td>
            <td>${track.fused_position.map((v) => Number(v).toFixed(1)).join(", ")}</td>
            <td>${track.source_count}</td>
            <td>${track.stale ? "yes" : "no"}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
  document.querySelector("#trackTable").innerHTML = html;
}

slider.addEventListener("input", () => {
  disconnectLive();
  loadSnapshot(Number(slider.value));
});

playButton.addEventListener("click", () => {
  disconnectLive();
  state.playing = !state.playing;
  playButton.classList.toggle("active", state.playing);
  playButton.textContent = state.playing ? "일시정지" : "재생";
});

liveButton.addEventListener("click", () => {
  if (state.live) disconnectLive();
  else connectLive();
});

setInterval(() => {
  if (!state.playing || !state.timeline.length) return;
  const next = (state.tickIndex + 1) % state.timeline.length;
  loadSnapshot(next);
}, 650);

const requestCommandButton = document.querySelector("#requestCommandButton");
if (requestCommandButton) requestCommandButton.addEventListener("click", () => requestHoldCommand().catch(console.error));

const approveCommandButton = document.querySelector("#approveCommandButton");
if (approveCommandButton) approveCommandButton.addEventListener("click", () => approveNextCommand().catch(console.error));

const rejectCommandButton = document.querySelector("#rejectCommandButton");
if (rejectCommandButton) rejectCommandButton.addEventListener("click", () => rejectNextCommand().catch(console.error));

const requestMissionUploadButton = document.querySelector("#requestMissionUploadButton");
if (requestMissionUploadButton) requestMissionUploadButton.addEventListener("click", () => requestMissionUpload().catch(console.error));

const approveMissionUploadButton = document.querySelector("#approveMissionUploadButton");
if (approveMissionUploadButton) approveMissionUploadButton.addEventListener("click", () => approveNextMissionUpload().catch(console.error));
function bindProtocolButton(selector, label, action) {
  const button = document.querySelector(selector);
  if (!button) return;
  button.addEventListener("click", () => runProtocolAction(label, action));
}

bindProtocolButton("#protocolHealthButton", "GET /api/health — 시스템 점검", () => api("/api/health"));
// 모달 오프닝 버튼 — 팝업이 열리며 실제 API는 모달 제출 시 호출됨
document.querySelector("#protocolRegisterUgvButton")?.addEventListener("click", openEdgeRegisterModal);
document.querySelector("#protocolRequestCommandButton")?.addEventListener("click", openCommandModal);
document.querySelector("#protocolRequestMissionButton")?.addEventListener("click", openMissionModal);
bindProtocolButton("#protocolHeartbeatUgvButton", "POST 엣지 심박 전송", heartbeatDashboardUgv);
bindProtocolButton("#protocolTelemetryUgvButton", "POST 텔레메트리 전송 (지도 갱신)", ingestDashboardUgvTelemetry);
bindProtocolButton("#protocolApproveCommandButton", "POST 커맨드 승인", approveNextCommand);
bindProtocolButton("#protocolApproveMissionButton", "POST 미션 업로드 승인", approveNextMissionUpload);
bindProtocolButton("#protocolPollDronebotButton", "GET UAV 작업 조회", () => pollEdgeWork("edge-dronebot-01"));
bindProtocolButton("#protocolPollUgvButton", "GET UGV 작업 조회", () => pollEdgeWork(edgeIdForAsset("ground-convoy-01")));
bindProtocolButton("#protocolAckLatestButton", "POST 작업 ACK 전송", ackLatestApprovedWork);
bindProtocolButton("#protocolVerifyLogsButton", "GET 감사 로그 검증", async () => {
  const result = await api("/api/logs/verify", 60000);  // 해시체인 검증은 최대 60초 허용
  state.logIntegrity = result.payload;
  renderLogStorage();
  return result;
});
bindProtocolButton("#injectFaultButton", "POST 시뮬레이션 폴트 주입", injectSelectedFault);

const refreshProtocolLogButton = document.querySelector("#refreshProtocolLogButton");
if (refreshProtocolLogButton) refreshProtocolLogButton.addEventListener("click", () => refreshProtocolLogsOnly().catch(console.error));

const toggleProtocolLiveButton = document.querySelector("#toggleProtocolLiveButton");
if (toggleProtocolLiveButton) {
  toggleProtocolLiveButton.addEventListener("click", () => {
    state.protocolLogLive = !state.protocolLogLive;
    renderProtocolLogs();
    renderRuntimeLogs();
    if (state.protocolLogLive) refreshProtocolLogsOnly().catch(console.error);
  });
}
const toggleHeartbeatButton = document.querySelector("#toggleHeartbeatButton");
if (toggleHeartbeatButton) {
  toggleHeartbeatButton.addEventListener("click", () => {
    state.showProtocolHeartbeat = !state.showProtocolHeartbeat;
    refreshProtocolLogsOnly().catch(console.error);
  });
}
// ── 침입 탐지 (Intrusion Detection) ──────────────────────────────────
// 외부 공격 컨테이너가 주입하는 특징적 필드로 탐지
const IDS_SIGNATURES = [
  // 기존 시나리오 시그니처
  { field: "source_authority", value: "EXTERNAL-ATTACKER", label: "외부 공격자 권한" },
  { field: "source", prefix: "GNSS-SPOOF",   label: "GNSS 스푸핑 소스" },
  { field: "source", prefix: "DYN-SPOOF",    label: "동역학 GPS 스푸핑" },
  { field: "source", prefix: "SYNC-DISRUPT", label: "협동 동기화 교란" },
  { field: "source", prefix: "ATTACK:",      label: "공격 소스 마커" },
  // 어드벤스드 시나리오 시그니처
  { field: "source", prefix: "SYBIL-FLEET",  label: "Sybil 유령 함대" },
  { field: "source", prefix: "FDI-FUSION",   label: "Track Fusion FDI" },
  { field: "source", prefix: "ALERT-NOISE",  label: "Alert Fatigue 노이즈" },
];

function _idsCheckTelemetry(payload) {
  const alerts = [];

  // 알려진 공격 source 필드
  for (const sig of IDS_SIGNATURES) {
    const v = payload[sig.field] ?? "";
    const hit = sig.value ? v === sig.value : v.startsWith(sig.prefix ?? "");
    if (hit) {
      alerts.push({
        severity: "critical",
        code: sig.label,
        asset_id: payload.asset_id,
        edge_id: payload.source_id ?? payload.edge_id,
        detail: `${sig.field}="${v}"`,
        time: new Date().toISOString(),
      });
    }
  }

  // 미인가 엣지 ID 패턴 탐지 (edge-attack-*, edge-sybil-*, edge-noise-*)
  const srcId = payload.source_id ?? "";
  const ROGUE_PREFIXES = ["edge-attack-", "edge-sybil-", "edge-noise-"];
  if (ROGUE_PREFIXES.some((p) => srcId.startsWith(p))) {
    alerts.push({
      severity: "critical",
      code: "미인가 엣지 ID",
      asset_id: payload.asset_id,
      edge_id: srcId,
      detail: `등록되지 않은 공격 엣지: ${srcId}`,
      time: new Date().toISOString(),
    });
  }

  // link_quality 급락 탐지 (0.3 미만)
  if (typeof payload.link_quality === "number" && payload.link_quality < 0.3) {
    alerts.push({
      severity: "warning",
      code: "링크 품질 이상",
      asset_id: payload.asset_id,
      edge_id: srcId,
      detail: `link_quality=${payload.link_quality.toFixed(3)} (임계값: 0.3)`,
      time: new Date().toISOString(),
    });
  }

  // track_confidence 급락 탐지 (0.6 미만)
  if (typeof payload.track_confidence === "number" && payload.track_confidence < 0.6) {
    alerts.push({
      severity: "warning",
      code: "트랙 신뢰도 이상",
      asset_id: payload.asset_id,
      edge_id: srcId,
      detail: `track_confidence=${payload.track_confidence.toFixed(3)} (임계값: 0.6)`,
      time: new Date().toISOString(),
    });
  }

  return alerts;
}

function _idsCheckCommand(payload) {
  const alerts = [];
  const reqBy = payload.requested_by ?? "";
  if (reqBy.startsWith("ATTACKER:")) {
    alerts.push({
      severity: "critical",
      code: "커맨드 인젝션 탐지",
      asset_id: payload.asset_id,
      edge_id: reqBy,
      detail: `불법 커맨드 요청: ${payload.command_type} (requested_by="${reqBy}")`,
      time: new Date().toISOString(),
    });
  }
  return alerts;
}

function _idsRaiseAlerts(newAlerts) {
  if (!newAlerts.length) return;
  for (const alert of newAlerts) {
    const isDup = state.intrusionAlerts.some(
      (a) => a.code === alert.code && a.asset_id === alert.asset_id && a.edge_id === alert.edge_id
        && (new Date(alert.time) - new Date(a.time)) < 10000
    );
    if (!isDup) {
      state.intrusionAlerts.unshift(alert);
      if (state.intrusionAlerts.length > 50) state.intrusionAlerts.pop();
    }
  }
  renderIntrusionAlerts();
}

function renderIntrusionAlerts() {
  const el = document.querySelector("#intrusionAlertList");
  if (!el) return;
  if (!state.intrusionAlerts.length) {
    el.innerHTML = "<li class='ids-clear'>탐지된 침입 없음</li>";
    return;
  }
  el.innerHTML = state.intrusionAlerts.map((a) => {
    const ts = new Date(a.time).toLocaleTimeString("ko-KR");
    const cls = a.severity === "critical" ? "ids-critical" : "ids-warning";
    const icon = a.severity === "critical" ? "🚨" : "⚠";
    return `<li class="${cls}">${icon} [${ts}] <strong>${a.code}</strong> — ${a.asset_id ?? ""} ${a.edge_id ? `(${a.edge_id})` : ""}: ${a.detail}</li>`;
  }).join("");
}

// 주기적으로 GCS 텔레메트리 로그에서 침입 신호 폴링 (5초 간격)
async function pollIntrusionDetection() {
  try {
    // 최근 트랙 데이터에서 이상 필드 탐지
    const tracks = await api("/api/tracks");
    const entries = tracks?.payload?.tracks ?? [];
    const alerts = [];
    for (const entry of entries) {
      alerts.push(..._idsCheckTelemetry(entry));
    }

    // 최근 커맨드에서 ATTACKER 요청 탐지
    const cmds = await api("/api/commands").catch(() => null);
    for (const cmd of (cmds?.payload?.commands ?? [])) {
      alerts.push(..._idsCheckCommand(cmd));
    }

    _idsRaiseAlerts(alerts);
  } catch (_) {
    // 폴링 실패는 무시
  }
}

setInterval(() => pollIntrusionDetection().catch(() => {}), 5000);

// ── 모달: 엣지 디바이스 등록 ──────────────────────────────────────────
const COMMAND_TYPES = [
  { value: "hold_position",     label: "홀드 포지션",    desc: "현재 위치에서 정지 유지" },
  { value: "return_to_launch",  label: "귀환",           desc: "이륙 지점으로 자동 복귀" },
  { value: "goto",              label: "좌표 이동",      desc: "지정 좌표로 이동" },
  { value: "land",              label: "착륙",           desc: "현재 위치에서 착륙" },
  { value: "set_mode",          label: "모드 변경",      desc: "비행 모드 전환 (GUIDED/AUTO 등)" },
  { value: "waypoint_advance",  label: "웨이포인트 전진", desc: "다음 미션 경유점으로 이동" },
];

let _selectedCommandType = "hold_position";
let _selectedMissionId = null;

function openEdgeRegisterModal() {
  const modal = document.querySelector("#edgeRegisterModal");
  if (!modal) return;
  updateEdgeDockerHint();
  document.querySelector("#edgeRegDeviceType")?.addEventListener("change", updateEdgeDockerHint);
  document.querySelector("#edgeRegAssetId")?.addEventListener("change", updateEdgeDockerHint);
  document.querySelector("#edgeRegEdgeId")?.addEventListener("input", updateEdgeDockerHint);
  document.querySelector("#edgeRegAuthority")?.addEventListener("input", updateEdgeDockerHint);
  document.querySelector("#edgeRegLinkProfile")?.addEventListener("change", updateEdgeDockerHint);
  modal.showModal();
}

function updateEdgeDockerHint() {
  const deviceType = document.querySelector("#edgeRegDeviceType")?.value ?? "ugv_edge";
  const assetId    = document.querySelector("#edgeRegAssetId")?.value ?? "ground-convoy-01";
  const edgeId     = document.querySelector("#edgeRegEdgeId")?.value ?? "edge-dashboard-ugv-01";
  const authority  = document.querySelector("#edgeRegAuthority")?.value ?? "ROKA UTM Cell";
  const linkProfile= document.querySelector("#edgeRegLinkProfile")?.value ?? "mavlink_udp";
  const cmd = [
    `docker run --rm --network dah-ops-net`,
    `  dah_temp-dah-gcs uas-utm-edge`,
    `  --service-url http://dah-gcs:8080`,
    `  --edge-id ${edgeId}`,
    `  --device-type ${deviceType}`,
    `  --asset ${assetId}`,
    `  --authority "${authority}"`,
    `  --link-profile ${linkProfile}`,
    `  --software-version dashboard-1.0`,
    `  --emit-sample-telemetry`,
  ].join("\n");
  const hint = document.querySelector("#edgeDockerHint");
  if (hint) hint.innerHTML = `<strong>Docker 명령어</strong><br><code id="edgeDockerCmd">${cmd}</code>`;
}

async function submitEdgeRegistration() {
  const edgeId      = document.querySelector("#edgeRegEdgeId")?.value?.trim() ?? "edge-dashboard-ugv-01";
  const deviceType  = document.querySelector("#edgeRegDeviceType")?.value ?? "ugv_edge";
  const assetId     = document.querySelector("#edgeRegAssetId")?.value ?? "ground-convoy-01";
  const authority   = document.querySelector("#edgeRegAuthority")?.value?.trim() ?? "ROKA UTM Cell";
  const linkProfile = document.querySelector("#edgeRegLinkProfile")?.value ?? "mavlink_udp";
  document.querySelector("#edgeRegisterModal")?.close();
  const result = await runProtocolAction(`POST 엣지 등록 — ${edgeId}`, () =>
    postApi("/api/edge/devices/register", {
      edge_id: edgeId,
      device_type: deviceType,
      asset_ids: [assetId],
      authority,
      link_profiles: [linkProfile],
      capabilities: ["telemetry_ingest", "approved_work_poll", "ack_work"],
      software_version: "dashboard-1.0",
    })
  );
  await afterEdgeRegistration(result);
  return result;
}

// ── 모달: 커맨드 발행 ──────────────────────────────────────────────────
function openCommandModal() {
  const modal = document.querySelector("#commandModal");
  if (!modal) return;
  _renderCommandTypeList();
  modal.showModal();
}

function _renderCommandTypeList() {
  const container = document.querySelector("#commandTypeList");
  if (!container) return;
  container.innerHTML = COMMAND_TYPES.map((ct) => `
    <label class="cmd-type-item${ct.value === _selectedCommandType ? " selected" : ""}">
      <input type="radio" name="cmdType" value="${ct.value}"${ct.value === _selectedCommandType ? " checked" : ""}>
      <div class="cmd-type-info">
        <strong>${ct.label}</strong>
        <span>${ct.desc}</span>
      </div>
    </label>`).join("");
  container.querySelectorAll("input[type=radio]").forEach((radio) => {
    radio.addEventListener("change", () => {
      _selectedCommandType = radio.value;
      container.querySelectorAll(".cmd-type-item").forEach((el) => el.classList.remove("selected"));
      radio.closest(".cmd-type-item")?.classList.add("selected");
    });
  });
}

async function submitCommandFromModal() {
  const assetId    = document.querySelector("#cmdModalAssetId")?.value ?? "ground-convoy-01";
  const autoApprove = document.querySelector("#cmdAutoApprove")?.checked ?? true;
  document.querySelector("#commandModal")?.close();
  await runProtocolAction(`POST 커맨드 요청 — ${_selectedCommandType} → ${assetId}`, async () => {
    const result = await postApi("/api/commands/request", {
      asset_id: assetId,
      command_type: _selectedCommandType,
      requested_by: "dashboard-operator",
      dry_run: true,
    });
    if (autoApprove) {
      const commandId = result?.payload?.command_id;
      if (commandId) await postApi("/api/commands/approve", { command_id: commandId });
    }
    return result;
  });
}

// ── 모달: 미션 발행 ────────────────────────────────────────────────────
function openMissionModal() {
  const modal = document.querySelector("#missionModal");
  if (!modal) return;
  _renderMissionCardList();
  modal.showModal();
}

function _renderMissionCardList() {
  const container = document.querySelector("#missionCardList");
  if (!container) return;
  const missions = state.scenario?.missions ?? [];
  const approved = new Set(state.summary?.approved_missions ?? []);
  if (!missions.length) {
    container.innerHTML = '<p class="modal-hint">미션 목록을 불러오는 중...</p>';
    return;
  }
  container.innerHTML = missions.map((m) => {
    const isApproved = approved.has(m.id);
    const selected   = m.id === _selectedMissionId || (!_selectedMissionId && isApproved);
    if (!_selectedMissionId && isApproved) _selectedMissionId = m.id;
    return `
      <label class="mission-card${selected ? " selected" : ""}${!isApproved ? " unavailable" : ""}"
             title="${isApproved ? "클릭하여 선택" : "UTM 미승인 미션 — 업로드 불가"}">
        <input type="radio" name="missionId" value="${m.id}"${selected ? " checked" : ""}${!isApproved ? " disabled" : ""}>
        <div class="mission-card-info">
          <strong>${m.id}</strong>
          <span>${m.mission_type ?? "transit"} · 자산: ${m.asset_id ?? "-"} · 경유점: ${(m.route ?? []).length}개</span>
        </div>
        <span class="mission-badge ${isApproved ? "approved" : ""}">${isApproved ? "UTM 승인" : "UTM 미승인"}</span>
      </label>`;
  }).join("");
  container.querySelectorAll("input[type=radio]").forEach((radio) => {
    radio.addEventListener("change", () => {
      _selectedMissionId = radio.value;
      container.querySelectorAll(".mission-card").forEach((el) => el.classList.remove("selected"));
      radio.closest(".mission-card")?.classList.add("selected");
    });
  });
}

async function submitMissionFromModal() {
  const missionId   = _selectedMissionId;
  const autoApprove = document.querySelector("#missionAutoApprove")?.checked ?? true;
  document.querySelector("#missionModal")?.close();
  if (!missionId) { alert("미션을 선택하세요"); return; }
  await runProtocolAction(`POST 미션 업로드 요청 — ${missionId}`, async () => {
    const result = await postApi("/api/mission-uploads/request", {
      mission_id: missionId,
      requested_by: "dashboard-operator",
    });
    if (autoApprove) {
      const uploadId = result?.payload?.upload_id;
      if (uploadId) await postApi("/api/mission-uploads/approve", { upload_id: uploadId });
    }
    return result;
  });
}

// ── 모달 버튼 이벤트 연결 ───────────────────────────────────────────────
document.querySelector("#edgeRegSubmitButton")?.addEventListener("click", () => submitEdgeRegistration().catch(console.error));
document.querySelector("#cmdSubmitButton")?.addEventListener("click", () => submitCommandFromModal().catch(console.error));
document.querySelector("#missionSubmitButton")?.addEventListener("click", () => submitMissionFromModal().catch(console.error));

bootstrap().catch((error) => {
  document.querySelector("#serviceStatus").textContent = "API 오류";
  console.error(error);
});
