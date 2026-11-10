import { homepageCadence } from "./home-cost-policy.js";
import {
  alignedHistoryCorrelation,
  appendObservation,
  pearsonCorrelation,
  projectAggregateNetworkFlow,
  projectAppliancePulse,
  projectFleet,
  projectLatency,
  projectProbeMatrix,
  projectProbes,
  projectPrometheusHistory,
  projectResources,
  projectResourceHeatmap,
  projectSecurity,
  projectServiceFootprint,
  sparklinePath,
  temporalSparklinePath,
} from "./home-operations-model.js";
import {
  discardPublicDirectory,
  persistPublicDirectory,
  restorePublicDirectory,
} from "./home-public-cache.js";

const ROOT = document.getElementById("home-operations");
const HOME_RUNTIME = ROOT?.dataset?.runtimeMode || "local";
const INITIAL_CADENCE = homepageCadence(HOME_RUNTIME, false);
// Limit idle anonymous polling on FastAPI Cloud; manual refresh remains available.
const CLOUD_RUNTIME = window.location?.hostname?.endsWith(".fastapicloud.dev") === true;
const INTERVAL_MS = CLOUD_RUNTIME ? 60000 : 30000;
const CLOUD_IDLE_POLL_PAUSE_MS = 5 * 60 * 1000;
let lastCloudInteractionAt = Date.now();
let cloudPollingPaused = false;

function cloudPollingIdle(now = Date.now()) {
  return CLOUD_RUNTIME && now - lastCloudInteractionAt >= CLOUD_IDLE_POLL_PAUSE_MS;
}
const SERIES = Object.create(null);
let CORRELATION_PAIRS = [];
let HISTORY_DATA = null;
let HISTORY_READ_AT = 0;
let HISTORY_WINDOW = "1h";
let LATEST_RESOURCE_TELEMETRY = null;
const HISTORY_RECHECK_MS = 120000;
const NS = "http://www.w3.org/2000/svg";
let active = false;
let refreshRequested = false;
let ownerSessionActive = false;
let warmupAttempts = 0;
let warmupTimer = null;
const WARMUP_DELAYS_MS = INITIAL_CADENCE.warmupDelaysMs;

function publicSessionCache() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function clearWarmupRetry() {
  if (warmupTimer !== null) clearTimeout(warmupTimer);
  warmupTimer = null;
}

function scheduleWarmupRetry() {
  clearWarmupRetry();
  // Five bounded fast retries, then return to normal periodic polling.
  if (warmupAttempts >= WARMUP_DELAYS_MS.length) {
    put(
      "home-retry-status",
      homepageCadence(HOME_RUNTIME, ownerSessionActive).pollEnabled
          ? "Actualisation périodique contrôlée"
          : "Mode Cloud économique · mise à jour au retour dans cet onglet",
    );
    return;
  }
  if (document.hidden || cloudPollingIdle()) return;
  const delay = WARMUP_DELAYS_MS[warmupAttempts];
  warmupAttempts += 1;
  put(
    "home-retry-status",
    "Nouvelle lecture automatique dans " + Math.round(delay / 1000) + " s",
  );
  warmupTimer = setTimeout(() => {
    warmupTimer = null;
    if (active) refreshRequested = true;
    else void refresh();
  }, delay);
}

function paintSessionDirectory() {
  const directory = restorePublicDirectory(publicSessionCache());
  if (!directory) return false;
  const projected = projectFleet(directory);
  if (!projected) return false;
  summaryCounts(projected);
  put(
    "home-fleet-source",
    "Inventaire public de cet onglet · états non vérifiés",
  );
  status("Inventaire provisoire · actualisation automatique", "unknown");
  return true;
}

function element(id) {
  return document.getElementById(id);
}

function put(id, value) {
  const node = element(id);
  if (node) node.textContent = value == null ? "—" : String(value);
}

function status(message, state = "unknown") {
  put("home-connection", message);
  const led = element("home-connection-led");
  if (led) led.dataset.state = state;
}

function summaryCounts({ total, counts, source, verified, boardState }) {
  for (const [field, value] of Object.entries({
    "home-services": total,
    "home-ok": counts.ok,
    "home-warn": counts.warn,
    "home-fail": counts.fail,
    "home-unknown": counts.unknown,
  }))
    put(field, value);
  put(
    "home-fleet-source",
    source +
      " · " +
      (verified
        ? "instantané vérifié"
        : "preuve " + boardState + " / non confirmée"),
  );
  const meter = element("home-fleet-meter");
  if (!meter) return;
  const parts = [];
  for (const kind of ["ok", "warn", "fail", "unknown"]) {
    const item = document.createElement("span");
    item.className = "op-meter-segment op-meter-segment-" + kind;
    item.style.width =
      (total > 0 ? (100 * counts[kind]) / total : 0).toFixed(2) + "%";
    item.title = kind + ": " + counts[kind];
    parts.push(item);
  }
  meter.replaceChildren(...parts);
  meter.setAttribute(
    "aria-label",
    total +
      " services ; " +
      Object.entries(counts)
        .map(([kind, value]) => kind + " " + value)
        .join(", "),
  );
}

