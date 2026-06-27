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
};

const canvas = document.querySelector("#airspaceCanvas");
const ctx = canvas.getContext("2d");
const slider = document.querySelector("#timeSlider");
const playButton = document.querySelector("#playButton");
const liveButton = document.querySelector("#liveButton");

async function api(path) {
  const response = await fetch(path, { cache: "no-store" });
  let body = null;
  try {
    body = await response.json();
  } catch (error) {
    body = null;
  }
  if (!response.ok) throw new Error(body?.payload?.error ?? `${path}: ${response.status}`);
  return body;
}

async function postApi(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload }),
  });
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
  const [health, protocol, scenario, summary, decisions, timeline, operationProfile, edgeDevices, commands, missionUploads, audit, logStatus, logIntegrity, protocolLogs, runtimeLogs, dashboard, chain, alerts, protocolMonitor] = await Promise.all([
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
    api("/api/logs/verify"),
    api("/api/protocol/logs?limit=80&include_heartbeat=false"),
    api("/api/runtime/logs?limit=80"),
    api("/api/dashboard"),
    api("/api/chain"),
    api("/api/alerts?limit=20"),
    api("/api/protocol-monitor?limit=20"),
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
  state.logIntegrity = logIntegrity.payload;
  state.protocolLogs = protocolLogs.payload;
  state.runtimeLogs = runtimeLogs.payload;
  state.dashboard = dashboard.payload;
  state.chain = chain.payload;
  state.alerts = alerts.payload;
  state.protocolMonitor = protocolMonitor.payload;
  slider.min = 0;
  slider.max = Math.max(0, state.timeline.length - 1);
  slider.value = 0;
  renderGcsSummary();
  renderChain();
  renderAlerts();
  renderFaultControls();
  renderSummary();
  renderOperationProfile();
  renderEdgeDevices();
  renderCommandPanel();
  renderMissionUploadPanel();
  renderAuditTimeline();
  renderLogStorage();
  renderProtocolRuns();
  renderProtocolLogs();
  renderRuntimeLogs();
  renderMavlinkState();
  await loadSnapshot(0);
  startProtocolLogLive();
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
      </div>
      ${index < chain.nodes.length - 1 ? '<div class="chain-arrow">-></div>' : ''}`)
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
    appendListText(list, "No simulated alerts");
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

function renderFaultControls() {
  const select = document.querySelector("#faultTypeSelect");
  if (!select) return;
  const current = select.value;
  const faults = state.dashboard?.fault_allowlist ?? [];
  select.innerHTML = faults.map((fault) => `<option value="${escapeHtml(fault)}">${escapeHtml(fault)}</option>`).join("");
  if (current && faults.includes(current)) select.value = current;
}

async function refreshDahDashboard() {
  const [dashboard, chain, alerts, protocolMonitor] = await Promise.all([
    api("/api/dashboard"),
    api("/api/chain"),
    api("/api/alerts?limit=20"),
    api("/api/protocol-monitor?limit=20"),
  ]);
  state.dashboard = dashboard.payload;
  state.chain = chain.payload;
  state.alerts = alerts.payload;
  state.protocolMonitor = protocolMonitor.payload;
  renderGcsSummary();
  renderChain();
  renderAlerts();
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
  document.querySelector("#modeLabel").textContent = state.live ? "Live" : "Replay";
  drawMap();
  renderAssetTable();
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
    item.textContent = "No edge devices registered";
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
    ["Events", state.logStatus?.event_count ?? 0],
    ["Integrity", state.logIntegrity?.valid ? "valid" : "check"],
    ["Profile", state.logStatus?.profile ?? "-"],
    ["Hash", state.logStatus?.last_hash ? state.logStatus.last_hash.slice(0, 12) : "none"],
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
    ["Schema", monitor?.schema_version ?? "-"],
    ["MAVLink", monitor?.mavlink_adapter?.mode ?? "-"],
    ["Telemetry", monitor?.telemetry?.length ?? 0],
    ["Commands", monitor?.commands?.length ?? 0],
    ["Tactical", monitor?.tactical_messages?.length ?? 0],
    ["Alerts", monitor?.alerts?.length ?? 0],
  ];
  for (const [label, value] of entries) {
    const item = document.createElement("div");
    item.innerHTML = `<strong>${escapeHtml(label)}</strong><br>${escapeHtml(value)}`;
    node.appendChild(item);
  }
  const boundary = document.querySelector("#protocolMonitorBoundary");
  if (boundary) boundary.textContent = monitor?.safety_boundary ?? "Protocol monitor not loaded";
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
    appendListText(list, "Click a protocol action to run it");
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
    const heartbeat = state.protocolLogs?.include_heartbeat ? "included" : "hidden";
    const mode = state.protocolLogLive ? "live" : "paused";
    status.textContent = `${state.protocolLogs?.count ?? 0} protocol events / heartbeat ${heartbeat} / ${mode}`;
  }
  const toggle = document.querySelector("#toggleHeartbeatButton");
  if (toggle) toggle.textContent = state.showProtocolHeartbeat ? "Hide Heartbeat" : "Show Heartbeat";
  const liveToggle = document.querySelector("#toggleProtocolLiveButton");
  if (liveToggle) liveToggle.textContent = state.protocolLogLive ? "Pause Live" : "Resume Live";
  if (!rows.length) {
    node.innerHTML = '<p class="protocol-text">No protocol log events yet</p>';
    return;
  }
  node.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Time</th><th>Flow</th><th>Protocol</th><th>Target</th><th>Status</th><th>Summary</th>
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
  if (text.includes("reject") || text.includes("error")) return "status-rejected";
  if (text.includes("approved") || text.includes("accepted") || text.includes("received") || text.includes("online")) return "status-approved";
  if (text.includes("pending")) return "status-pending";
  return "status-neutral";
}

async function refreshProtocolLogsOnly() {
  const heartbeatParam = state.showProtocolHeartbeat ? "true" : "false";
  const [protocolLogs, runtimeLogs, logStatus, logIntegrity] = await Promise.all([
    api(`/api/protocol/logs?limit=120&include_heartbeat=${heartbeatParam}`),
    api("/api/runtime/logs?limit=120"),
    api("/api/logs/status"),
    api("/api/logs/verify"),
  ]);
  state.protocolLogs = protocolLogs.payload;
  state.runtimeLogs = runtimeLogs.payload;
  state.logStatus = logStatus.payload;
  state.logIntegrity = logIntegrity.payload;
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
  const entry = { label, status: "running", ok: null, time: new Date().toISOString(), detail: "" };
  state.protocolRuns.push(entry);
  renderProtocolRuns();
  try {
    const result = await action();
    entry.status = result?.skipped ? "skipped" : "ok";
    entry.ok = result?.skipped ? null : true;
    entry.detail = actionDetail(result);
    try {
      await refreshWorkQueues();
    } catch (refreshError) {
      entry.status = "ok / refresh stale";
      entry.detail = `${entry.detail}\n\nRefresh warning: ${refreshError.message}`;
      refreshProtocolLogsOnly().catch(console.error);
    }
  } catch (error) {
    entry.status = "error";
    entry.ok = false;
    entry.detail = error.message;
  }
  renderProtocolRuns();
}
async function refreshWorkQueues() {
  const heartbeatParam = state.showProtocolHeartbeat ? "true" : "false";
  const [commands, missionUploads, audit, logStatus, logIntegrity, protocolLogs, edgeDevices] = await Promise.all([
    api("/api/commands"),
    api("/api/mission-uploads"),
    api("/api/audit?limit=80"),
    api("/api/logs/status"),
    api("/api/logs/verify"),
    api(`/api/protocol/logs?limit=80&include_heartbeat=${heartbeatParam}`),
    api("/api/edge/devices"),
  ]);
  state.commands = commands.payload;
  state.missionUploads = missionUploads.payload;
  state.audit = audit.payload;
  state.logStatus = logStatus.payload;
  state.logIntegrity = logIntegrity.payload;
  state.protocolLogs = protocolLogs.payload;
  state.edgeDevices = edgeDevices.payload;
  renderCommandPanel();
  renderMissionUploadPanel();
  renderAuditTimeline();
  renderLogStorage();
  renderProtocolLogs();
  renderEdgeDevices();
}

function renderCommandPanel() {
  const list = document.querySelector("#commandQueueList");
  if (!list) return;
  const commands = state.commands?.commands ?? [];
  list.innerHTML = "";
  if (!commands.length) {
    appendListText(list, "No command requests");
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
    appendListText(list, "No mission uploads");
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
    appendListText(list, "No audit events");
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
  const edgeIds = new Set(registeredEdgeAssetIds());
  if (!edgeIds.size) return [];
  const externalByAsset = new Map(externalFrames.map((frame) => [frame.asset_id, frame]));
  return [...edgeIds]
    .map((assetId) => externalByAsset.get(assetId))
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

function registeredEdgeAssetIds() {
  const ids = new Set();
  for (const device of visibleEdgeDevices()) {
    for (const assetId of device.asset_ids ?? []) ids.add(assetId);
  }
  return [...ids];
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

function edgeTelemetryPayload(assetId) {
  const mission = missionForAsset(assetId);
  const elapsedS = (Date.now() - state.edgeMotionStartedAt) / 1000;
  const position = routePositionAt(mission, elapsedS);
  const isUgv = assetId.includes("ground") || assetId.includes("ugv");
  return {
    asset_id: assetId,
    time_s: state.timeline[state.tickIndex] ?? Math.round(elapsedS),
    position,
    velocity_mps: isUgv ? [5.5, 0.4, 0] : [14, 1.2, 0.1],
    heading_deg: (elapsedS * (isUgv ? 8 : 16)) % 360,
    mission_id: mission?.id ?? null,
    status: "edge-live",
    battery_wh: isUgv ? 3725 : 690,
    c2_node_id: isUgv ? "ground-control-west" : "ground-control-east",
    link_profile: isUgv ? "mesh_ground" : "mavlink_udp",
    source: "dashboard-edge-sim",
    source_id: edgeIdForAsset(assetId),
    source_authority: isUgv ? "ROKA Ground Robotics Cell" : "ROKA UTM Cell",
    track_confidence: 0.91,
  };
}

async function emitRegisteredEdgeTelemetry() {
  const assetIds = registeredEdgeAssetIds();
  if (!assetIds.length) return { skipped: true, reason: "No registered edge assets" };
  const accepted = [];
  for (const assetId of assetIds) {
    const result = await postApi("/api/telemetry/ingest", edgeTelemetryPayload(assetId));
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
    if (!registeredEdgeAssetIds().length) return;
    state.edgeMotionBusy = true;
    try {
      await emitRegisteredEdgeTelemetry();
    } catch (error) {
      console.error(error);
    } finally {
      state.edgeMotionBusy = false;
    }
  }, 1500);
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
  ctx.fillText("No protocol edge telemetry. Register an edge device, then run Telemetry.", 24, canvas.height - 28);
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
  ctx.fillStyle = external ? "#7c3aed" : active ? "#146c94" : "#617080";
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(x, y, external ? 9 : active ? 8 : 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#18202a";
  ctx.font = "13px Segoe UI";
  ctx.fillText(frame.asset_id, x + 10, y + 4);
}

function renderAssetTable() {
  const rows = visibleMapFrames();
  const html = `
    <table>
      <thead>
        <tr>
          <th>Asset</th><th>Status</th><th>Mission</th><th>C2</th><th>Link</th><th>Position</th><th>Battery</th><th>Source</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (frame) => `
          <tr>
            <td>${frame.asset_id}</td>
            <td>${frame.status}</td>
            <td>${frame.mission_id ?? "-"}</td>
            <td>${frame.c2_node_id ?? "-"}</td>
            <td>${frame.link_profile ?? "-"}</td>
            <td>${frame.position.map((v) => Number(v).toFixed(1)).join(", ")}</td>
            <td>${Number(frame.battery_wh ?? 0).toFixed(1)} Wh</td>
            <td>${frame.source ?? "simulation"}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
  document.querySelector("#assetTable").innerHTML = html;
}

function renderTrackTable() {
  const rows = state.tracks?.tracks ?? [];
  const html = `
    <table>
      <thead>
        <tr>
          <th>Track</th><th>Primary</th><th>Confidence</th><th>Authority</th><th>Position</th><th>Sources</th><th>Stale</th>
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
  playButton.textContent = state.playing ? "Pause" : "Play";
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

bindProtocolButton("#protocolHealthButton", "GET /api/health", () => api("/api/health"));
bindProtocolButton("#protocolRegisterUgvButton", "POST edge register", registerDashboardUgv);
bindProtocolButton("#protocolHeartbeatUgvButton", "POST edge heartbeat", heartbeatDashboardUgv);
bindProtocolButton("#protocolTelemetryUgvButton", "POST telemetry ingest", ingestDashboardUgvTelemetry);
bindProtocolButton("#protocolRequestCommandButton", "POST command request", requestUgvHoldCommand);
bindProtocolButton("#protocolApproveCommandButton", "POST command approve", approveNextCommand);
bindProtocolButton("#protocolRequestMissionButton", "POST mission upload request", requestUgvMissionUpload);
bindProtocolButton("#protocolApproveMissionButton", "POST mission upload approve", approveNextMissionUpload);
bindProtocolButton("#protocolPollDronebotButton", "GET edge-dronebot work", () => pollEdgeWork("edge-dronebot-01"));
bindProtocolButton("#protocolPollUgvButton", "GET UGV edge work", () => pollEdgeWork(edgeIdForAsset("ground-convoy-01")));
bindProtocolButton("#protocolAckLatestButton", "POST edge work ACK", ackLatestApprovedWork);
bindProtocolButton("#protocolVerifyLogsButton", "GET logs verify", () => api("/api/logs/verify"));
bindProtocolButton("#injectFaultButton", "POST simulated fault", injectSelectedFault);

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
bootstrap().catch((error) => {
  document.querySelector("#serviceStatus").textContent = "API Error";
  console.error(error);
});
