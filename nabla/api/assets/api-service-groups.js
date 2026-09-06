import {
  analyzeTopology,
  CRITICALITY_WEIGHT,
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
      "Preventive, detective and response controls used to experiment with and improve security.",
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

  const tags = row.querySelector(".health-row-tags");
  if (!tags) return;
  const original = tags.textContent?.trim() || "";
  tags.textContent = "";
  addBadge(tags, status, `status-${statusKind}`);
  addBadge(tags, presentation.role, "role");
  if (["critical", "high"].includes(presentation.criticality)) {
    addBadge(tags, presentation.criticality, presentation.criticality);
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
        (left.textContent || "").localeCompare(right.textContent || ""),
    )
    .forEach((row) => list.appendChild(row));
  section.append(heading, list);
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
      `${row.dataset.searchText || ""} ${group.label} ${group.description} ${presentation.role} ${presentation.criticality} ${rowStatus(row, check)}`.toLowerCase();
    buckets.get(group.key).push(row);
  }
  return buckets;
}

function overviewCard(label, rows) {
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
  return `<div class="service-overview-card service-overview-card--${tone}"><span>${label}</span><strong>${operational}/${total} operational</strong><small>${details.length ? details.join(" · ") : "No active issue"}</small></div>`;
}

function updateOverview(buckets) {
  const target = document.getElementById("service-health-overview");
  if (!target) return;
  const coreRows = [
    ...(buckets.get("core-critical") || []),
    ...(buckets.get("shared-core") || []),
  ];
  target.innerHTML = [
    overviewCard("Services", buckets.get("services") || []),
    overviewCard("Core platform", coreRows),
    overviewCard("Security controls", buckets.get("security-controls") || []),
    overviewCard("Support", buckets.get("support") || []),
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

export async function organizeHealthRows(data) {
  const list = document.getElementById("health-checks");
  const target = document.getElementById("health-services-groups");
  if (!list || !target) return;
  const rows = [...list.querySelectorAll(":scope > [data-service-filter-target]")];
  for (const row of rows) row.remove();
  target.innerHTML = "";

  const topologyData = await topology();
  const buckets = assignRows(rows, data?.checks || {}, topologyData);
  updateOverview(buckets);
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
