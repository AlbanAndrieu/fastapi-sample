import { fetchHealthBoard } from "./api-health-board.js";

const PROBE_RETAIN_MS = 90000;
const PROBE_SLOT_DEFINITIONS = new Map([
  ["dns", ["🧭", "DNS"]],
  ["http", ["🌐", "HTTP"]],
  ["tls", ["🔒", "TLS"]],
  ["cloudflare", ["☁️", "Tunnel"]],
  ["access", ["🛡️", "Access"]],
  ["service-token", ["🔑", "Token"]],
  ["tcp", ["🔌", "TCP"]],
  ["api", ["⚙️", "API"]],
  ["websocket", ["↔", "WebSocket"]],
  ["metrics", ["📈", "Prometheus"]],
]);
const PROBE_SLOT_ORDER = [...PROBE_SLOT_DEFINITIONS.keys()];
const probeEvidenceCache = new Map();
const knownProbeSlots = new Map();
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

function hostOf(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return new URL(raw, window.location.href).hostname
      .toLowerCase()
      .replace(/\.$/, "");
  } catch {
    return "";
  }
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

function collectionValues(collection) {
  if (Array.isArray(collection)) return collection;
  if (collection && typeof collection === "object") return Object.values(collection);
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
  return rowHost && hostOf(check.url || check.tunnel_url || check.tunnelUrl) === rowHost;
}

function evidenceForRow(row) {
  if (!latestSnapshot) return null;
  for (const collection of [
    latestSnapshot?.homelab?.public_probe_results,
    latestSnapshot?.homelab?.services,
    latestSnapshot?.healthz?.checks,
    latestSnapshot?.sickz?.checks,
  ]) {
    const match = collectionValues(collection).find((check) =>
      checkMatchesRow(check, row),
    );
    if (match) return match;
  }
  return null;
}

function probeCacheKey(row, kind) {
  return `${rowKey(row)}:${kind}`;
}

