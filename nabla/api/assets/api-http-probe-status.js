import {
  expectedAnonymousAuth,
  expectedHttpFailure,
  firstObservedCheck,
  httpObservationTone,
} from "./api-service-http-auth.js";

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

const PRIVATE_S3_DETAIL =
  "Private S3 API. Anonymous HTTP GET is not a signed S3 health check; outside-in failures do not prove origin downtime.";

function privateS3(serviceId) {
  return (
    serviceId.replace(/^albandrieu_/, "").replaceAll("_", "-") === "garage"
  );
}

function toneFor(check, serviceId) {
  if (privateS3(serviceId)) return "unknown";
  return httpObservationTone(check, serviceId);
}

function pending(check, snapshot) {
  if (check?.refreshing === true || check?.pending === true) return true;
  if (snapshot?.refreshing !== true) return false;
  const interval = Number(check?.probe_interval_seconds);
  const age = ageSeconds(check);
  if (!Number.isFinite(interval) || interval <= 0 || age == null) return true;
  return age >= Math.max(0, interval - 2);
}

function hoverFor(check, snapshot, serviceId, target) {
  const parts = [];
  if (privateS3(serviceId)) parts.push(PRIVATE_S3_DETAIL);
  const expected =
    expectedAnonymousAuth(serviceId, check) || expectedHttpFailure(check);
  if (expected) parts.push(expected.detail);
  if (target) parts.push(`target=${target}`);
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
    // Sole writer of this badge: the outside-in public probe first, then the
    // same order api-service-diagnostics uses to build the strip.
    const declared = findCheck(latestSnapshot?.homelab?.services, row);
    const rowHost = hostOf(row.dataset.serviceUrl);
    const declaredHere =
      rowHost && hostOf(declared?.url) && hostOf(declared.url) !== rowHost
        ? null
        : declared;
    const check = firstObservedCheck(
      findCheck(latestSnapshot?.homelab?.public_probe_results, row),
      findCheck(latestSnapshot?.healthz?.checks, row),
      declaredHere,
      findCheck(latestSnapshot?.sickz?.checks, row),
    );
    if (!check) continue;

    const serviceId = String(
      row.dataset.topologyId || row.dataset.serviceKey || "",
    );
    const tone = `service-probe--${toneFor(check, serviceId)}`;
    // Swap the tone only when it changes: a remove/add pair re-triggers observers.
    if (!badge.classList.contains(tone)) {
      for (const candidate of [
        "ok",
        "warn",
        "fail",
        "unknown",
        "neutral",
        "info",
        "expected",
      ]) {
        badge.classList.remove(`service-probe--${candidate}`);
      }
      badge.classList.add(tone);
    }
    const expected = expectedAnonymousAuth(serviceId, check);
    const label = badge.querySelector(".service-probe-label");
    const observedHttp = Number(check?.http_status);
    const text = privateS3(serviceId)
      ? "Private S3 · HTTP ≠ health"
      : expected?.label ||
        (Number.isFinite(observedHttp) && observedHttp > 0
          ? `HTTP ${observedHttp}`
          : "HTTP");
    if (label && label.textContent !== text) label.textContent = text;
    const hover = hoverFor(
      check,
      latestSnapshot,
      serviceId,
      check.url || row.dataset.serviceUrl || "",
    );
    if (badge.title !== hover) {
      badge.title = hover;
      badge.setAttribute("aria-label", hover);
    }
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
  // service-diagnostics rebuilds the strip, then announces it with this event.
  document.addEventListener("service-filter-changed", schedule);
  // Changes originate from health-board events; a 1-second full-card scan
  // wastes CPU and can make the catalogue look frozen on large inventories.
}
