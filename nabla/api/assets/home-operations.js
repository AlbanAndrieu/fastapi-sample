import {
  appendObservation,
  projectFleet,
  projectLatency,
  projectProbes,
  projectResources,
  projectSecurity,
  sparklinePath,
} from "./home-operations-model.js";

const ROOT = document.getElementById("home-operations");
const INTERVAL_MS = 30000;
const SERIES = Object.create(null);
const NS = "http://www.w3.org/2000/svg";
let active = false;

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
    "home-services": total, "home-ok": counts.ok,
    "home-warn": counts.warn, "home-fail": counts.fail,
    "home-unknown": counts.unknown,
  })) put(field, value);
  put("home-fleet-source", source + " · " +
    (verified ? "instantané vérifié" : "preuve " + boardState + " / non confirmée"));
  const meter = element("home-fleet-meter");
  if (!meter) return;
  const parts = [];
  for (const kind of ["ok", "warn", "fail", "unknown"]) {
    const item = document.createElement("span");
    item.className = "op-meter-segment op-meter-segment-" + kind;
    item.style.width = (total > 0 ? 100 * counts[kind] / total : 0).toFixed(2) + "%";
    item.title = kind + ": " + counts[kind];
    parts.push(item);
  }
  meter.replaceChildren(...parts);
  meter.setAttribute(
    "aria-label",
    total + " services ; " +
    Object.entries(counts).map(([kind, value]) => kind + " " + value).join(", "),
  );
}

function clearPublic() {
  for (const name of [
    "home-services", "home-ok", "home-warn", "home-fail", "home-unknown",
  ]) put(name, "—");
  put("home-fleet-source", "Catalogue indisponible · aucune preuve");
  element("home-fleet-meter")?.replaceChildren();
}

function metric(id, value, digits, suffix = "") {
  put(id, typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits) + suffix : "—");
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
  svg.setAttribute("aria-label", label + ", " + history.length +
    " mesures depuis l'ouverture de la page");
  const grid = document.createElementNS(NS, "path");
  grid.setAttribute("d", "M0 54 L420 54");
  grid.setAttribute("class", "op-spark-grid");
  const trace = document.createElementNS(NS, "path");
  trace.setAttribute("d", path);
  trace.setAttribute("class", "op-spark-line");
  svg.append(grid, trace);
  node.replaceChildren(svg);
  node.setAttribute("aria-label", label + " : " + history.length + " observations");
}

function clearPrivate() {
  metric("home-coverage", null, 1);
  metric("home-healthy-coverage", null, 1);
  metric("home-cpu", null, 3);
  metric("home-memory", null, 1);
  metric("home-network", null, 1);
  put("home-coverage-detail", "Aucune observation fraîche");
  put("home-resource-source", "Prometheus / cAdvisor · indisponible");
  put("home-security-summary", "—");
  put("home-security-detail", "Contrôles non confirmés");
  element("home-security-checks")?.replaceChildren();
}

function privateBoard(board) {
  const probes = projectProbes(board);
  if (probes) {
    metric("home-coverage", probes.coverage, 1, " %");
    metric("home-healthy-coverage", probes.healthyCoverage, 1, " %");
    put("home-coverage-detail", probes.known + "/" + probes.eligible +
      " preuves observées · " + probes.unobserved + " absentes");
    observe("coverage", probes.observedAt, probes.coverage,
      "home-probes-history", "Couverture des sondes en pourcentage");
  } else {
    metric("home-coverage", null, 1);
    metric("home-healthy-coverage", null, 1);
    put("home-coverage-detail", "Aucune preuve fraîche disponible");
  }
  const latency = projectLatency(board);
  if (latency) {
    observe("latency", latency.observedAt, latency.valueMs,
      "home-latency-history", "Durée des sondes HTTP en ms");
  }
  const security = projectSecurity(board);
  const target = element("home-security-checks");
  if (!security || !target) {
    put("home-security-summary", "—");
    put("home-security-detail", "Pas de preuve actuelle");
    target?.replaceChildren();
    return;
  }
  const policy = security.policyCounts;
  put("home-security-summary", security.policyObserved ?
    security.policyObserved + " politiques" : "Non mesuré");
  put("home-security-detail", security.policyObserved ?
    policy.ok + " OK · " + policy.warn + " WARN · " + policy.fail + " FAIL" :
    "Aucun contrôle d'exposition qualifié dans cet instantané");
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
    detail.textContent = check.description +
      (check.category ? " · " + check.category : "");
    li.append(heading, detail);
    return li;
  });
  target.replaceChildren(...entries);
}

