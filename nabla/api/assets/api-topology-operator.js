const GROUP_PREFIX = "operator-group-";

let graph = null;
let topology = null;
let telemetry = null;

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function operatorStatus(message, tone = "neutral") {
  const node = document.getElementById("topology-operator-status");
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
}

async function fetchJson(path) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return response.json();
}

function installStyles() {
  if (!graph) return;
  graph
    .style()
    .selector(".operator-hidden")
    .style({ display: "none" })
    .selector(".operator-group")
    .style({
      shape: "roundrectangle",
      "background-opacity": 0.08,
      "border-width": 1,
      "border-style": "dashed",
      "border-color": "#59616a",
      color: "#9aa4ad",
      "font-size": 9,
      "text-valign": "top",
      "text-halign": "center",
      padding: 18,
      "z-compound-depth": "bottom",
    })
    .update();
}

function hideDocker() {
  if (!graph) return;
  const hidden =
    document.getElementById("topology-hide-docker")?.checked === true;
  graph.batch(() => {
    graph.elements().removeClass("operator-hidden");
    if (!hidden) return;
    const docker = graph.getElementById("docker");
    docker.addClass("operator-hidden");
    graph
      .edges()
      .filter(
        (edge) =>
          edge.data("relationType") === "hostedBy" &&
          edge.data("target") === "docker",
      )
      .addClass("operator-hidden");
  });
}

function removeGroups() {
  if (!graph) return;
  const children = graph.nodes().filter((node) => node.parent().nonempty());
  children.forEach((node) => node.move({ parent: null }));
  graph.nodes(".operator-group").remove();
}

function groupLabel(value, mode) {
  if (mode === "lifecycle") {
    return value
      .split("-")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }
  return value;
}

function networkMembership(nodeId) {
  const source =
    (topology?.nodes || []).find((node) => node.id === nodeId) || {};
  const runtime = source.runtime || {};
  const candidates = source.dockerNetworks || runtime.networks || [];
  return Array.isArray(candidates)
    ? [...new Set(candidates.filter(Boolean).map(String))].sort((left, right) =>
        left.localeCompare(right),
      )
    : [];
}

function groupKeyForNode(node, mode) {
  if (node.hasClass("operator-group") || node.id() === "docker") return "";
  if (mode === "lifecycle")
    return String(node.data("lifecyclePhase") || "unclassified");
  if (mode === "docker-network") {
    const networks = networkMembership(node.id());
    return networks.length > 0 ? networks.join(" + ") : "";
  }
  return "";
}

function applyGrouping() {
  if (!graph) return;
  const mode = document.getElementById("topology-group-by")?.value || "none";
  removeGroups();
  if (mode === "none") return;

  const groups = new Map();
  for (const node of graph.nodes()) {
    const key = groupKeyForNode(node, mode);
    if (!key) continue;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  }

  if (mode === "docker-network" && groups.size === 0) {
    operatorStatus(
      "Docker network grouping is waiting for canonical network-membership metadata from nabla-compose; no network is guessed from names.",
      "warn",
    );
    return;
  }

  graph.batch(() => {
    for (const [key, nodes] of groups.entries()) {
      const safe = key.replace(/[^a-zA-Z0-9_-]/g, "-");
      const id = `${GROUP_PREFIX}${mode}-${safe}`;
      graph.add({
        group: "nodes",
        data: {
          id,
          label: groupLabel(key, mode),
          operatorGroup: true,
          searchText: key,
          lifecyclePhase:
            mode === "lifecycle" && key !== "unclassified" ? key : "",
        },
        classes: "operator-group",
      });
      for (const node of nodes) node.move({ parent: id });
    }
  });
  if (mode === "docker-network") {
    operatorStatus(
      "Docker network groups use the complete canonical Compose membership set; multi-network services are never assigned to an arbitrary first network.",
      "ok",
    );
  }
}

function percentile(values, fraction) {
  const sorted = values
    .filter((value) => value != null && value >= 0)
    .sort((a, b) => a - b);
  if (sorted.length === 0) return null;
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor((sorted.length - 1) * fraction)),
  );
  return sorted[index];
}

function resourceForNode(node) {
  const service = String(node.data("runtimeContainerService") || "");
  return service ? telemetry?.resources?.[service] || null : null;
}

function resetNodeSizing() {
  if (!graph) return;
  graph
    .nodes()
    .not(".operator-group")
    .forEach((node) => {
      node.removeStyle("width");
      node.removeStyle("height");
    });
}