function rememberProbe(row, probe) {
  const kind = String(probe?.dataset?.probeKind || "").trim();
  if (!kind || probe?.dataset?.probePlaceholder === "true") return;
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

function makeProbe(kind, tone, iconText, labelText, detail) {
  const badge = document.createElement("span");
  badge.className = `service-probe service-probe--${tone}`;
  badge.dataset.probeKind = kind;
  badge.title = detail;
  badge.setAttribute("aria-label", detail);
  const icon = document.createElement("span");
  icon.className = "service-probe-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = iconText;
  const label = document.createElement("span");
  label.className = "service-probe-label";
  label.textContent = labelText;
  badge.append(icon, label);
  return badge;
}

function ensureDnsEvidence(row) {
  const strip = publicStrip(row);
  if (!strip || strip.querySelector('[data-probe-kind="dns"]')) return;
  const evidence = evidenceForRow(row);
  if (!evidence?.dns_hostname) return;
  const state = normalize(evidence.dns_state);
  const resolved = Array.isArray(evidence.dns_resolved)
    ? evidence.dns_resolved.filter(Boolean)
    : [];
  const resolvers = Array.isArray(evidence.dns_resolvers)
    ? evidence.dns_resolvers.filter(Boolean)
    : [];
  const tone = state === "ok" ? "ok" : state === "fail" ? "fail" : "unknown";
  const latency = Number(evidence.dns_latency_ms);
  const detail = [
    `DNS ${evidence.dns_hostname}`,
    resolved.length ? `resolved=${resolved.join(", ")}` : "no resolved address",
    resolvers.length ? `resolver=${resolvers.join(", ")}` : "resolver unavailable",
    Number.isFinite(latency) ? `${latency} ms` : "",
    evidence.dns_probe ? `probe=${evidence.dns_probe}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  strip.prepend(makeProbe("dns", tone, "🧭", "DNS", detail));
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

  if (
    !key.includes("cloudflare") &&
    row.dataset.exposureMode !== "cloudflare"
  ) {
    return;
  }
  const badge = makeProbe(
    "cloudflare",
    "neutral",
    "☁️",
    "Tunnel",
    "Cloudflare Tunnel evidence is currently unavailable. The Tunnel capability remains visible in gray so unavailable control-plane evidence is not confused with a removed route.",
  );
  badge.dataset.probePlaceholder = "true";
  strip.appendChild(badge);
}

function rememberAndRestoreProbes(row) {
  ensureDnsEvidence(row);
  const probes = [...row.querySelectorAll(".service-probe[data-probe-kind]")];
  for (const probe of probes) rememberProbe(row, probe);
  ensureStableCloudflareTunnel(row);
}

function slotKey(row, strip) {
  return `${rowKey(row)}:slots:${strip.dataset.probePlane || "public"}`;
}

function inferredProbeKinds(row, strip) {
  const kinds = new Set(
    [...strip.querySelectorAll(":scope > .service-probe[data-probe-kind]")]
      .map((probe) => probe.dataset.probeKind)
      .filter(Boolean),
  );
  const plane = strip.dataset.probePlane || "public";
  if (plane === "lan") {
    kinds.add("tcp");
    return kinds;
  }

  const evidence = evidenceForRow(row);
  const url = String(
    evidence?.url ||
      evidence?.tunnel_url ||
      evidence?.tunnelUrl ||
      row.dataset.serviceUrl ||
      "",
  ).trim();
  if (hostOf(url)) kinds.add("dns");
  if (/^https?:\/\//i.test(url)) kinds.add("http");
  if (/^https:\/\//i.test(url)) kinds.add("tls");

  const declared = String(row.dataset.probeKinds || "")
    .split(/[\s,]+/)
    .map((kind) => kind.trim().toLowerCase())
    .filter((kind) => PROBE_SLOT_DEFINITIONS.has(kind));
  for (const kind of declared) kinds.add(kind);

  const identity = normalize(`${row.dataset.serviceKey} ${row.dataset.serviceName}`);
  const cloudflareRelevant =
    row.dataset.exposureMode === "cloudflare" ||
    identity.includes("cloudflare") ||
    kinds.has("cloudflare") ||
    kinds.has("access") ||
    kinds.has("service-token");
  if (cloudflareRelevant) {
    kinds.add("cloudflare");
    kinds.add("access");
    kinds.add("service-token");
  }
  return kinds;
}

function ensureProbePlaceholder(strip, kind) {
  if (strip.querySelector(`:scope > .service-probe[data-probe-kind="${kind}"]`)) {
    return;
  }
  const [icon, label] = PROBE_SLOT_DEFINITIONS.get(kind) || ["•", kind];
  const badge = makeProbe(
    kind,
    "neutral",
    icon,
    label,
    `${label} evidence is not available in the current snapshot. The slot remains visible to keep the operational layout stable.`,
  );
  badge.dataset.probePlaceholder = "true";
  strip.appendChild(badge);
}

function stabilizeProbeSlots(row) {
  for (const strip of row.querySelectorAll(":scope .service-probe-strip")) {
    const key = slotKey(row, strip);
    const known = knownProbeSlots.get(key) || new Set();
    for (const kind of inferredProbeKinds(row, strip)) known.add(kind);
    knownProbeSlots.set(key, known);
    for (const kind of known) ensureProbePlaceholder(strip, kind);

    const order = new Map(PROBE_SLOT_ORDER.map((kind, index) => [kind, index]));
    const probes = [
      ...strip.querySelectorAll(":scope > .service-probe[data-probe-kind]"),
    ];
    probes
      .sort(
        (left, right) =>
          (order.get(left.dataset.probeKind) ?? 99) -
          (order.get(right.dataset.probeKind) ?? 99),
      )
      .forEach((probe) => strip.appendChild(probe));
  }
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
      planeLabelCache.set(key, {
        html: label.outerHTML,
        observedAt: Date.now(),
      });
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

  let latency = column.querySelector(".health-meta-badge--probe-latency");
  if (!latency) {
    latency = document.createElement("span");
    latency.className =
      "health-meta-badge health-meta-badge--probe-latency health-meta-badge--probe-latency-unavailable";
    column.prepend(latency);
  }
  if (latency.hidden || !latency.textContent?.trim()) {
    latency.hidden = false;
    latency.classList.add("health-meta-badge--probe-latency-unavailable");
    latency.textContent = "—";
    latency.title = "Latest probe latency unavailable";
    latency.setAttribute("aria-label", latency.title);
  } else {
    latency.classList.toggle(
      "health-meta-badge--probe-latency-unavailable",
      latency.textContent.trim() === "—",
    );
    latency.title =
      latency.textContent.trim() === "—"
        ? "Latest probe latency unavailable"
        : `Latest probe latency: ${latency.textContent.trim()}`;
    latency.setAttribute("aria-label", latency.title);
  }

  const age = column.querySelector(".health-meta-badge--probe-age");
  if (age) {
    const value = String(age.textContent || "").trim() || "age unknown";
    age.textContent = value;
    age.title = `Latest probe age: ${value}`;
    age.setAttribute("aria-label", age.title);
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
  row
    .querySelectorAll(".health-row-detail, .service-provider-item")
    .forEach((node) => {
      node.classList.add("health-overflow-safe");
    });
}

function decorateRows() {
  for (const row of document.querySelectorAll("[data-service-filter-target]")) {
    normalizeTelemetry(row);
    rememberAndRestoreProbes(row);
    stabilizeProbeSlots(row);
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
  schedule();
}

export function installHealthUiFinalFollowup() {
  observeBoard();
  document.addEventListener("health-board-refreshed", refresh);
  document.addEventListener("service-filter-changed", schedule);
  refresh();
}