function privateResources(snapshot) {
  const resources = projectResources(snapshot);
  if (!resources) {
    put("home-resource-source", "Prometheus / cAdvisor · aucune donnée fraîche");
    for (const id of ["home-cpu", "home-memory", "home-network"]) put(id, "—");
    return;
  }
  put("home-resource-source", resources.source + " · " + resources.observedAt);
  metric("home-cpu", resources.cpuCores, 3, " c");
  metric("home-memory", resources.memoryMiB, 1, " MiB");
  metric("home-network", resources.networkKiBs, 1, " KiB/s");
  for (const [name, at, value, target, label] of [
    ["cpu", resources.observedAt, resources.cpuCores, "home-cpu-history", "CPU en cœurs"],
    ["memory", resources.observedAt, resources.memoryMiB, "home-memory-history", "Mémoire en MiB"],
    ["network", resources.observedAt, resources.networkKiBs, "home-network-history", "Débit réseau KiB/s"],
  ]) observe(name, at, value, target, label);
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
  active = true;
  const button = element("home-refresh");
  if (button) button.disabled = true;
  status("Lecture des observations mises en cache…");
  try {
  const [publicResult, sessionResult] = await Promise.allSettled([
    fetchJSON("/api/ui/services"),
    fetchJSON("/api/ui/session", 3500),
  ]);
  const fleet = publicResult.status === "fulfilled"
    ? projectFleet(publicResult.value) : null;
  if (fleet) {
    summaryCounts(fleet);
    status(fleet.verified ? "Catalogue vérifié" :
      "Catalogue disponible, preuves périmées", fleet.verified ? "ok" : "warn");
  } else {
    clearPublic();
    status("Catalogue indisponible · état inconnu", "unknown");
  }

  const owner = sessionResult.status === "fulfilled" &&
    sessionResult.value?.authenticated === true;
  element("home-locked").hidden = owner;
  element("home-operator-detail").hidden = !owner;
  if (!owner) {
    put("home-observed", "Mode public · détails réservés au propriétaire");
    clearPrivate();
  } else {
    const [boardResult, telemetryResult] = await Promise.allSettled([
      fetchJSON("/api/health-board", 8000),
      fetchJSON("/api/topology-telemetry", 6000),
    ]);
    clearPrivate();
    if (boardResult.status === "fulfilled" &&
        boardResult.value?.state === "fresh") {
      privateBoard(boardResult.value);
    } else {
      status("Diagnostics détaillés absents ou périmés", "warn");
    }
    if (telemetryResult.status === "fulfilled") {
      privateResources(telemetryResult.value);
    }
    const board = boardResult.status === "fulfilled" ? boardResult.value : null;
    put("home-observed", board?.generated_at && board?.state === "fresh" ?
      "Mesuré : " + board.generated_at :
      "Preuve propriétaire indisponible · aucune santé supposée");
  }
  } catch {
    clearPublic();
    clearPrivate();
    status("Impossible de confirmer les mesures", "unknown");
  } finally {
    if (button) button.disabled = false;
    active = false;
  }
}

if (ROOT) {
  element("home-refresh")?.addEventListener("click", () => void refresh());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void refresh();
  });
  setInterval(() => { if (!document.hidden) void refresh(); }, INTERVAL_MS);
  void refresh();
}
