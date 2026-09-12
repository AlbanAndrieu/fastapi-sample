const ROW_SELECTOR = ".health-row[data-service-filter-target]";

let latestSnapshot = null;
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
  if (timestamp != null) return Math.max(0, (Date.now() - timestamp) / 1000);
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

function toneFor(check) {
  const status = Number(check?.http_status);
  if (Number.isFinite(status)) {
    if (status >= 200 && status < 400) return "ok";
    if (status >= 500) return "fail";
    if (status >= 400) return "warn";
  }
  if (check?.skipped === true) return "neutral";
  if (check?.reachable === true) return "ok";
  if (check?.reachable === false) return "fail";
  return "unknown";
}

function pending(check, snapshot) {
  if (check?.refreshing === true || check?.pending === true) return true;
  if (snapshot?.refreshing !== true) return false;
  const interval = Number(check?.probe_interval_seconds);
  const age = ageSeconds(check);
  if (!Number.isFinite(interval) || interval <= 0 || age == null) return true;
  return age >= Math.max(0, interval - 2);
}

function hoverFor(check, snapshot) {
  const parts = [];
  const status = Number(check?.http_status);
  if (Number.isFinite(status)) parts.push(`HTTP ${status}`);
  else parts.push("HTTP status unconfirmed");

  const elapsed = Number(check?.elapsed_ms ?? check?.latency_ms);
  if (Number.isFinite(elapsed)) parts.push(`latency=${elapsed}ms`);

  const observed = observedAt(check);
  if (observed != null)
    parts.push(`last-run=${new Date(observed).toISOString()}`);
  const age = ageSeconds(check);
  if (age != null) parts.push(`age=${Math.round(age)}s`);

  const interval = Number(check?.probe_interval_seconds);
  if (Number.isFinite(interval) && interval > 0) {
    parts.push(`cadence=${Math.round(interval)}s`);
    if (age != null)
      parts.push(`next-due=${Math.max(0, Math.round(interval - age))}s`);
  }
  if (pending(check, snapshot)) parts.push("PENDING / probing…");
  if (check?.stale === true) parts.push("stale");
  if (check?.vantage_point) parts.push(`vantage=${check.vantage_point}`);
  if (check?.failure_stage) parts.push(`stage=${check.failure_stage}`);
  if (check?.error_kind) parts.push(`error=${check.error_kind}`);
  return parts.join(" · ");
}

function apply() {
  scheduled = false;
  if (!latestSnapshot) return;
  for (const row of document.querySelectorAll(ROW_SELECTOR)) {
    const badge = row.querySelector(
      '.service-probe-strip [data-probe-kind="http"]',
    );
    if (!badge) continue;
    const check =
      findCheck(latestSnapshot?.healthz?.checks, row) ||
      findCheck(latestSnapshot?.homelab?.services, row) ||
      findCheck(latestSnapshot?.sickz?.checks, row);
    if (!check) continue;

    for (const candidate of ["ok", "warn", "fail", "unknown", "neutral"]) {
      badge.classList.remove(`service-probe--${candidate}`);
    }
    badge.classList.add(`service-probe--${toneFor(check)}`);
    const hover = hoverFor(check, latestSnapshot);
    badge.title = hover;
    badge.setAttribute("aria-label", hover);
  }
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.setTimeout(() => window.requestAnimationFrame(apply), 0);
}

export function decorateHttpProbeStatuses(snapshot) {
  latestSnapshot = snapshot;
  schedule();
}

export function installHttpProbeStatuses() {
  document.addEventListener("health-board-refreshed", schedule);
  window.setInterval(schedule, 1000);
}