function clearPublic() {
  for (const name of [
    "home-services",
    "home-ok",
    "home-warn",
    "home-fail",
    "home-unknown",
  ])
    put(name, "—");
  put("home-fleet-source", "Catalogue indisponible · aucune preuve");
  const meter = element("home-fleet-meter");
  meter?.replaceChildren();
  meter?.setAttribute(
    "aria-label",
    "Répartition inconnue · aucune preuve récente",
  );
}

function metric(id, value, digits, suffix = "") {
  put(
    id,
    typeof value === "number" && Number.isFinite(value)
      ? value.toFixed(digits) + suffix
      : "—",
  );
}

function observe(name, at, value, target, label) {
  const history = appendObservation(SERIES[name] || [], at, value);
  SERIES[name] = history;
  const node = element(target);
  if (!node) return;
  const path = sparklinePath(history);
  if (!path) {
    node.replaceChildren();
    if (node.classList.contains("op-chart")) {
      const empty = document.createElement("p");
      empty.className = "op-chart-empty";
      empty.textContent = "En attente de deux instantanés réels distincts.";
      node.append(empty);
    }
    node.setAttribute("aria-label", label + " : historique insuffisant");
    return;
  }
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 420 108");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    label + ", " + history.length + " mesures depuis l'ouverture de la page",
  );
  const grid = document.createElementNS(NS, "path");
  grid.setAttribute("d", "M0 54 L420 54");
  grid.setAttribute("class", "op-spark-grid");
  const trace = document.createElementNS(NS, "path");
  trace.setAttribute("d", path);
  trace.setAttribute("class", "op-spark-line");
  svg.append(grid, trace);
  node.replaceChildren(svg);
  node.setAttribute(
    "aria-label",
    label + " : " + history.length + " observations",
  );
}

function clearPrivate({ purge = false } = {}) {
  LATEST_RESOURCE_TELEMETRY = null;
  element("home-footprint-bars")?.replaceChildren();
  element("home-resource-heatmap")?.replaceChildren();
  put("home-resource-heatmap-source", "Aucune mesure privée vérifiée");
  put("home-footprint-source", "Mesures non confirmées");
  put(
    "home-footprint-note",
    "Barres relatives entre services observés, pas un pourcentage de capacité.",
  );
  put("home-pfsense-flow", "—");
  put("home-flow-source", "Flux non confirmés · Akvorado / Prometheus.");
  if (purge) {
    HISTORY_DATA = null;
    HISTORY_READ_AT = 0;
    CORRELATION_PAIRS = [];
    for (const key of Object.keys(SERIES)) delete SERIES[key];
  }
  for (const id of [
    "home-probes-history",
    "home-latency-history",
    "home-cpu-history",
    "home-memory-history",
    "home-network-history",
    "home-p95-history",
    "home-gatus-history",
    "home-correlation-chart",
  ])
    element(id)?.replaceChildren();
  metric("home-coverage", null, 1);
  metric("home-healthy-coverage", null, 1);
  metric("home-cpu", null, 3);
  metric("home-memory", null, 1);
  metric("home-network", null, 1);
  put("home-coverage-detail", "Aucune observation fraîche");
  element("home-probe-mosaic")?.replaceChildren();
  put("home-probe-mosaic-source", "Aucune sonde vérifiée");
  put("home-resource-source", "Prometheus / cAdvisor · indisponible");
  put("home-security-summary", "—");
  put("home-security-detail", "Contrôles non confirmés");
  element("home-security-checks")?.replaceChildren();
  put("home-history-status", "Historique non confirmé");
  put("home-p95", "—");
  put("home-gatus", "—");
  clearPulse("TrueNAS · aucun instantané");
}

const PULSE_FIELDS = [
  "home-pulse-load",
  "home-pulse-cpu",
  "home-pulse-memory",
  "home-pulse-network",
  "home-pulse-storage",
  "home-pulse-alerts",
  "home-pulse-apps",
];

function clearPulse(message) {
  for (const id of PULSE_FIELDS) put(id, "—");
  for (const id of [
    "home-pulse-load-detail",
    "home-pulse-cpu-detail",
    "home-pulse-memory-detail",
    "home-pulse-network-detail",
    "home-pulse-storage-detail",
    "home-pulse-alerts-detail",
    "home-pulse-apps-detail",
  ])
    put(id, "Non mesuré");
  for (const id of [
    "home-pulse-cpu-history",
    "home-pulse-memory-history",
    "home-pulse-network-history",
  ]) {
    element(id)?.replaceChildren();
  }
  put("home-pulse-source", message);
  put("home-pulse-impacts-summary", "Aucune interdépendance mesurée");
  element("home-pulse-impacts")?.replaceChildren();
  const led = element("home-pulse-led");
  if (led) led.dataset.state = "unknown";
}

