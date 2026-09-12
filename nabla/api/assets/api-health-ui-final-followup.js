import { fetchHealthBoard } from "./api-health-board.js";

const PROBE_RETAIN_MS = 90000;
const probeEvidenceCache = new Map();
const planeLabelCache = new Map();
let latestSnapshot = null;
let scheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function rowKey(row) {
  return String(
    row?.dataset?.topologyId ||
      row?.dataset?.serviceKey ||
      row?.dataset?.serviceName ||
      row?.id ||
      "service",
  );
}

function probeCacheKey(row, kind) {
  return `${rowKey(row)}:${kind}`;
}

function rememberProbe(row, probe) {
  const kind = String(probe?.dataset?.probeKind || "").trim();
  if (!kind) return;
  probeEvidenceCache.set(probeCacheKey(row, kind), {
    html: probe.outerHTML,
    observedAt: Date.now(),
  });
}

function cloneCachedProbe(row, kind) {
  const cached = probeEvidenceCache.get(probeCacheKey(row, kind));
  if (!cached || Date.now() - cached.observedAt > PROBE_RETAIN_MS) return null;
  const template = document.createElement("template");
  template.innerHTML = cached.html.trim();
  const probe = template.content.firstElementChild;
  if (!(probe instanceof HTMLElement)) return null;
  probe.dataset.retainedDuringRefresh = "true";
  probe.title = `Retained during UI refresh · ${probe.title || "last known probe evidence"}`;
  return probe;
}

function publicStrip(row) {
  return (
    row.querySelector(
      ':scope .service-probe-strip[data-probe-plane="public"]',
    ) || row.querySelector(":scope .service-probe-strip")
  );
}

function ensureStableCloudflareTunnel(row) {
  const key = normalize(`${row.dataset.serviceKey} ${row.dataset.serviceName}`);
  const exposureRow = Boolean(row.closest("#sickz-checks"));
  const cloudflareRelevant =
    key.includes("cloudflare") ||
    row.dataset.exposureMode === "cloudflare" ||
    exposureRow;
  if (!cloudflareRelevant) return;
  const strip = publicStrip(row);
  if (!strip || strip.querySelector('[data-probe-kind="cloudflare"]')) return;

  const cached = cloneCachedProbe(row, "cloudflare");
  if (cached) {
    strip.appendChild(cached);
    return;
  }

  if (!key.includes("cloudflare") && row.dataset.exposureMode !== "cloudflare") {
    return;
  }
  const badge = document.createElement("span");
  badge.className = "service-probe service-probe--neutral";
  badge.dataset.probeKind = "cloudflare";
  badge.dataset.probeDisabled = "true";
  badge.title =
    "Cloudflare Tunnel evidence is currently unavailable. The Tunnel capability remains visible in gray so unavailable control-plane evidence is not confused with a removed route.";
  badge.setAttribute("aria-label", badge.title);
  const icon = document.createElement("span");
  icon.className = "service-probe-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "☁️";
  const label = document.createElement("span");
  label.className = "service-probe-label";
  label.textContent = "Tunnel";
  badge.append(icon, label);
  strip.appendChild(badge);
}

function rememberAndRestoreProbes(row) {
  const probes = [...row.querySelectorAll(".service-probe[data-probe-kind]")];
  for (const probe of probes) rememberProbe(row, probe);
  ensureStableCloudflareTunnel(row);
}

function planeCacheKey(row, plane) {
  return `${rowKey(row)}:plane:${plane}`;
}

function stabilizePlaneLabels(row) {
  for (const plane of ["public", "lan"]) {
    const selector = `.service-probe-plane-label--${plane}`;
    const label = row.querySelector(selector);
    const key = planeCacheKey(row, plane);
    if (label) {
      planeLabelCache.set(key, { html: label.outerHTML, observedAt: Date.now() });
      continue;
    }
    const cached = planeLabelCache.get(key);
    if (!cached || Date.now() - cached.observedAt > PROBE_RETAIN_MS) continue;
    const strip = row.querySelector(
      `.service-probe-strip[data-probe-plane="${plane}"]`,
    );
    const primary = strip?.parentElement;
    if (!strip || !primary) continue;
    const template = document.createElement("template");
    template.innerHTML = cached.html.trim();
    const restored = template.content.firstElementChild;
    if (!(restored instanceof HTMLElement)) continue;
    restored.dataset.retainedDuringRefresh = "true";
    primary.insertBefore(restored, strip);
  }
}

