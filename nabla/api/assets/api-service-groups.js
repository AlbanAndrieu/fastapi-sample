import {
  analyzeTopology,
  CRITICALITY_WEIGHT,
  NIST_CSF_FUNCTIONS,
} from "./api-service-classification.js";

const GROUPS = [
  {
    key: "services",
    label: "1 · Services & experiments",
    description:
      "User-facing and lab capabilities — the reason this homelab platform exists.",
    openWhenHealthy: true,
  },
  {
    key: "core-critical",
    label: "2 · Critical core platform",
    description:
      "Foundations with broad blast radius: storage, runtime, network and orchestration.",
    openWhenHealthy: true,
  },
  {
    key: "security-controls",
    label: "3 · Security controls",
    description:
      "Security-control health and posture, with NIST CSF 2.0 coverage metadata kept separate from effectiveness or compliance.",
    openWhenHealthy: true,
  },
  {
    key: "shared-core",
    label: "4 · Shared platform & data",
    description:
      "Shared state and platform capabilities used by multiple services.",
  },
  {
    key: "support",
    label: "5 · Observability & support",
    description:
      "Telemetry, dashboards, exporters and auxiliary components.",
  },
];

const EXTRA_GROUP = {
  key: "external",
  label: "External / optional integrations",
  description:
    "Checks outside the declared homelab dependency graph or not yet mapped to it.",
};

let topologyPromise = null;
let activeFilter = "";

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
    return new URL(String(value)).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function topologyIndexes(topology) {
  const byId = new Map();
  const byName = new Map();
  const byHost = new Map();
  for (const node of topology?.nodes || []) {
    byId.set(node.id, node);
    byName.set(normalize(node.name), node);
    const host = hostOf(node.url);
    if (host && !byHost.has(host)) byHost.set(host, node);
  }
  return { byId, byName, byHost };
}

function candidateIdFromKey(key) {
  const raw = String(key || "");
  if (raw.startsWith("albandrieu_"))
    return raw.slice("albandrieu_".length).replaceAll("_", "-");
  return raw.replaceAll("_", "-");
}

function findTopologyNode(row, check, indexes) {
  const idCandidates = [
    check?.service_id,
    check?.id,
    row?.dataset?.serviceKey,
    candidateIdFromKey(row?.dataset?.serviceKey),
  ];
  for (const candidate of idCandidates) {
    if (candidate && indexes.byId.has(String(candidate)))
      return indexes.byId.get(String(candidate));
  }

  for (const candidate of [
    check?.name,
    check?.display_label,
    row?.dataset?.serviceName,
  ]) {
    const name = normalize(candidate);
    if (name && indexes.byName.has(name)) return indexes.byName.get(name);
  }

  for (const value of [
    check?.url,
    check?.tunnel_url,
    check?.tunnelUrl,
    row?.dataset?.serviceUrl,
    ...(Array.isArray(check?.aliases_probed) ? check.aliases_probed : []),
  ]) {
    const host = hostOf(value);
    if (host && indexes.byHost.has(host)) return indexes.byHost.get(host);
  }
  return null;
}

function topology() {
  if (!topologyPromise) {
    topologyPromise = fetch("/api/homelab-topology", {
      cache: "no-store",
      headers: { Accept: "application/json", "Cache-Control": "no-cache" },
    })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .catch(() => ({ nodes: [], relations: [] }));
  }
  return topologyPromise;
}

function rowSeverity(row) {
  if (row.querySelector(".health-led--red")) return 0;
  if (row.querySelector(".health-led--yellow")) return 1;
  if (row.querySelector(".health-led--blue")) return 2;
  if (row.querySelector(".health-led--gray")) return 3;
  return 4;
}

function normalizedHealthState(value) {
  const state = String(value || "").trim().toLowerCase();
  return ["ok", "warn", "fail", "unknown"].includes(state) ? state : "";
}

function rowStatus(row, check = {}) {
  const localState = normalizedHealthState(check?.local_state);
  const dependencyState = normalizedHealthState(check?.dependency_state);

  if (localState === "fail") return "Down";
  if (localState === "warn") return "Degraded";
  if (localState === "unknown") return "Unknown";
  if (
    localState === "ok" &&
    ["fail", "warn", "unknown"].includes(dependencyState)
  ) {
    return "At risk";
  }
  if (localState === "ok") return "Operational";

  const severity = rowSeverity(row);
  if (severity === 0) return "Down";
  if (severity === 1 || severity === 2) return "Degraded";
  if (severity === 3) return "Unknown";
  return "Operational";
}