function pulseSparkline(target, points, label) {
  const node = element(target);
  if (!node) return;
  if (points.length < 2) {
    node.replaceChildren();
    node.setAttribute("aria-label", label + " : série TrueNAS insuffisante");
    return;
  }
  const startMs = Date.parse(points[0].at);
  const endMs = Date.parse(points[points.length - 1].at);
  const path = temporalSparklinePath(points, {
    startMs,
    endMs,
    maxGapMs: 15 * 60000,
  });
  if (!path) {
    node.replaceChildren();
    return;
  }
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 420 108");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    label + " · " + points.length + " points TrueNAS",
  );
  const grid = document.createElementNS(NS, "path");
  grid.setAttribute("d", "M0 54 L420 54");
  grid.setAttribute("class", "op-spark-grid");
  const trace = document.createElementNS(NS, "path");
  trace.setAttribute("d", path);
  trace.setAttribute("class", "op-spark-line");
  svg.append(grid, trace);
  node.replaceChildren(svg);
}

function privatePulse(payload) {
  const pulse = projectAppliancePulse(payload);
  if (!pulse) {
    const state =
      typeof payload?.state === "string" ? payload.state : "inaccessible";
    clearPulse("API TrueNAS · " + state + " · aucune valeur supposée");
    return null;
  }
  const led = element("home-pulse-led");
  if (led) led.dataset.state = pulse.pressure;
  put(
    "home-pulse-source",
    "API TrueNAS " +
      (pulse.appliance.version || "") +
      " · " +
      pulse.observedAt +
      (pulse.partial ? " · partiel (" + pulse.errors.join(", ") + ")" : ""),
  );
  metric("home-pulse-load", pulse.appliance.loadPerCore, 2);
  put(
    "home-pulse-load-detail",
    pulse.appliance.load1 !== null && pulse.appliance.cores !== null
      ? "charge 1 min " +
          pulse.appliance.load1.toFixed(2) +
          " sur " +
          pulse.appliance.cores +
          " cœurs"
      : "system.info indisponible",
  );
  metric("home-pulse-cpu", pulse.cpu.busyPercent, 0, " %");
  put(
    "home-pulse-cpu-detail",
    pulse.cpu.state === "observed"
      ? "netdata · dernière heure"
      : pulse.cpu.state === "legend_unrecognized"
        ? "légende netdata non reconnue"
        : "série indisponible",
  );
  pulseSparkline("home-pulse-cpu-history", pulse.cpu.series, "CPU occupé %");
  metric("home-pulse-memory", pulse.memory.usedPercent, 0, " %");
  put(
    "home-pulse-memory-detail",
    pulse.memory.state === "observed"
      ? "utilisée / total netdata"
      : pulse.memory.state === "legend_unrecognized"
        ? "légende netdata non reconnue"
        : "série indisponible",
  );
  pulseSparkline(
    "home-pulse-memory-history",
    pulse.memory.series,
    "Mémoire utilisée %",
  );
  metric(
    "home-pulse-network",
    pulse.network.throughput,
    0,
    pulse.network.label ? " " + pulse.network.label : "",
  );
  const linksUp = pulse.network.interfaces
    .filter((row) => row.linkUp)
    .map((row) => row.name);
  put(
    "home-pulse-network-detail",
    pulse.network.observed
      ? linksUp.length
        ? "RX+TX " + linksUp.join(", ")
        : "aucun lien physique actif"
      : "interface.query indisponible",
  );
  pulseSparkline(
    "home-pulse-network-history",
    pulse.network.series,
    "Débit RX+TX",
  );
  metric("home-pulse-storage", pulse.storage.worstUsedPercent, 1, " %");
  put(
    "home-pulse-storage-detail",
    pulse.storage.observed
      ? pulse.storage.pools
          .map(
            (pool) =>
              pool.name +
              " " +
              pool.status +
              (pool.usedPercent !== null
                ? " " + pool.usedPercent.toFixed(0) + " %"
                : ""),
          )
          .join(" · ") || "aucun pool"
      : "pool.query indisponible",
  );
  put("home-pulse-alerts", pulse.alerts.active);
  put(
    "home-pulse-alerts-detail",
    pulse.alerts.observed
      ? Object.entries(pulse.alerts.byLevel)
          .map(([level, value]) => level + " " + value)
          .join(" · ") || "aucune alerte active"
      : "alert.list indisponible",
  );
  const counts = pulse.apps.counts;
  put("home-pulse-apps", pulse.apps.total);
  put(
    "home-pulse-apps-detail",
    pulse.apps.observed
      ? (counts.RUNNING || 0) +
          " RUNNING · " +
          (counts.STOPPED || 0) +
          " STOPPED · " +
          (counts.CRASHED || 0) +
          " CRASHED · " +
          (counts.DEPLOYING || 0) +
          " DEPLOYING"
      : "app.query indisponible",
  );
  const target = element("home-pulse-impacts");
  if (target) {
    target.replaceChildren(
      ...pulse.impacts.map((impact) => {
        const li = document.createElement("li");
        li.className = "op-check";
        const heading = document.createElement("div");
        heading.className = "op-check-heading";
        const label = document.createElement("strong");
        label.textContent = impact.from + " → " + impact.to;
        const badge = document.createElement("span");
        badge.className = "op-check-state op-check-state-" + impact.state;
        badge.textContent = impact.state.toUpperCase();
        heading.append(label, badge);
        const detail = document.createElement("p");
        detail.textContent =
          impact.evidence +
          (impact.linked.length ? " · " + impact.linked.join(", ") : "");
        li.append(heading, detail);
        return li;
      }),
    );
  }
  put(
    "home-pulse-impacts-summary",
    pulse.impacts.length +
      " associations du même instantané · pression " +
      pulse.pressure.toUpperCase() +
      " · aucune causalité déduite",
  );
  return pulse;
}

