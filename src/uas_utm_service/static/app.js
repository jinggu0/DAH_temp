const state = {
  scenario: null,
  summary: null,
  decisions: [],
  timeline: [],
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
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function bootstrap() {
  const [health, protocol, scenario, summary, decisions, timeline] = await Promise.all([
    api("/api/health"),
    api("/api/protocol"),
    api("/api/scenario"),
    api("/api/summary"),
    api("/api/decisions"),
    api("/api/timeline"),
  ]);
  document.querySelector("#serviceStatus").textContent = health.payload.ok ? "API OK" : "API Error";
  document.querySelector("#protocolText").textContent =
    `${protocol.payload.profile} ${protocol.payload.version} / ${protocol.payload.transport.live_push}`;
  state.scenario = scenario.payload;
  state.summary = summary.payload;
  state.decisions = decisions.payload;
  state.timeline = timeline.payload.ticks;
  slider.min = 0;
  slider.max = Math.max(0, state.timeline.length - 1);
  slider.value = 0;
  renderSummary();
  await loadSnapshot(0);
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
  for (const decision of state.decisions) {
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
  const snapshot = await api(`/api/live/snapshot?time_s=${time}`);
  applySnapshot(snapshot.payload);
  slider.value = state.tickIndex;
}

function applySnapshot(snapshot) {
  state.snapshot = snapshot;
  document.querySelector("#clockLabel").textContent = `T+${state.snapshot.time_s}s`;
  document.querySelector("#modeLabel").textContent = state.live ? "Live" : "Replay";
  drawMap();
  renderAssetTable();
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
  const frames = [...(state.snapshot?.frames ?? []), ...(state.snapshot?.external_frames ?? [])];
  const bounds = calculateBounds(scenario);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#dfeaf3";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawGrid();

  for (const zone of scenario.zones) drawZone(zone, bounds);
  for (const node of scenario.c2_nodes) drawC2(node, bounds);
  for (const mission of scenario.missions) drawRoute(mission, bounds);
  for (const frame of frames) drawAsset(frame, bounds);
}

function calculateBounds(scenario) {
  const xs = [];
  const ys = [];
  for (const zone of scenario.zones) {
    xs.push(zone.x_min, zone.x_max);
    ys.push(zone.y_min, zone.y_max);
  }
  for (const mission of scenario.missions) {
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
  const rows = [...(state.snapshot?.frames ?? []), ...(state.snapshot?.external_frames ?? [])];
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

bootstrap().catch((error) => {
  document.querySelector("#serviceStatus").textContent = "API Error";
  console.error(error);
});