function probeLatencyMs(check) {
  for (const value of [check?.latency_ms, check?.elapsed_ms]) {
    const latency = Number(value);
    if (Number.isFinite(latency) && latency >= 0) return Math.round(latency);
  }
  return null;
}

function rowOutcomeOperational(row) {
  if (row.dataset.localState) return row.dataset.localState === "ok";
  return row.dataset.semanticStatus === "operational";
}

function addBadge(target, text, kind) {
  const badge = document.createElement("span");
  badge.className = `health-meta-badge health-meta-badge--${kind}`;
  badge.textContent = text;
  target.appendChild(badge);
}

function decorateRow(row, presentation, check) {
  const status = rowStatus(row, check);
  const statusKind = status.toLowerCase().replaceAll(" ", "-");
  const localState = normalizedHealthState(check?.local_state);
  const dependencyState = normalizedHealthState(check?.dependency_state);

  row.dataset.presentationRole = presentation.role;
  row.dataset.criticality = presentation.criticality;
  row.dataset.presentationGroup = presentation.group;
  row.dataset.semanticStatus = statusKind;
  row.dataset.localState = localState;
  row.dataset.dependencyState = dependencyState;
  row.dataset.downstreamCount = String(presentation.transitiveDependents || 0);
  row.dataset.securityFunctions = (presentation.securityFunctions || []).join(" ");

  const tags = row.querySelector(".health-row-tags");
  if (!tags) return;
  const original = tags.textContent?.trim() || "";
  tags.textContent = "";
  addBadge(tags, status, `status-${statusKind}`);
  addBadge(tags, presentation.role, "role");
  if (["critical", "high"].includes(presentation.criticality)) {
    addBadge(tags, presentation.criticality, presentation.criticality);
  }
  for (const securityFunction of presentation.securityFunctions || []) {
    const definition = NIST_CSF_FUNCTIONS.find(
      (item) => item.key === securityFunction,
    );
    addBadge(
      tags,
      `CSF · ${definition?.label || securityFunction}`,
      "security-function",
    );
  }

  const latency = probeLatencyMs(check);
  if (latency != null) addBadge(tags, `${latency} ms`, "metric");

  if (presentation.transitiveDependents > 0) {
    addBadge(
      tags,
      `${presentation.transitiveDependents} downstream`,
      "impact",
    );
  }
  if (original) {
    const note = document.createElement("span");
    note.className = "health-meta-note";
    note.textContent = original;
    tags.appendChild(note);
  }
}

function securityFrameworkReference(rows) {
  const declared = new Set(
    rows.flatMap((row) =>
      String(row.dataset.securityFunctions || "")
        .split(/\s+/)
        .filter(Boolean),
    ),
  );
  const reference = document.createElement("div");
  reference.className = "security-framework-reference";

  const heading = document.createElement("div");
  heading.className = "security-framework-heading";
  const title = document.createElement("strong");
  title.textContent = "NIST Cybersecurity Framework (CSF) 2.0";
  const link = document.createElement("a");
  link.href = "https://doi.org/10.6028/NIST.CSWP.29";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "NIST CSWP 29 ↗";
  heading.append(title, link);

  const note = document.createElement("p");
  note.textContent =
    "Six concurrent risk-management functions. Highlighted functions are declared coverage metadata, not proof of control effectiveness, maturity or compliance.";

  const functions = document.createElement("div");
  functions.className = "security-framework-functions";
  for (const definition of NIST_CSF_FUNCTIONS) {
    const item = document.createElement("span");
    item.className = `security-framework-function${declared.has(definition.key) ? " security-framework-function--declared" : ""}`;
    item.textContent = definition.label;
    item.title = definition.description;
    item.dataset.securityFunction = definition.key;
    functions.appendChild(item);
  }

  reference.append(heading, note, functions);
  return reference;
}