function renderProbeMatrix(board) {
  const target = element("home-probe-mosaic");
  if (!target) return;
  target.replaceChildren();
  const matrix = projectProbeMatrix(board);
  if (!matrix || matrix.tiles.length === 0) {
    put("home-probe-mosaic-source", "Aucune donnée de sonde récente");
    return;
  }
  put(
    "home-probe-mosaic-source",
    matrix.count +
      " sondes dans l'instantané · " +
      matrix.tiles.length +
      " affichées" +
      (matrix.truncated ? " · " + matrix.truncated + " masquées" : ""),
  );
  for (const tile of matrix.tiles) {
    const li = document.createElement("li");
    li.className =
      "op-probe-tile op-probe-tile-" +
      tile.state +
      (tile.evidence === "stale" ? " op-probe-tile-stale" : "");
    const detail =
      tile.scope +
      " / " +
      tile.id +
      " · " +
      (tile.evidence === "observed"
        ? tile.state
        : tile.evidence + " / état inconnu");
    li.setAttribute("role", "img");
    li.setAttribute("aria-label", detail);
    li.title = detail;
    target.append(li);
  }
}

function privateBoard(board) {
  renderProbeMatrix(board);
  const probes = projectProbes(board);
  if (probes) {
    metric("home-coverage", probes.coverage, 1, " %");
    metric("home-healthy-coverage", probes.healthyCoverage, 1, " %");
    put(
      "home-coverage-detail",
      probes.known +
        "/" +
        probes.eligible +
        " preuves observées · " +
        probes.unobserved +
        " absentes",
    );
    observe(
      "coverage",
      probes.observedAt,
      probes.coverage,
      "home-probes-history",
      "Couverture des sondes en pourcentage",
    );
  } else {
    metric("home-coverage", null, 1);
    metric("home-healthy-coverage", null, 1);
    put("home-coverage-detail", "Aucune preuve fraîche disponible");
  }
  const latency = projectLatency(board);
  if (latency) {
    observe(
      "latency",
      latency.observedAt,
      latency.valueMs,
      "home-latency-history",
      "Durée des sondes HTTP en ms",
    );
  }
  const security = projectSecurity(board);
  const target = element("home-security-checks");
  if (!security || !target) {
    put("home-security-summary", "—");
    put("home-security-detail", "Pas de preuve actuelle");
    target?.replaceChildren();
    return latency;
  }
  const policy = security.policyCounts;
  put(
    "home-security-summary",
    security.policyObserved
      ? security.policyObserved + " politiques"
      : "Non mesuré",
  );
  put(
    "home-security-detail",
    security.policyObserved
      ? policy.ok + " OK · " + policy.warn + " WARN · " + policy.fail + " FAIL"
      : "Aucun contrôle d'exposition qualifié dans cet instantané",
  );
  const entries = security.checks.map((check) => {
    const li = document.createElement("li");
    li.className = "op-check";
    const heading = document.createElement("div");
    heading.className = "op-check-heading";
    const label = document.createElement("strong");
    label.textContent = check.label;
    const badge = document.createElement("span");
    badge.className = "op-check-state op-check-state-" + check.state;
    badge.textContent = check.state.toUpperCase();
    heading.append(label, badge);
    const detail = document.createElement("p");
    detail.textContent =
      check.description + (check.category ? " · " + check.category : "");
    li.append(heading, detail);
    return li;
  });
  target.replaceChildren(...entries);
  return latency;
}

