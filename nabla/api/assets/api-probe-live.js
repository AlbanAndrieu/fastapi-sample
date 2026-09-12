const AGE_TICK_MS = 1000;
const ROW_DECORATION_RETRY_MS = 50;
const ROW_DECORATION_ATTEMPTS = 20;

let lastSnapshot = null;
let ticker = null;

const TIER_HELP = {
  "Required infra (albandrieu.com)":
    "Required infrastructure for the albandrieu.com application/homelab view. A confirmed failure can affect the overall health summary. This is an availability tier, not the same thing as the canonical topology group or blast-radius criticality.",
  "Required health check":
    "Dependency required by the application health contract. A confirmed failure makes the deep diagnostic unhealthy.",
  "Optional health check":
    "Non-blocking integration or supporting service. A confirmed failure can raise attention, but it does not make the application unavailable. Missing or timed-out evidence is reported as a warning/unknown state rather than downtime.",
};

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

function parseObservedAt(value) {
  if (!value) return null;
  const timestamp = Date.parse(String(value));
  return Number.isFinite(timestamp) ? timestamp : null;
}

function observedAtForCheck(check, snapshot) {
  const candidates = [
    check?.probe_observed_at,
    check?.direct_probe_observed_at,
    check?.internal_probe_observed_at,
    check?.observed_at,
    check?.last_success_at,
    snapshot?.homelab?.checked_at,
  ]
    .map(parseObservedAt)
    .filter((value) => value != null);
  if (candidates.length > 0) return Math.max(...candidates);
  return parseObservedAt(snapshot?.generated_at);
}

function ageSeconds(observedAt) {
  if (observedAt == null) return null;
  return Math.max(0, Math.floor((Date.now() - observedAt) / 1000));
}

function collectionValues(collection) {
  if (Array.isArray(collection)) return collection;
  if (collection && typeof collection === "object") {
    return Object.values(collection);
  }
  return [];
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
  return [check.url, check.tunnel_url, check.tunnelUrl, check.href, ...aliases]
    .map(hostOf)
    .filter(Boolean)
    .includes(rowHost);
}

function findCheck(collection, row) {
  return (
    collectionValues(collection).find((check) => checkMatchesRow(check, row)) ||
    null
  );
}

function checkForRow(snapshot, row) {
  const healthChecks = snapshot?.healthz?.checks || {};
  const direct = healthChecks[row.dataset.serviceKey];
  if (direct) return direct;
  return (
    findCheck(snapshot?.homelab?.public_probe_results, row) ||
    findCheck(snapshot?.homelab?.services, row) ||
    findCheck(snapshot?.sickz?.checks, row) ||
    findCheck(healthChecks, row) ||
    null
  );
}

function ensureTelemetryColumn(row) {
  let column = row.querySelector(":scope > .health-row-telemetry");
  if (column) return column;
  column = document.createElement("div");
  column.className = "health-row-telemetry";
  column.setAttribute("aria-label", "Probe timing and freshness");
  row.appendChild(column);
  return column;
}

function ensureTelemetryBadge(row, className) {
  const column = ensureTelemetryColumn(row);
  let badge = column.querySelector(`.${className}`);
  if (badge) return badge;
  badge = document.createElement("span");
  badge.className = `health-meta-badge ${className}`;
  column.appendChild(badge);
  return badge;
}

function ensureAgeBadge(row) {
  return ensureTelemetryBadge(row, "health-meta-badge--probe-age");
}

function ensureLatencyBadge(row) {
  return ensureTelemetryBadge(row, "health-meta-badge--probe-latency");
}

function ensureProbingBadge(row) {
  const badge = ensureTelemetryBadge(row, "health-meta-badge--probing");
  badge.textContent = "probing…";
  return badge;
}

function checkIsDue(check, observedAt) {
  const interval = Number(check?.probe_interval_seconds);
  if (!Number.isFinite(interval) || interval <= 0) return true;
  const age = ageSeconds(observedAt);
  return age == null || age >= Math.max(0, interval - 2);
}

function decorateTierHelp(row) {
  const note = row.querySelector(".health-meta-note");
  if (!note) return;
  const label = String(note.textContent || "").trim();
  const help = TIER_HELP[label];
  if (!help) return;
  note.classList.add("health-tier-help");
  note.title = help;
  note.setAttribute("aria-label", `${label}. ${help}`);
}

function updateRow(row, check, snapshot) {
  decorateTierHelp(row);
  const observedAt = observedAtForCheck(check, snapshot);
  const age = ageSeconds(observedAt);
  const badge = ensureAgeBadge(row);
  badge.textContent = age == null ? "age unknown" : `${age}s ago`;
  const interval = Number(check?.probe_interval_seconds);
  const cadence =
    Number.isFinite(interval) && interval > 0
      ? ` · cadence ${Math.round(interval)}s`
      : "";
  badge.title =
    age == null
      ? `Latest probe age unavailable${cadence}`
      : `Latest probe age: ${age}s${cadence}`;
  badge.setAttribute("aria-label", badge.title);

  const latency = Number(check?.elapsed_ms ?? check?.latency_ms);
  const latencyBadge = ensureLatencyBadge(row);
  latencyBadge.hidden = false;
  latencyBadge.classList.toggle(
    "health-meta-badge--probe-latency-unavailable",
    !Number.isFinite(latency),
  );
  if (Number.isFinite(latency)) {
    latencyBadge.textContent = `${latency} ms`;
    latencyBadge.title = `Latest probe latency: ${latency} ms`;
  } else {
    latencyBadge.textContent = "—";
    latencyBadge.title = "Latest probe latency unavailable";
  }
  latencyBadge.setAttribute("aria-label", latencyBadge.title);

  const probing =
    snapshot?.refreshing === true && checkIsDue(check, observedAt);
  const probingBadge = row.querySelector(
    ":scope > .health-row-telemetry .health-meta-badge--probing",
  );
  if (probing) ensureProbingBadge(row);
  else probingBadge?.remove();
}

function decorateRows(snapshot, attempt = 0) {
  const rows = [...document.querySelectorAll(".health-row[data-service-key]")];
  if (rows.length === 0 && attempt < ROW_DECORATION_ATTEMPTS) {
    window.setTimeout(
      () => decorateRows(snapshot, attempt + 1),
      ROW_DECORATION_RETRY_MS,
    );
    return;
  }
  for (const row of rows) {
    updateRow(row, checkForRow(snapshot, row) || {}, snapshot);
  }
}

function installTierLegend() {
  if (document.getElementById("health-tier-legend")) return;
  const groups = document.getElementById("health-services-groups");
  if (!groups) return;
  const legend = document.createElement("div");
  legend.id = "health-tier-legend";
  legend.className = "health-tier-legend";
  legend.innerHTML =
    "<strong>Health-check tiers</strong>" +
    "<span><b>Required infra (albandrieu.com)</b> — availability requirement for the homelab/domain view; confirmed failures may affect the overall summary.</span>" +
    "<span><b>Optional health check</b> — non-blocking integration/support probe; an unconfirmed timeout is a warning, not downtime.</span>";
  groups.before(legend);
}

export function decorateProbeTelemetry(snapshot) {
  lastSnapshot = snapshot;
  installTierLegend();
  decorateRows(snapshot);
}

export function markVisibleProbeRowsPending() {
  for (const row of document.querySelectorAll(
    ".health-row[data-service-key]",
  )) {
    ensureProbingBadge(row);
  }
}

export function startProbeAgeTicker() {
  if (ticker) return;
  ticker = window.setInterval(() => {
    if (lastSnapshot) decorateRows(lastSnapshot);
  }, AGE_TICK_MS);
}
