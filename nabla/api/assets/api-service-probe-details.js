import { fetchHealthBoard } from "./api-health-board.js";

const ROW_SELECTOR = ".health-row[data-service-filter-target]";
const TICK_MS = 1000;

let latestSnapshot = null;
let ticker = null;
let scheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value), window.location.href).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function checkMatchesRow(check, row) {
  if (!check || !row) return false;
  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const ids = [check.id, check.service_id, check.serviceId]
    .map(normalize)
    .filter(Boolean);
  if (key && ids.includes(key)) return true;
  const names = [check.name, check.display_label]
    .map(normalize)
    .filter(Boolean);
  if (name && names.includes(name)) return true;
  const rowHost = hostOf(row.dataset.serviceUrl);
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  return [check.url, check.tunnel_url, check.tunnelUrl, ...aliases]
    .map(hostOf)
    .filter(Boolean)
    .includes(rowHost);
}

function findCheck(collection, row) {
  if (!collection) return null;
  const direct = collection[row.dataset.serviceKey];
  if (direct) return direct;
  const values = Array.isArray(collection)
    ? collection
    : Object.values(collection);
  return values.find((check) => checkMatchesRow(check, row)) || null;
}

function observedAt(check) {
  for (const value of [
    check?.probe_observed_at,
    check?.direct_probe_observed_at,
    check?.internal_probe_observed_at,
    check?.observed_at,
    check?.last_success_at,
  ]) {
    if (!value) continue;
    const timestamp = Date.parse(String(value));
    if (Number.isFinite(timestamp)) return timestamp;
  }
  return null;
}

function ageSeconds(check) {
  const timestamp = observedAt(check);
  if (timestamp != null) {
    return Math.max(0, (Date.now() - timestamp) / 1000);
  }
  for (const value of [
    check?.probe_age_seconds,
    check?.direct_probe_age_seconds,
    check?.internal_probe_age_seconds,
    check?.observation_age_seconds,
    check?.cache_age_seconds,
    check?.age_seconds,
  ]) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return Math.max(0, numeric);
  }
  return null;
}

function humanSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return null;
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${minutes.toFixed(minutes < 10 ? 1 : 0)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

function pendingState(check, snapshot) {
  if (check?.refreshing === true || check?.pending === true) return true;
  if (snapshot?.refreshing !== true) return false;
  const interval = Number(check?.probe_interval_seconds);
  const age = ageSeconds(check);
  if (!Number.isFinite(interval) || interval <= 0 || age == null) return true;
  return age >= Math.max(0, interval - 2);
}

function metricItem(label, value) {
  if (value == null || value === "") return null;
  const item = document.createElement("div");
  item.className = "service-detail-metric";
  const term = document.createElement("span");
  term.textContent = label;
  const content = document.createElement("strong");
  content.textContent = String(value);
  item.append(term, content);
  return item;
}

function layerMetrics(check, snapshot) {
  const elapsed = Number(check?.elapsed_ms ?? check?.latency_ms);
  const dnsElapsed = Number(check?.dns_latency_ms);
  const interval = Number(check?.probe_interval_seconds);
  const age = ageSeconds(check);
  const next =
    Number.isFinite(interval) && interval > 0 && age != null
      ? Math.max(0, interval - age)
      : Number(check?.next_probe_in_seconds);
  const observed = observedAt(check);
  const status = pendingState(check, snapshot)
    ? "PENDING / probing…"
    : check?.stale === true
      ? "STALE"
      : "complete";
  const cache =
    check?.cache_layer ??
    (check?.cached === true
      ? "cached"
      : check?.cached === false
        ? "live"
        : null);

  return [
    metricItem("Probe state", status),
    metricItem(
      "HTTP status",
      Number.isFinite(Number(check?.http_status)) ? check.http_status : null,
    ),
    metricItem(
      "Reachable",
      typeof check?.reachable === "boolean" ? String(check.reachable) : null,
    ),
    metricItem(
      "TLS trusted",
      typeof check?.tls_trusted === "boolean"
        ? String(check.tls_trusted)
        : null,
    ),
    metricItem(
      "Probe latency",
      Number.isFinite(elapsed) ? `${elapsed} ms` : null,
    ),
    metricItem(
      "DNS latency",
      Number.isFinite(dnsElapsed) ? `${dnsElapsed} ms` : null,
    ),
    metricItem(
      "Last probe",
      observed != null ? new Date(observed).toISOString() : null,
    ),
    metricItem("Probe age", age != null ? `${humanSeconds(age)} ago` : null),
    metricItem(
      "Cadence",
      Number.isFinite(interval) && interval > 0 ? humanSeconds(interval) : null,
    ),
    metricItem(
      "Next due",
      Number.isFinite(next) && next >= 0 ? humanSeconds(next) : null,
    ),
    metricItem("Cache", cache),
    metricItem("Stale", check?.stale === true ? "true" : null),
    metricItem("Vantage point", check?.vantage_point),
    metricItem("Probe", check?.probe),
    metricItem("Failure stage", check?.failure_stage),
    metricItem(
      "Refresh error",
      check?.probe_refresh_error ?? check?.refresh_error,
    ),
    metricItem("Error kind", check?.error_kind),
  ].filter(Boolean);
}

function appendLayer(section, label, check, snapshot) {
  if (!check) return false;
  const block = document.createElement("div");
  block.className = "service-detail-relation-block";
  const heading = document.createElement("strong");
  heading.textContent = label;
  block.appendChild(heading);
  const grid = document.createElement("div");
  grid.className = "service-detail-metrics";
  for (const item of layerMetrics(check, snapshot)) grid.appendChild(item);
  block.appendChild(grid);
  section.appendChild(block);
  return true;
}

function renderSelected(snapshot) {
  const row = document.querySelector(
    `${ROW_SELECTOR}[data-detail-selected="true"]`,
  );
  const body = document
    .getElementById("service-detail-drawer")
    ?.querySelector(".service-detail-body");
  if (!row || !body) return;

  body.querySelector("[data-probe-timing-section]")?.remove();
  const section = document.createElement("section");
  section.dataset.probeTimingSection = "true";
  const heading = document.createElement("h3");
  heading.textContent = "Probe timing & freshness";
  section.appendChild(heading);

  const layers = [
    ["Health probe", findCheck(snapshot?.healthz?.checks, row)],
    ["Homelab probe", findCheck(snapshot?.homelab?.services, row)],
    ["Exposure / edge probe", findCheck(snapshot?.sickz?.checks, row)],
  ];
  let rendered = false;
  for (const [label, check] of layers) {
    rendered = appendLayer(section, label, check, snapshot) || rendered;
  }

  if (!rendered) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent =
      "No per-service probe timing evidence is available yet.";
    section.appendChild(empty);
  }
  body.appendChild(section);
}

function scheduleRender() {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(() => {
    scheduled = false;
    if (latestSnapshot) renderSelected(latestSnapshot);
  });
}

async function refreshSnapshot() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  scheduleRender();
}

export function installServiceProbeDetails() {
  document.addEventListener(
    "click",
    (event) => {
      const trigger =
        event.target instanceof Element
          ? event.target.closest(".service-detail-trigger")
          : null;
      if (!trigger) return;
      window.setTimeout(() => {
        if (latestSnapshot) scheduleRender();
        else refreshSnapshot();
      }, 0);
    },
    true,
  );
  document.addEventListener("health-board-refreshed", refreshSnapshot);
  refreshSnapshot();
  ticker = window.setInterval(scheduleRender, TICK_MS);
}