function renderResourceHeatmap(snapshot) {
  const target = element("home-resource-heatmap");
  if (!target) return;
  target.replaceChildren();
  const matrix = projectResourceHeatmap(snapshot);
  if (!matrix || matrix.rows.length === 0) {
    put("home-resource-heatmap-source", "Mesures absentes ou périmées · aucune valeur supposée");
    return;
  }
  put(
    "home-resource-heatmap-source",
    matrix.measuredServices + "/" + matrix.declaredServices +
      " services avec au moins une mesure · " + matrix.observedAt +
      (matrix.truncated ? " · " + matrix.truncated + " autres non affichés" : ""),
  );
  const header = document.createElement("div");
  header.className = "op-heatmap-row op-heatmap-head";
  const first = document.createElement("span");
  first.textContent = "Service";
  header.append(first);
  for (const dimension of matrix.dimensions) {
    const title = document.createElement("span");
    title.textContent = dimension.label;
    title.title = dimension.label + " · " + dimension.unit;
    header.append(title);
  }
  target.append(header);
  for (const row of matrix.rows) {
    const line = document.createElement("div");
    line.className = "op-heatmap-row";
    const name = document.createElement("strong");
    name.className = "op-heatmap-name";
    name.textContent = row.name;
    name.title = row.name;
    line.append(name);
    for (const cell of row.cells) {
      const tile = document.createElement("span");
      tile.className = "op-heatmap-cell";
      if (cell.value === null) {
        tile.classList.add("op-heatmap-missing");
        tile.textContent = "—";
        tile.setAttribute("aria-label", row.name + " · " + cell.label + " : non mesuré");
      } else {
        const displayed = cell.value.toLocaleString("fr-FR", {
          maximumFractionDigits: cell.value < 1 ? 3 : 1,
        }) + " " + cell.unit;
        tile.style.setProperty("--heat-alpha", String(0.10 + (cell.relativePercent ?? 0) * 0.0066));
        tile.textContent = displayed;
        tile.setAttribute(
          "aria-label",
          row.name + " · " + cell.label + " : " + displayed +
            " · intensité relative, pas capacité",
        );
      }
      line.append(tile);
    }
    target.append(line);
  }
}

function renderServiceFootprint(snapshot) {
  // Never expose this projection outside the already authenticated OWNER panel.
  const list = element("home-footprint-bars");
  if (!list) return;
  list.replaceChildren();
  const selected = element("home-footprint-metric")?.value || "memory_bytes";
  const footprint = projectServiceFootprint(snapshot, selected);
  if (!footprint || !footprint.rows.length) {
    const empty = document.createElement("li");
    empty.className = "op-resource-empty";
    empty.textContent =
      "Aucune mesure récente pour cette ressource (absence ≠ zéro).";
    list.append(empty);
    put("home-footprint-source", "Télémétrie indisponible ou mesure absente");
    put(
      "home-footprint-note",
      selected === "fs_bytes"
        ? "FS conteneur uniquement ; aucun chiffre de datasets ZFS ou PVC."
        : "Aucune capacité, utilisation ou indisponibilité inventée.",
    );
  } else {
    put(
      "home-footprint-source",
      footprint.measured +
        "/" +
        footprint.declared +
        " services mesurés · " +
        footprint.observedAt +
        " · 8 premiers",
    );
    put(
      "home-footprint-note",
      footprint.storageScope ||
        "Largeur relative au plus grand service mesuré : ce n'est pas un % de quota CPU/RAM.",
    );
    for (const row of footprint.rows) {
      const item = document.createElement("li");
      item.className = "op-resource-item";
      const heading = document.createElement("div");
      heading.className = "op-resource-label";
      const label = document.createElement("strong");
      label.textContent = row.name;
      const measure = document.createElement("data");
      measure.textContent =
        row.value.toLocaleString("fr-FR", {
          maximumFractionDigits: row.value < 1 ? 3 : 1,
        }) +
        " " +
        footprint.unit;
      heading.append(label, measure);
      const track = document.createElement("div");
      track.className = "op-resource-track";
      track.setAttribute("role", "img");
      track.setAttribute(
        "aria-label",
        row.name +
          " : " +
          measure.textContent +
          " · barre relative, pas capacité",
      );
      const bar = document.createElement("span");
      bar.className = "op-resource-fill";
      bar.style.width = row.relativePercent.toFixed(2) + "%";
      track.append(bar);
      item.append(heading, track);
      list.append(item);
    }
  }
  const flow = projectAggregateNetworkFlow(snapshot);
  put(
    "home-pfsense-flow",
    flow?.kiBs == null
      ? "—"
      : flow.kiBs.toLocaleString("fr-FR", { maximumFractionDigits: 1 }) +
          " KiB/s",
  );
  put(
    "home-flow-source",
    !flow
      ? "Absence de preuve réseau récente"
      : flow.kiBs === null
        ? "Débit pfSense absent · aucune valeur supposée"
        : (flow.collectorConfirmed
            ? "Collecte Akvorado confirmée"
            : "Collecte Akvorado non confirmée") +
          " · flux pfSense agrégé, non attribué",
  );
}