function serviceGroupSection(definition, rows) {
  const issueCount = rows.filter((row) => rowSeverity(row) < 4).length;
  const criticalIssues = rows.filter(
    (row) =>
      ["critical", "high"].includes(row.dataset.criticality || "") &&
      rowSeverity(row) < 4,
  ).length;
  const section = document.createElement("details");
  section.className = "service-group";
  section.dataset.serviceGroup = definition.key;
  section.open = Boolean(definition.openWhenHealthy || issueCount > 0);

  const heading = document.createElement("summary");
  heading.className = "service-group-heading";
  const issueText =
    issueCount > 0
      ? ` · ${issueCount} attention${criticalIssues ? ` · ${criticalIssues} high impact` : ""}`
      : "";
  heading.innerHTML = `<div><h4>${definition.label}</h4><p>${definition.description}</p></div><span>${rows.length} component${rows.length === 1 ? "" : "s"}${issueText}</span>`;

  const list = document.createElement("ul");
  list.className = "health-checks service-group-list";
  rows
    .sort(
      (left, right) =>
        rowSeverity(left) - rowSeverity(right) ||
        (CRITICALITY_WEIGHT[left.dataset.criticality] ?? 9) -
          (CRITICALITY_WEIGHT[right.dataset.criticality] ?? 9) ||
        Number(right.dataset.downstreamCount || 0) -
          Number(left.dataset.downstreamCount || 0) ||
        (left.textContent || "").localeCompare(right.textContent || ""),
    )
    .forEach((row) => list.appendChild(row));
  section.append(heading);
  if (definition.key === "security-controls") {
    section.appendChild(securityFrameworkReference(rows));
  }
  section.appendChild(list);
  return section;
}

function assignRows(rows, checks, topologyData) {
  const indexes = topologyIndexes(topologyData);
  const analysis = analyzeTopology(topologyData);
  const buckets = new Map(
    [...GROUPS, EXTRA_GROUP].map((group) => [group.key, []]),
  );

  for (const row of rows) {
    const key = row.dataset.serviceKey || "";
    const check = checks?.[key] || {};
    const node = findTopologyNode(row, check, indexes);
    const presentation = node
      ? analysis.get(node.id) || {
          role: "support",
          criticality: "low",
          group: "support",
        }
      : { role: "support", criticality: "low", group: "external" };
    decorateRow(row, presentation, check);
    const group =
      GROUPS.find((item) => item.key === presentation.group) || EXTRA_GROUP;
    row.dataset.searchText =
      `${row.dataset.searchText || ""} ${group.label} ${group.description} ${presentation.role} ${presentation.criticality} ${(presentation.securityFunctions || []).join(" ")} ${rowStatus(row, check)}`.toLowerCase();
    buckets.get(group.key).push(row);
  }
  return buckets;
}

function overviewCard(label, rows, metricDetail = "") {
  const total = rows.length;
  const operational = rows.filter(rowOutcomeOperational).length;
  const atRisk = rows.filter(
    (row) => row.dataset.semanticStatus === "at-risk",
  ).length;
  const down = rows.filter(
    (row) => row.dataset.semanticStatus === "down",
  ).length;
  const degraded = rows.filter(
    (row) => row.dataset.semanticStatus === "degraded",
  ).length;
  const unknown = rows.filter(
    (row) => row.dataset.semanticStatus === "unknown",
  ).length;
  const attention = atRisk + down + degraded + unknown;
  const tone =
    down > 0
      ? "red"
      : attention > 0
        ? "yellow"
        : total > 0
          ? "green"
          : "neutral";
  const details = [
    atRisk > 0 ? `${atRisk} at risk` : "",
    degraded > 0 ? `${degraded} degraded` : "",
    down > 0 ? `${down} down` : "",
    unknown > 0 ? `${unknown} unknown` : "",
  ].filter(Boolean);
  const footer = [...details, metricDetail].filter(Boolean).join(" · ");
  return `<div class="service-overview-card service-overview-card--${tone}"><span>${label}</span><strong>${operational}/${total} operational</strong><small>${footer || "No active issue"}</small></div>`;
}

function percentMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${Math.round(number * 100)}%`;
}

function platformOverviewDetails(platformMetrics) {
  const summary = platformMetrics?.summary || {};
  const memory = percentMetric(summary.truenas_memory_available_ratio);
  const cpu = percentMetric(summary.truenas_cpu_busy_ratio);
  const core = [
    cpu ? `TrueNAS CPU ${cpu}` : "",
    memory ? `memory ${memory} free` : "",
  ].filter(Boolean).join(" · ");

  const telemetryTotal = Number(summary.telemetry_total);
  const telemetryUp = Number(summary.telemetry_up);
  const telemetry =
    Number.isFinite(telemetryTotal) && telemetryTotal > 0
      ? `${telemetryUp}/${telemetryTotal} telemetry signals up`
      : platformMetrics?.state === "not_configured"
        ? "Prometheus metrics not configured"
        : platformMetrics?.state === "telemetry_unavailable"
          ? "Prometheus telemetry unavailable"
          : "";

  const pfsense = Number(summary.pfsense_metrics_up);
  const security = Number.isFinite(pfsense)
    ? pfsense >= 1
      ? "pfSense metrics online"
      : "pfSense metrics unavailable"
    : "";

  return { core, telemetry, security };
}

function updateOverview(buckets, platformMetrics = null) {
  const target = document.getElementById("service-health-overview");
  if (!target) return;
  const metrics = platformOverviewDetails(platformMetrics);
  target.innerHTML = [
    overviewCard("Services", buckets.get("services") || []),
    overviewCard("Critical core", buckets.get("core-critical") || [], metrics.core),
    overviewCard(
      "Security controls",
      buckets.get("security-controls") || [],
      metrics.security,
    ),
    overviewCard("Shared platform", buckets.get("shared-core") || []),
    overviewCard("Observability", buckets.get("support") || [], metrics.telemetry),
  ].join("");
}

function refreshFilter() {
  const tokens = normalize(activeFilter).split(/\s+/).filter(Boolean);
  for (const target of document.querySelectorAll("[data-service-filter-target]")) {
    const haystack = normalize(target.dataset.searchText || target.textContent || "");
    target.hidden =
      tokens.length > 0 && !tokens.every((token) => haystack.includes(token));
  }
  for (const group of document.querySelectorAll("[data-service-group]")) {
    const visible = [...group.querySelectorAll("[data-service-filter-target]")].some(
      (row) => !row.hidden,
    );
    group.hidden = !visible;
    if (tokens.length > 0 && visible) group.open = true;
  }
}

export async function organizeHealthRows(data, platformMetrics = null) {
  const list = document.getElementById("health-checks");
  const target = document.getElementById("health-services-groups");
  if (!list || !target) return;
  const rows = [...list.querySelectorAll(":scope > [data-service-filter-target]")];
  for (const row of rows) row.remove();
  target.innerHTML = "";

  const topologyData = await topology();
  const buckets = assignRows(rows, data?.checks || {}, topologyData);
  updateOverview(buckets, platformMetrics);
  for (const definition of [...GROUPS, EXTRA_GROUP]) {
    const groupRows = buckets.get(definition.key) || [];
    if (groupRows.length > 0) {
      target.appendChild(serviceGroupSection(definition, groupRows));
    }
  }
  refreshFilter();
}

export async function organizeSickzRows(data, pfsenseKey) {
  const list = document.getElementById("sickz-checks");
  if (!list) return;
  const rows = [...list.querySelectorAll(":scope > [data-service-filter-target]")];
  const topologyData = await topology();
  const checks = { ...(data?.checks || {}) };
  if (pfsenseKey) delete checks[pfsenseKey];
  const buckets = assignRows(rows, checks, topologyData);
  list.innerHTML = "";
  for (const definition of [...GROUPS, EXTRA_GROUP]) {
    const groupRows = buckets.get(definition.key) || [];
    if (groupRows.length === 0) continue;
    const shell = document.createElement("li");
    shell.className = "service-group-shell";
    shell.appendChild(serviceGroupSection(definition, groupRows));
    list.appendChild(shell);
  }
  refreshFilter();
}

export function installServiceFilter() {
  const input = document.getElementById("service-filter");
  const clear = document.getElementById("service-filter-clear");
  const expandIssues = document.getElementById("service-expand-issues");
  const collapseAll = document.getElementById("service-collapse-all");
  if (!input) return;

  input.addEventListener("input", () => {
    activeFilter = input.value;
    refreshFilter();
  });
  clear?.addEventListener("click", () => {
    input.value = "";
    activeFilter = "";
    refreshFilter();
    input.focus();
  });
  expandIssues?.addEventListener("click", () => {
    for (const group of document.querySelectorAll("[data-service-group]")) {
      group.open = Boolean(
        group.querySelector(
          ".health-led--red, .health-led--yellow, .health-led--blue, .health-led--gray",
        ),
      );
    }
  });
  collapseAll?.addEventListener("click", () => {
    for (const group of document.querySelectorAll("[data-service-group]")) {
      group.open = false;
    }
  });
}
