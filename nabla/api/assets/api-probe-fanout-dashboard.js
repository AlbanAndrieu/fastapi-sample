import { escapeText } from "./api-health-ui.js";
import { fetchHomelabProbeMatrix } from "./api-homelab-health.js";

const UPDATE_EVENT = "homelab-probes:update";
const LOADING_EVENT = "homelab-probes:loading";
const ERROR_EVENT = "homelab-probes:error";
const DASHBOARD_ID = "truenas-probe-dashboard";

let lastPayload = null;
let browserWarmupObservedAt = null;
let browserWarmupCompletedInSeconds = null;
let refreshInFlight = false;

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, finiteNumber(value)));
}

function humanSeconds(value) {
  const seconds = Math.max(0, Math.round(finiteNumber(value)));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function probeRows(data) {
  const internal = Array.isArray(data?.internal_services)
    ? data.internal_services.map((row) => ({ ...row, probe_scope: "LAN" }))
    : [];
  const publicRows = Array.isArray(data?.public_probe_results)
    ? data.public_probe_results.map((row) => ({ ...row, probe_scope: "public" }))
    : [];
  return [...internal, ...publicRows];
}

function scopeMetrics(summary, enabled = true) {
  const evidence = summary?.evidence || {};
  const eligible = enabled ? finiteNumber(summary?.eligible) : 0;
  const sampled = enabled
    ? finiteNumber(summary?.sampled ?? summary?.scheduled)
    : 0;
  const known = enabled ? finiteNumber(evidence?.known) : 0;
  const fresh = enabled ? finiteNumber(evidence?.fresh) : 0;
  const cached = enabled ? finiteNumber(evidence?.cached) : 0;
  return {
    enabled,
    eligible,
    sampled,
    known,
    fresh,
    cached,
    coverage: eligible > 0 ? clampPercent((known / eligible) * 100) : 100,
    timedOut: enabled ? finiteNumber(summary?.timed_out) : 0,
    cacheTtl: finiteNumber(summary?.evidence?.evidence_ttl_seconds),
  };
}

function classifyKnownRows(rows) {
  const counts = { ok: 0, warn: 0, fail: 0, stale: 0, deadline: 0 };
  for (const row of rows) {
    if (row?.probe_source === "deadline") {
      counts.deadline += 1;
      continue;
    }
    if (row?.probe_source !== "origin" && row?.probe_source !== "memory") {
      continue;
    }
    if (row?.probe_stale === true) {
      counts.stale += 1;
      continue;
    }
    const state = row?.state;
    if (state === "ok" || state === "warn" || state === "fail") {
      counts[state] += 1;
    } else {
      counts.warn += 1;
    }
  }
  return counts;
}

function progressModel(data) {
  const summary = data?.probe_summary || {};
  const internalEnabled =
    data?.internal_probes_enabled ?? summary?.internal?.enabled ?? false;
  const publicScope = scopeMetrics(summary.public || {}, true);
  const internalScope = scopeMetrics(summary.internal || {}, internalEnabled);
  const rows = probeRows(data);
  const counts = classifyKnownRows(rows);
  const eligible = publicScope.eligible + internalScope.eligible;
  const known = publicScope.known + internalScope.known;
  const unknown = Math.max(0, eligible - known);
  const coverage =
    eligible > 0 ? clampPercent((known / eligible) * 100) : 100;
  const healthy = counts.ok;
  const healthyCoverage =
    eligible > 0 ? clampPercent((healthy / eligible) * 100) : 100;
  return {
    publicScope,
    internalScope,
    rows,
    counts,
    eligible,
    known,
    unknown,
    coverage,
    healthy,
    healthyCoverage,
  };
}

function estimatedWarmupSeconds(data, model) {
  const runtimeEstimate = finiteNumber(
    data?.probe_runtime?.estimated_full_cycle_seconds,
    Number.NaN,
  );
  if (Number.isFinite(runtimeEstimate) && runtimeEstimate > 0) {
    return runtimeEstimate;
  }
  const cadences = model.rows
    .map((row) => finiteNumber(row?.probe_interval_seconds, Number.NaN))
    .filter((value) => Number.isFinite(value) && value > 0);
  return cadences.length ? Math.max(...cadences) : null;
}

function progressSegment(count, eligible, kind, label) {
  if (eligible <= 0 || count <= 0) return "";
  const width = clampPercent((count / eligible) * 100);
  return `<span class="probe-coverage-segment probe-coverage-segment--${kind}" style="width:${width}%" title="${escapeText(label)}"></span>`;
}

function progressBar(model) {
  const { counts, eligible, unknown } = model;
  return (
    '<div class="probe-coverage-track" role="img" aria-label="Probe evidence and health coverage">' +
    progressSegment(counts.ok, eligible, "ok", `${counts.ok} healthy`) +
    progressSegment(counts.warn, eligible, "warn", `${counts.warn} warning`) +
    progressSegment(counts.fail, eligible, "fail", `${counts.fail} failed`) +
    progressSegment(
      counts.stale,
      eligible,
      "stale",
      `${counts.stale} stale`,
    ) +
    progressSegment(
      unknown,
      eligible,
      "unknown",
      `${unknown} not yet observed`,
    ) +
    "</div>"
  );
}

function scopeCard(label, icon, scope) {
  if (!scope.enabled) {
    return `<div class="probe-scope-card"><span>${icon} ${escapeText(label)}</span><strong>disabled</strong><small>Excluded from coverage denominator</small></div>`;
  }
  return (
    '<div class="probe-scope-card">' +
    `<span>${icon} ${escapeText(label)}</span>` +
    `<strong>${scope.coverage.toFixed(1)}%</strong>` +
    `<small>${scope.known}/${scope.eligible} observed · ${scope.fresh} latest · ${scope.cached} retained</small>` +
    "</div>"
  );
}

function runtimeWarmupDetail(data) {
  const runtime = data?.probe_runtime || {};
  const uptime = finiteNumber(runtime?.uptime_seconds, Number.NaN);
  if (Number.isFinite(uptime)) {
    const startedAt = String(runtime?.started_at || "").trim();
    return `scheduler uptime ${humanSeconds(uptime)}${startedAt ? ` · started ${startedAt}` : ""}`;
  }

  if (browserWarmupObservedAt == null) browserWarmupObservedAt = Date.now();
  return `visible in this tab for ${humanSeconds((Date.now() - browserWarmupObservedAt) / 1000)}`;
}

function warmupText(data, model) {
  if (model.coverage < 100 && browserWarmupObservedAt == null) {
    browserWarmupObservedAt = Date.now();
  }
  if (
    model.coverage >= 100 &&
    browserWarmupObservedAt != null &&
    browserWarmupCompletedInSeconds == null
  ) {
    browserWarmupCompletedInSeconds = Math.max(
      0,
      Math.round((Date.now() - browserWarmupObservedAt) / 1000),
    );
  }

  const estimate = estimatedWarmupSeconds(data, model);
  const estimateText = estimate
    ? ` · longest priority-aware cadence ≈${humanSeconds(estimate)}`
    : "";
  const runtimeDetail = runtimeWarmupDetail(data);
  if (model.coverage >= 100) {
    return `✅ Full rolling evidence coverage · ${runtimeDetail}${estimateText}`;
  }
  return `🧊 Evidence warm-up · ${model.known}/${model.eligible} probe slots observed · ${runtimeDetail}${estimateText}`;
}

function cacheText(data) {
  const cache = data?.probe_cache || {};
  const age = finiteNumber(cache.age_seconds);
  const ttl = finiteNumber(cache.ttl_seconds, 30);
  const next = Math.max(0, ttl - age);
  if (cache.source === "origin") {
    return `Latest rotating wave completed · next window due in ≈${humanSeconds(next)}`;
  }
  if (cache.source === "memory") {
    return `Cached snapshot ${humanSeconds(age)} old · next rotating window due in ≈${humanSeconds(next)}`;
  }
  return "Probe cache state unknown";
}

function stateLabel(row) {
  if (row?.probe_source === "deadline" || row?.timed_out === true) {
    return "deadline";
  }
  if (row?.probe_stale === true) return "stale";
  return row?.state || "unknown";
}

function stateClass(row) {
  const state = stateLabel(row);
  if (state === "ok") return "ok";
  if (state === "fail") return "fail";
  if (state === "warn" || state === "deadline" || state === "stale") {
    return "warn";
  }
  return "unknown";
}

function targetHtml(row) {
  if (row?.probe_scope === "LAN") {
    const target =
      row?.host && row?.port != null
        ? `${row.host}:${row.port}`
        : "target unavailable";
    return `<code>${escapeText(target)}</code>`;
  }
  const target = String(row?.url || "public target unavailable");
  if (/^https?:\/\//i.test(target)) {
    return `<a href="${escapeText(target)}" target="_blank" rel="noopener noreferrer">${escapeText(target)}</a>`;
  }
  return `<code>${escapeText(target)}</code>`;
}

function observationText(row) {
  const age = finiteNumber(row?.probe_age_seconds, Number.NaN);
  const interval = finiteNumber(row?.probe_interval_seconds, Number.NaN);
  const next = finiteNumber(row?.next_probe_in_seconds, Number.NaN);
  const parts = [];
  if (Number.isFinite(age)) parts.push(`${humanSeconds(age)} ago`);
  if (Number.isFinite(interval)) {
    parts.push(`cadence ≈${humanSeconds(interval)}`);
  }
  if (Number.isFinite(next)) parts.push(`next ≈${humanSeconds(next)}`);
  return parts.length
    ? parts.join(" · ")
    : "observation timing unavailable";
}

function rowDetail(row) {
  const parts = [];
  if (row?.http_status) parts.push(`HTTP ${row.http_status}`);
  if (row?.latency_ms != null) parts.push(`${row.latency_ms} ms`);
  if (row?.error_kind) parts.push(row.error_kind);
  if (row?.probe_refresh_error) {
    parts.push(`refresh: ${row.probe_refresh_error}`);
  } else if (row?.error) {
    parts.push(row.error);
  }
  return parts.join(" · ") || "no error detail";
}

function probeRow(row) {
  const kind = stateClass(row);
  const source = row?.probe_source || "unknown";
  const sourceLabel =
    source === "origin"
      ? "latest"
      : source === "memory"
        ? "retained"
        : source;
  return (
    `<div class="probe-dashboard-row probe-dashboard-row--${kind}">` +
    '<div class="probe-dashboard-row-main">' +
    `<strong>${escapeText(row?.name || row?.id || "probe")}</strong>` +
    `<span class="probe-scope-badge">${escapeText(row?.probe_scope || "scope")}</span>` +
    `<span class="probe-state-badge probe-state-badge--${kind}">${escapeText(stateLabel(row))}</span>` +
    `<span class="probe-source-badge">${escapeText(sourceLabel)}</span>` +
    "</div>" +
    `<div class="probe-dashboard-target">${targetHtml(row)}</div>` +
    `<div class="probe-dashboard-timing">${escapeText(observationText(row))}</div>` +
    `<div class="probe-dashboard-detail">${escapeText(rowDetail(row))}</div>` +
    "</div>"
  );
}

function severity(row) {
  const state = stateLabel(row);
  if (state === "fail") return 0;
  if (state === "deadline") return 1;
  if (state === "warn" || state === "stale") return 2;
  return 3;
}

function sortedRows(rows, previous = false) {
  return [...rows].sort((left, right) => {
    if (previous) {
      return (
        finiteNumber(left?.probe_age_seconds) -
        finiteNumber(right?.probe_age_seconds)
      );
    }
    const stateOrder = severity(left) - severity(right);
    if (stateOrder !== 0) return stateOrder;
    return finiteNumber(right?.latency_ms) - finiteNumber(left?.latency_ms);
  });
}

function groupHtml(title, description, rows, previous = false) {
  if (rows.length === 0) {
    return `<section class="probe-dashboard-group"><h5>${escapeText(title)} · 0</h5><p>${escapeText(description)}</p><div class="probe-dashboard-empty">No rows in this group.</div></section>`;
  }
  return (
    '<section class="probe-dashboard-group">' +
    `<h5>${escapeText(title)} · ${rows.length}</h5>` +
    `<p>${escapeText(description)}</p>` +
    `<div class="probe-dashboard-rows">${sortedRows(rows, previous).map(probeRow).join("")}</div>` +
    "</section>"
  );
}

function ensureDashboard() {
  const legacySummary = document.getElementById("truenas-probe-summary");
  const legacyDetails = document.getElementById("truenas-probe-details");
  if (!legacySummary || !legacyDetails) return null;
  legacySummary.hidden = true;
  legacyDetails.hidden = true;

  let root = document.getElementById(DASHBOARD_ID);
  if (root) return root;
  root = document.createElement("details");
  root.id = DASHBOARD_ID;
  root.className = "probe-dashboard";
  root.innerHTML = `
    <summary class="probe-dashboard-heading">
      <div>
        <h4>Homelab probe fan-out</h4>
        <p id="probe-dashboard-activity">Waiting for the first bounded probe snapshot…</p>
      </div>
      <span class="probe-dashboard-collapsed-hint">Details</span>
    </summary>
    <div class="probe-dashboard-body">
      <div class="probe-dashboard-actions">
        <button type="button" id="probe-dashboard-refresh" class="probe-dashboard-refresh">Refresh details</button>
      </div>
    <div class="probe-dashboard-progress" aria-live="polite">
      <div class="probe-dashboard-progress-copy">
        <strong id="probe-dashboard-coverage">0% evidence coverage</strong>
        <span id="probe-dashboard-health">0% healthy coverage</span>
      </div>
      <div id="probe-dashboard-progress-bar"></div>
      <p id="probe-dashboard-warmup">Probe evidence has not loaded yet.</p>
    </div>
    <div class="probe-dashboard-scopes" id="probe-dashboard-scopes"></div>
    <div class="probe-dashboard-legend">
      <span>● healthy</span><span>▲ warning</span><span>■ failed</span><span>◌ stale</span><span>· not observed</span>
    </div>
    <div id="probe-dashboard-latest"></div>
    <div id="probe-dashboard-previous"></div>
    <p class="probe-dashboard-note">Coverage counts eligible probe slots, not catalog services: one service may have both a public and LAN probe. Disabled or unconfigured targets are excluded from the eligible denominator. The server keeps the 12-per-scope bounded scheduler and 30-second snapshot cache.</p>
    </div>
  `;
  legacySummary.insertAdjacentElement("beforebegin", root);

  root.addEventListener("toggle", () => {
    if (root.open && lastPayload) renderDashboard(lastPayload);
  });

  const button = root.querySelector("#probe-dashboard-refresh");
  button?.addEventListener("click", async () => {
    if (refreshInFlight) return;
    refreshInFlight = true;
    button.disabled = true;
    button.textContent = "Refreshing…";
    try {
      await fetchHomelabProbeMatrix({ reason: "manual" });
    } catch (error) {
      renderActivity(
        `⚠ Refresh failed: ${String(error?.message || error)}`,
        true,
      );
    } finally {
      refreshInFlight = false;
      button.disabled = false;
      button.textContent = "Refresh details";
    }
  });
  return root;
}

function renderActivity(message, warning = false) {
  const activity = document.getElementById("probe-dashboard-activity");
  if (!activity) return;
  activity.textContent = message;
  activity.classList.toggle("probe-dashboard-warning", warning);
}

function clarifyRuntimeTimeout(data) {
  const error = document.getElementById("truenas-platform-error");
  if (!error || data?.truenas?.api?.reachable !== true) return;
  const text = String(error.textContent || "");
  if (!text.includes("TrueNAS runtime: Call timeout")) return;
  error.textContent = text.replace(
    "TrueNAS runtime: Call timeout",
    "⚠ Aggregate TrueNAS runtime enrichment timed out; the raw TrueNAS API probe is healthy and this does not mark the platform down",
  );
}

function renderDashboard(data) {
  const root = ensureDashboard();
  if (!root) return;
  lastPayload = data;
  const model = progressModel(data);
  renderActivity(
    `${model.coverage.toFixed(1)}% evidence · ${model.healthyCoverage.toFixed(1)}% healthy · ${model.counts.fail} failed · ${model.counts.warn} warning`,
  );
  if (!root.open) {
    clarifyRuntimeTimeout(data);
    return;
  }
  const coverage = document.getElementById("probe-dashboard-coverage");
  const health = document.getElementById("probe-dashboard-health");
  const bar = document.getElementById("probe-dashboard-progress-bar");
  const warmup = document.getElementById("probe-dashboard-warmup");
  const scopes = document.getElementById("probe-dashboard-scopes");
  const latest = document.getElementById("probe-dashboard-latest");
  const previous = document.getElementById("probe-dashboard-previous");
  if (
    !coverage ||
    !health ||
    !bar ||
    !warmup ||
    !scopes ||
    !latest ||
    !previous
  ) {
    return;
  }

  coverage.textContent = `${model.coverage.toFixed(1)}% evidence coverage · ${model.known}/${model.eligible} eligible probe slots`;
  health.textContent = `${model.healthyCoverage.toFixed(1)}% healthy coverage · ${model.healthy} healthy · ${model.counts.warn} warning · ${model.counts.fail} failed · ${model.counts.stale} stale · ${model.counts.deadline} latest deadlines`;
  bar.innerHTML = progressBar(model);
  warmup.textContent = warmupText(data, model);
  scopes.innerHTML =
    scopeCard("public HTTPS", "🌐", model.publicScope) +
    scopeCard("LAN/TCP", "🏠", model.internalScope);

  const latestRows = model.rows.filter(
    (row) => row?.probe_source === "origin" || row?.probe_source === "deadline",
  );
  const previousRows = model.rows.filter(
    (row) => row?.probe_source === "memory",
  );
  latest.innerHTML = groupHtml(
    "Latest rotating wave",
    "Rows sampled by the most recent bounded window; deadlines are attempts without current evidence.",
    latestRows,
  );
  previous.innerHTML = groupHtml(
    "Retained previous evidence",
    "Last-known observations kept across rotating windows until cadence/staleness rules expire.",
    previousRows,
    true,
  );
  renderActivity(
    `${cacheText(data)} · refresh ${finiteNumber(data?.refresh_elapsed_ms)} ms`,
  );
  clarifyRuntimeTimeout(data);
}

function installRuntimeTimeoutObserver() {
  const error = document.getElementById("truenas-platform-error");
  if (!error) return;
  const observer = new MutationObserver(() => {
    if (lastPayload) clarifyRuntimeTimeout(lastPayload);
  });
  observer.observe(error, {
    childList: true,
    characterData: true,
    subtree: true,
  });
}

export function installProbeFanoutDashboard() {
  ensureDashboard();
  installRuntimeTimeoutObserver();
  window.addEventListener(UPDATE_EVENT, (event) =>
    renderDashboard(event.detail || {}),
  );
  window.addEventListener(LOADING_EVENT, (event) => {
    const reason = event.detail?.reason;
    renderActivity(
      reason === "manual"
        ? "↻ Refreshing the probe snapshot; the server still respects its bounded scheduler and cache…"
        : "◌ Checking whether the next bounded rotating wave is due…",
    );
  });
  window.addEventListener(ERROR_EVENT, (event) => {
    renderActivity(
      `⚠ Probe snapshot request failed: ${String(event.detail?.message || "unknown error")}`,
      true,
    );
  });
}