function privateResources(snapshot) {
  LATEST_RESOURCE_TELEMETRY = snapshot;
  renderServiceFootprint(snapshot);
  renderResourceHeatmap(snapshot);
  const resources = projectResources(snapshot);
  if (!resources) {
    put(
      "home-resource-source",
      "Prometheus / cAdvisor · aucune donnée fraîche",
    );
    for (const id of ["home-cpu", "home-memory", "home-network"]) put(id, "—");
    return null;
  }
  put("home-resource-source", resources.source + " · " + resources.observedAt);
  metric("home-cpu", resources.cpuCores, 3, " c");
  metric("home-memory", resources.memoryMiB, 1, " MiB");
  metric("home-network", resources.networkKiBs, 1, " KiB/s");
  for (const [name, at, value, target, label] of [
    [
      "cpu",
      resources.observedAt,
      resources.cpuCores,
      "home-cpu-history",
      "CPU en cœurs",
    ],
    [
      "memory",
      resources.observedAt,
      resources.memoryMiB,
      "home-memory-history",
      "Mémoire en MiB",
    ],
    [
      "network",
      resources.observedAt,
      resources.networkKiBs,
      "home-network-history",
      "Débit réseau KiB/s",
    ],
  ])
    observe(name, at, value, target, label);
  return resources;
}

function correlation() {
  const node = element("home-correlation-chart");
  if (!node) return;
  const r = pearsonCorrelation(CORRELATION_PAIRS);
  if (r === null) {
    put(
      "home-correlation-summary",
      CORRELATION_PAIRS.length +
        "/6 mesures synchronisées · corrélation inconnue",
    );
    const empty = document.createElement("p");
    empty.className = "op-chart-empty";
    empty.textContent = "Six paires CPU/HTTP valides sont nécessaires.";
    node.replaceChildren(empty);
    node.setAttribute("aria-label", "Corrélation non mesurée");
    return;
  }
  put(
    "home-correlation-summary",
    "r = " +
      r.toFixed(2) +
      " · n = " +
      CORRELATION_PAIRS.length +
      " paires · association, pas causalité",
  );
  const width = 420,
    height = 108,
    pad = 18;
  const xs = CORRELATION_PAIRS.map((point) => point.cpu);
  const ys = CORRELATION_PAIRS.map((point) => point.httpMs);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs);
  const minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const rx = Math.max(0.00001, maxX - minX);
  const ry = Math.max(0.00001, maxY - minY);
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 420 108");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    "CPU en cœurs contre durée HTTP en ms, " +
      CORRELATION_PAIRS.length +
      " observations, corrélation " +
      r.toFixed(2),
  );
  const axes = document.createElementNS(NS, "path");
  axes.setAttribute("d", "M18 10 L18 90 L410 90");
  axes.setAttribute("class", "op-scatter-axis");
  svg.append(axes);
  for (const point of CORRELATION_PAIRS) {
    const dot = document.createElementNS(NS, "circle");
    dot.setAttribute(
      "cx",
      String(pad + ((point.cpu - minX) / rx) * (width - 2 * pad)),
    );
    dot.setAttribute(
      "cy",
      String(height - pad - ((point.httpMs - minY) / ry) * (height - 2 * pad)),
    );
    dot.setAttribute("r", "3.5");
    dot.setAttribute("class", "op-scatter-dot");
    svg.append(dot);
  }
  node.replaceChildren(svg);
  node.setAttribute("aria-label", "Corrélation CPU / HTTP : " + r.toFixed(2));
}

function renderSeriesHistory(target, points, label, history) {
  const node = element(target);
  if (!node) return;
  const path = temporalSparklinePath(points, {
    startMs: history.start * 1000,
    endMs: history.end * 1000,
    maxGapMs: history.step * 2000,
  });
  if (!path) {
    node.replaceChildren();
    const fallback = document.createElement("p");
    fallback.className = "op-chart-empty";
    fallback.textContent = "Pas assez d'échantillons Prometheus.";
    node.append(fallback);
    node.setAttribute("aria-label", label + " : preuve indisponible");
    return;
  }
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 420 108");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  const first = points[0].at,
    last = points[points.length - 1].at;
  svg.setAttribute("aria-label", label + " de " + first + " à " + last);
  const grid = document.createElementNS(NS, "path");
  grid.setAttribute("d", "M0 54 L420 54");
  grid.setAttribute("class", "op-spark-grid");
  const trace = document.createElementNS(NS, "path");
  trace.setAttribute("d", path);
  trace.setAttribute("class", "op-spark-line");
  svg.append(grid, trace);
  node.replaceChildren(svg);
  node.setAttribute(
    "aria-label",
    label +
      " · " +
      points.length +
      " mesures Prometheus · " +
      first.slice(0, 16) +
      " → " +
      last.slice(0, 16),
  );
}