function applyResourceSizing() {
  if (!graph) return;
  const mode =
    document.getElementById("topology-node-sizing")?.value || "declared";
  resetNodeSizing();
  if (mode !== "resources") return;

  const rows = graph
    .nodes()
    .not(".operator-group")
    .map((node) => ({ node, resource: resourceForNode(node) }))
    .filter((row) => row.resource);
  if (rows.length === 0) {
    operatorStatus(
      `CPU/RAM sizing unavailable (${telemetry?.state || "no telemetry"}); declared criticality sizing is retained.`,
      "warn",
    );
    return;
  }

  const cpuP95 =
    percentile(
      rows.map((row) => finite(row.resource.cpu_cores)),
      0.95,
    ) || 1;
  const memoryP95 =
    percentile(
      rows.map((row) => finite(row.resource.memory_bytes)),
      0.95,
    ) || 1;
  for (const { node, resource } of rows) {
    const cpu = Math.min(
      1,
      Math.max(0, (finite(resource.cpu_cores) || 0) / cpuP95),
    );
    const memory = Math.min(
      1,
      Math.max(0, (finite(resource.memory_bytes) || 0) / memoryP95),
    );
    const pressure = Math.max(cpu, memory);
    const size = Math.round(32 + 56 * Math.sqrt(pressure));
    node.style({ width: size, height: size });
    node.data("operatorCpuCores", finite(resource.cpu_cores));
    node.data("operatorMemoryBytes", finite(resource.memory_bytes));
    node.data("operatorNetworkBps", finite(resource.network_bytes_per_second));
  }
}

function resetEdgeSizing() {
  if (!graph) return;
  graph.edges().forEach((edge) => edge.removeStyle("width"));
}

function edgeBandwidth(edge) {
  const byId = telemetry?.edge_bandwidth?.[edge.id()];
  if (byId != null) return finite(byId);
  const key = `${edge.data("source")}->${edge.data("target")}`;
  return finite(telemetry?.edge_bandwidth?.[key]);
}

function applyBandwidthSizing() {
  if (!graph) return;
  const mode =
    document.getElementById("topology-edge-sizing")?.value || "declared";
  resetEdgeSizing();
  if (mode !== "bandwidth") return;

  const rows = graph
    .edges()
    .map((edge) => ({ edge, bytesPerSecond: edgeBandwidth(edge) }))
    .filter((row) => row.bytesPerSecond != null);
  if (rows.length === 0) {
    operatorStatus(
      telemetry?.edge_bandwidth_detail ||
        "Per-edge bandwidth attribution is unavailable; relation widths remain declarative.",
      "warn",
    );
    return;
  }

  const p95 =
    percentile(
      rows.map((row) => row.bytesPerSecond),
      0.95,
    ) || 1;
  for (const { edge, bytesPerSecond } of rows) {
    const ratio = Math.min(1, Math.max(0, bytesPerSecond / p95));
    edge.style("width", 1.5 + 8.5 * Math.sqrt(ratio));
    edge.data("operatorBandwidthBps", bytesPerSecond);
  }
}

function fitAndLayout() {
  if (!graph) return;
  const visible = graph.elements().not(".is-filtered").not(".operator-hidden");
  visible
    .layout({
      name: "cose",
      padding: 32,
      nodeRepulsion: 8500,
      idealEdgeLength: 100,
      animate: false,
    })
    .run();
  graph.fit(visible, 36);
}

function applyOperatorView({ relayout = false } = {}) {
  if (!graph) return;
  hideDocker();
  applyGrouping();
  applyResourceSizing();
  applyBandwidthSizing();
  if (relayout) fitAndLayout();
}

async function loadTelemetry() {
  try {
    telemetry = await fetchJson("/api/topology-telemetry");
    const resources = Object.keys(telemetry?.resources || {}).length;
    const flow = finite(telemetry?.network_flow?.pfsense_bytes_per_second);
    operatorStatus(
      `Telemetry: ${telemetry.state} · ${resources} container resource series${flow != null ? ` · pfSense ${Math.round(flow)} B/s via Akvorado` : ""}`,
      telemetry.state === "healthy" ? "ok" : "warn",
    );
  } catch (caught) {
    telemetry = null;
    operatorStatus(`Topology telemetry unavailable: ${caught.message}`, "warn");
  }
  applyResourceSizing();
  applyBandwidthSizing();
}

async function loadTopologyMetadata() {
  try {
    topology = await fetchJson("/api/homelab-topology");
  } catch {
    topology = null;
  }
}

function installControls() {
  document
    .getElementById("topology-hide-docker")
    ?.addEventListener("change", () => {
      applyOperatorView({ relayout: true });
    });
  document
    .getElementById("topology-group-by")
    ?.addEventListener("change", () => {
      applyOperatorView({ relayout: true });
    });
  document
    .getElementById("topology-node-sizing")
    ?.addEventListener("change", () => {
      applyResourceSizing();
    });
  document
    .getElementById("topology-edge-sizing")
    ?.addEventListener("change", () => {
      applyBandwidthSizing();
    });
}

async function initialize(capturedGraph) {
  if (graph) return;
  graph = capturedGraph;
  installStyles();
  installControls();
  await Promise.all([loadTopologyMetadata(), loadTelemetry()]);
  applyOperatorView();
}

const existing = window.__nablaTopologyGraph;
if (existing) void initialize(existing);
else {
  document.addEventListener(
    "nabla-topology-graph-ready",
    (event) => void initialize(event.detail?.graph),
    { once: true },
  );
}