function normalizeTelemetry(row) {
  let column = row.querySelector(":scope > .health-row-telemetry");
  if (!column) {
    column = document.createElement("div");
    column.className = "health-row-telemetry";
    row.appendChild(column);
  }

  const liveLatency = column.querySelector(".health-meta-badge--probe-latency");
  for (const legacy of row.querySelectorAll(".health-meta-badge--metric")) {
    const value = String(legacy.textContent || "").trim();
    if (liveLatency) {
      legacy.remove();
      continue;
    }
    legacy.classList.remove("health-meta-badge--metric");
    legacy.classList.add("health-meta-badge--probe-latency");
    legacy.title = value
      ? `Latest probe latency: ${value}`
      : "Latest probe latency unavailable";
    legacy.setAttribute("aria-label", legacy.title);
    column.appendChild(legacy);
  }

  const key = normalize(`${row.dataset.serviceKey} ${row.dataset.serviceName}`);
  const latency = column.querySelector(".health-meta-badge--probe-latency");
  if (key.includes("cloudflare") && (!latency || latency.hidden)) {
    const unavailable = latency || document.createElement("span");
    unavailable.hidden = false;
    unavailable.className =
      "health-meta-badge health-meta-badge--probe-latency health-meta-badge--probe-latency-unavailable";
    unavailable.textContent = "-";
    unavailable.title = "Latest probe latency unavailable in the current snapshot";
    unavailable.setAttribute("aria-label", unavailable.title);
    const probing = column.querySelector(".health-meta-badge--probing");
    if (probing) column.insertBefore(unavailable, probing);
    else column.appendChild(unavailable);
  }

  const age = column.querySelector(".health-meta-badge--probe-age");
  if (age?.title?.startsWith("Last probe ")) {
    age.title = age.title.replace("Last probe ", "Latest probe observation: ");
    age.setAttribute("aria-label", age.title);
  }
  if (latency && !latency.hidden && latency.textContent?.trim()) {
    latency.title = `Latest probe latency: ${latency.textContent.trim()}`;
    latency.setAttribute("aria-label", latency.title);
  }
}

function cleanExposureCardInlineDetails(row) {
  if (!row.closest("#sickz-checks")) return;
  row
    .querySelectorAll(
      ".health-downstream-badge .service-hover-popover, .service-help-badge",
    )
    .forEach((node) => node.remove());
  const note = row.querySelector(".health-meta-note");
  if (
    note &&
    normalize(note.textContent).startsWith("legacy inverse-reachability target")
  ) {
    note.remove();
  }
}

function constrainLongMessages(row) {
  row.querySelectorAll(".health-row-detail, .service-provider-item").forEach((node) => {
    node.classList.add("health-overflow-safe");
  });
}

function decorateRows() {
  for (const row of document.querySelectorAll("[data-service-filter-target]")) {
    normalizeTelemetry(row);
    rememberAndRestoreProbes(row);
    stabilizePlaneLabels(row);
    cleanExposureCardInlineDetails(row);
    constrainLongMessages(row);
  }
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(() => {
    scheduled = false;
    decorateRows();
  });
}

function observeBoard() {
  const board = document.getElementById("health-board");
  if (!board) return;
  new MutationObserver(schedule).observe(board, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "hidden", "data-probe-plane"],
  });
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  void latestSnapshot;
  schedule();
}

export function installHealthUiFinalFollowup() {
  observeBoard();
  document.addEventListener("health-board-refreshed", refresh);
  document.addEventListener("service-filter-changed", schedule);
  refresh();
}