function renderPrometheusHistory(history) {
  const fields = history.fields;
  const formats = [
    ["cpu_cores", "home-cpu-history", "CPU en cœurs", 1],
    ["memory_bytes", "home-memory-history", "Mémoire active MiB", 1 / 1048576],
    [
      "network_bytes_per_second",
      "home-network-history",
      "Débit RX+TX KiB/s",
      1 / 1024,
    ],
    ["http_p95_ms", "home-p95-history", "Latence applicative p95 ms", 1],
    [
      "gatus_availability_percent",
      "home-gatus-history",
      "Disponibilité Gatus %",
      1,
    ],
  ];
  for (const [field, target, label, scale] of formats) {
    const points = (fields[field] || []).map((row) => ({
      at: row.at,
      value: row.value * scale,
    }));
    renderSeriesHistory(target, points, label, history);
  }
  const p95 = fields.http_p95_ms || [];
  const gatus = fields.gatus_availability_percent || [];
  const currentValue = (points) =>
    points.length &&
    history.end * 1000 - Date.parse(points.at(-1).at) <= history.step * 2000
      ? points.at(-1).value
      : null;
  metric("home-p95", currentValue(p95), 1, " ms");
  metric("home-gatus", currentValue(gatus), 1, " %");
  const alignment = alignedHistoryCorrelation(history);
  CORRELATION_PAIRS = alignment.pairs;
  correlation();
  put(
    "home-history-status",
    history.window +
      " · Prometheus · " +
      history.availableSeries +
      "/5 séries" +
      (history.partial ? " · partiel" : "") +
      " · dernier point " +
      new Date(history.end * 1000).toISOString(),
  );
}

async function updatePrometheusHistory({ force = false } = {}) {
  if (
    !force &&
    HISTORY_DATA &&
    Date.now() - HISTORY_READ_AT < HISTORY_RECHECK_MS
  ) {
    renderPrometheusHistory(HISTORY_DATA);
    return;
  }
  put(
    "home-history-status",
    "Lecture de l'historique Prometheus " + HISTORY_WINDOW + "…",
  );
  const requestedWindow = HISTORY_WINDOW;
  try {
    const payload = await fetchJSON(
      "/api/home/metrics/history?window=" + requestedWindow,
      11500,
    );
    if (requestedWindow !== HISTORY_WINDOW) return;
    const history = projectPrometheusHistory(payload);
    HISTORY_READ_AT = Date.now();
    HISTORY_DATA = history;
    if (!history) {
      put(
        "home-history-status",
        "Historique indisponible ou non configuré · aucune valeur simulée",
      );
      return;
    }
    renderPrometheusHistory(history);
  } catch {
    if (requestedWindow !== HISTORY_WINDOW) return;
    HISTORY_DATA = null;
    HISTORY_READ_AT = Date.now();
    put(
      "home-history-status",
      "Historique inaccessible · aucune mesure supposée",
    );
  }
}

