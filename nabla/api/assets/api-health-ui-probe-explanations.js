import { fetchHealthBoard } from "./api-health-board.js";

const ROW_SELECTOR = "[data-service-filter-target]";
let latestSnapshot = null;
let applyScheduled = false;

function scopeSummary(scope) {
  const summary = latestSnapshot?.homelab?.probe_summary?.[scope] || {};
  const evidence = summary.evidence || {};
  return {
    enabled:
      scope === "internal"
        ? (latestSnapshot?.homelab?.internal_probes_enabled ??
          summary.enabled ??
          false)
        : true,
    eligible: Number(summary.eligible),
    sampled: Number(summary.sampled ?? summary.scheduled),
    known: Number(evidence.known),
    cached: Number(evidence.cached),
    rotating: summary.rotating_sample === true,
  };
}

function countText(value, fallback = "?") {
  return Number.isFinite(value) ? String(value) : fallback;
}

function internalSamplingDetail() {
  const scope = scopeSummary("internal");
  if (!scope.enabled) {
    return "LAN/TCP probes are disabled for this runtime. Enable HOMELAB_INTERNAL_PROBES_ENABLED=true only on a trusted homelab/local observer.";
  }
  const sample = `${countText(scope.sampled, "0")}/${countText(scope.eligible)} sampled`;
  const retained = Number.isFinite(scope.cached)
    ? ` · ${scope.cached} retained`
    : "";
  const rotation = scope.rotating
    ? " The fan-out uses a bounded rotating window, so an unsampled service is not considered unreachable."
    : "";
  return `LAN/TCP probe not sampled in the current cycle: ${sample}${retained}.${rotation}`;
}

function publicSamplingDetail() {
  const scope = scopeSummary("public");
  const sample = `${countText(scope.sampled, "0")}/${countText(scope.eligible)} sampled`;
  const retained = Number.isFinite(scope.cached)
    ? ` · ${scope.cached} retained`
    : "";
  const rotation = scope.rotating
    ? " Public HTTP probing also uses a bounded rotating window."
    : "";
  return `No current public HTTP evidence is attached to this service: ${sample}${retained}.${rotation} Runtime RUNNING and LAN/TCP reachability are independent signals and do not prove HTTP health.`;
}

function annotateRow(row) {
  const lan = row.querySelector(
    '.service-probe-strip[data-probe-plane="lan"] [data-probe-kind="tcp"]',
  );
  if (lan?.classList.contains("service-probe--unknown")) {
    const detail = internalSamplingDetail();
    lan.title = detail;
    lan.setAttribute("aria-label", detail);
  }

  const http = row.querySelector(
    '.service-probe-strip[data-probe-plane="public"] [data-probe-kind="http"]',
  );
  if (http?.classList.contains("service-probe--unknown")) {
    const detail = publicSamplingDetail();
    http.title = detail;
    http.setAttribute("aria-label", detail);
  }
}

function apply() {
  applyScheduled = false;
  if (!latestSnapshot) return;
  document.querySelectorAll(ROW_SELECTOR).forEach(annotateRow);
}

function scheduleApply() {
  if (applyScheduled) return;
  applyScheduled = true;
  window.requestAnimationFrame(apply);
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  scheduleApply();
}

export function installHealthUiProbeExplanations() {
  document.addEventListener("health-board-refreshed", refresh);
  document.addEventListener("service-filter-changed", scheduleApply);
  refresh();
}