async function fetchJSON(url, timeout = 6500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("http_" + response.status);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function refresh() {
  if (active || document.hidden || !ROOT) return;
  clearWarmupRetry();
  active = true;
  let retryWarmup = false;
  const button = element("home-refresh");
  if (button) button.disabled = true;
  status("Lecture des observations mises en cache…");
  try {
    // A slow owner session check must not delay public service cards.
    const publicRequest = fetchJSON("/api/ui/services").then(
      (value) => ({ status: "fulfilled", value }),
      (reason) => ({ status: "rejected", reason }),
    );
    const sessionRequest = fetchJSON("/api/ui/session", 3500).then(
      (value) => ({ status: "fulfilled", value }),
      (reason) => ({ status: "rejected", reason }),
    );
    const publicResult = await publicRequest;
    const fleet =
      publicResult.status === "fulfilled"
        ? projectFleet(publicResult.value)
        : null;
    const publicDenied =
      publicResult.status === "rejected" &&
      ["http_401", "http_403", "http_404"].includes(
        publicResult.reason?.message,
      );
    if (fleet) {
      persistPublicDirectory(publicSessionCache(), publicResult.value);
      summaryCounts(fleet);
      retryWarmup = !fleet.verified;
      status(
        fleet.verified
          ? "Catalogue vérifié · instantané public"
          : HOME_RUNTIME === "fastapi_cloud"
            ? "Inventaire public · sondes à exécuter sur demande"
            : "Sondes en préparation · nouvelle lecture automatique",
        fleet.verified ? "ok" : "unknown",
      );
      if (fleet.verified) {
        put(
      "home-retry-status",
      homepageCadence(HOME_RUNTIME, ownerSessionActive).pollEnabled
          ? "Actualisation périodique contrôlée"
          : "Mode Cloud économique · mise à jour au retour dans cet onglet",
    );
      }
    } else if (publicDenied) {
      discardPublicDirectory(publicSessionCache());
      clearPublic();
      warmupAttempts = WARMUP_DELAYS_MS.length;
      put("home-retry-status", "Accès public indisponible");
      status("Inventaire public désactivé ou non autorisé", "unknown");
    } else {
      // Cached directory contains names/kinds ONLY. Never reuse an old OK.
      const restored = paintSessionDirectory();
      if (!restored) clearPublic();
      retryWarmup = true;
      status(
        "Catalogue temporairement indisponible · nouvelle tentative automatique",
        "warn",
      );
    }
    const sessionResult = await sessionRequest;
    if (sessionResult.status === "rejected") retryWarmup = true;

    const owner =
      sessionResult.status === "fulfilled" &&
      sessionResult.value?.authenticated === true;
    ownerSessionActive = owner;
    element("home-locked").hidden = owner;
    element("home-operator-detail").hidden = !owner;
    if (!owner) {
      put("home-observed", "Mode public · détails réservés au propriétaire");
      clearPrivate({ purge: true });
    } else {
      const [boardResult, telemetryResult, pulseResult] =
        await Promise.allSettled([
          fetchJSON("/api/health-board", 8000),
          fetchJSON("/api/topology-telemetry", 6000),
          fetchJSON("/api/home/appliance/pulse", 10000),
        ]);
      clearPrivate();
      privatePulse(
        pulseResult.status === "fulfilled" ? pulseResult.value : null,
      );
      let latency = null;
      if (
        boardResult.status === "fulfilled" &&
        boardResult.value?.state === "fresh"
      ) {
        latency = privateBoard(boardResult.value);
      } else {
        retryWarmup = true;
        status(
          "Diagnostics détaillés absents ou périmés · nouvelle lecture automatique",
          "warn",
        );
      }
      const resources =
        telemetryResult.status === "fulfilled"
          ? privateResources(telemetryResult.value)
          : null;
      await updatePrometheusHistory();
      const board =
        boardResult.status === "fulfilled" ? boardResult.value : null;
      put(
        "home-observed",
        board?.generated_at && board?.state === "fresh"
          ? "Mesuré : " + board.generated_at
          : "Preuve propriétaire indisponible · aucune santé supposée",
      );
    }
  } catch {
    if (!paintSessionDirectory()) clearPublic();
    clearPrivate({ purge: true });
    retryWarmup = true;
    status(
      "Impossible de confirmer les mesures · nouvel essai automatique",
      "unknown",
    );
  } finally {
    if (button) button.disabled = false;
    active = false;
    if (retryWarmup) {
      scheduleWarmupRetry();
    } else {
      warmupAttempts = 0;
      clearWarmupRetry();
      put(
      "home-retry-status",
      homepageCadence(HOME_RUNTIME, ownerSessionActive).pollEnabled
          ? "Actualisation périodique contrôlée"
          : "Mode Cloud économique · mise à jour au retour dans cet onglet",
    );
    }
    if (refreshRequested && !document.hidden) {
      refreshRequested = false;
      queueMicrotask(() => void refresh());
    }
  }
}

if (ROOT) {
  // Before the first network response, show only public service names with
  // UNKNOWN statuses. Session storage never contains probe health or tokens.
  paintSessionDirectory();
  element("home-refresh")?.addEventListener("click", () => {
    HISTORY_READ_AT = 0;
    warmupAttempts = 0;
    void refresh();
  });
  element("home-footprint-metric")?.addEventListener("change", () => {
    if (!element("home-operator-detail")?.hidden && LATEST_RESOURCE_TELEMETRY) {
      renderServiceFootprint(LATEST_RESOURCE_TELEMETRY);
    }
  });
  element("home-history-window")?.addEventListener("change", (event) => {
    const selection = event.target.value;
    if (!["1h", "24h", "7d"].includes(selection)) return;
    HISTORY_WINDOW = selection;
    HISTORY_DATA = null;
    HISTORY_READ_AT = 0;
    if (active) refreshRequested = true;
    else void refresh();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearWarmupRetry();
    } else {
      lastCloudInteractionAt = Date.now();
      cloudPollingPaused = false;
      warmupAttempts = 0;
      if (active) refreshRequested = true;
      else void refresh();
    }
  });
  if (CLOUD_RUNTIME) {
    const resumeCloudPolling = () => {
      const paused = cloudPollingPaused || cloudPollingIdle();
      lastCloudInteractionAt = Date.now();
      if (!paused || document.hidden) return;
      cloudPollingPaused = false;
      put("home-retry-status", "Reprise de la surveillance automatique");
      if (active) refreshRequested = true;
      else void refresh();
    };
    document.addEventListener("pointerdown", resumeCloudPolling, { passive: true });
    document.addEventListener("keydown", resumeCloudPolling);
  }
  setInterval(() => {
    if (document.hidden) return;
    if (cloudPollingIdle()) {
      if (!cloudPollingPaused) {
        cloudPollingPaused = true;
        clearWarmupRetry();
        put("home-retry-status", "Surveillance en pause · inactivité Cloud");
      }
      return;
    }
    // Anonymous FastAPI Cloud visitors never poll (PR #405); owners keep #406's idle pause.
    if (homepageCadence(HOME_RUNTIME, ownerSessionActive).pollEnabled) void refresh();
  }, INTERVAL_MS);
  void refresh();
}
