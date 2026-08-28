const CORE_HEALTH_KEYS = new Set(["postgres", "redis", "supabase"]);

const BLOCKING_RELATION_TYPES = new Set([
  "dependsOn",
  "consumesApi",
  "routesTo",
  "storesIn",
  "authenticatesVia",
  "partOf",
]);

const FOUNDATION_KINDS = new Set([
  "storage-platform",
  "container-runtime",
  "firewall",
  "edge",
  "network-gateway",
  "reverse-proxy",
]);

const SHARED_DATA_KINDS = new Set([
  "database",
  "cache",
  "key-value-store",
  "object-storage",
  "analytics-database",
  "vector-database",
  "message-broker",
  "search",
  "log-store",
  "metrics-store",
  "trace-store",
]);

const GROUPS = [
  {
    key: "foundation",
    label: "1 · Infrastructure foundations",
    description: "Storage, runtime, firewall and edge components with the broadest failure domain.",
  },
  {
    key: "shared-data",
    label: "2 · Shared data & state",
    description: "Databases, caches and durable state used by dependent services.",
  },
  {
    key: "shared-platform",
    label: "3 · Shared platform services",
    description: "Gateways, runtimes and shared capabilities reused by several consumers.",
  },
  {
    key: "application",
    label: "4 · Applications & consumers",
    description: "User-facing workloads and consumers of the shared layers above.",
  },
  {
    key: "support",
    label: "5 · Support / low blast radius",
    description: "Leaf, observability and support components without required downstream consumers.",
  },
];

const EXTRA_GROUP = {
  key: "external",
  label: "External / optional integrations",
  description: "Checks outside the declared homelab dependency graph or not yet mapped to it.",
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

function collectReachable(start, adjacency) {
  const seen = new Set();
  const pending = [...(adjacency.get(start) || [])];
  while (pending.length > 0) {
    const current = pending.pop();
    if (!current || current === start || seen.has(current)) continue;
    seen.add(current);
    for (const next of adjacency.get(current) || []) {
      if (!seen.has(next)) pending.push(next);
    }
  }
  return seen;
}

function analyzeTopology(topology) {
  const requiredDependencies = new Map();
  const requiredDependents = new Map();
  for (const relation of topology?.relations || []) {
    if (relation?.strength !== "required" || !BLOCKING_RELATION_TYPES.has(relation?.type)) {
      continue;
    }
    if (!requiredDependencies.has(relation.source)) requiredDependencies.set(relation.source, new Set());
    requiredDependencies.get(relation.source).add(relation.target);
    if (!requiredDependents.has(relation.target)) requiredDependents.set(relation.target, new Set());
    requiredDependents.get(relation.target).add(relation.source);
  }

  const analysis = new Map();
  for (const node of topology?.nodes || []) {
    const directDependencies = requiredDependencies.get(node.id)?.size || 0;
    const transitiveDependents = collectReachable(node.id, requiredDependents).size;
    let tier = "support";
    if (FOUNDATION_KINDS.has(node.kind)) tier = "foundation";
    else if ((node.category === "data" || SHARED_DATA_KINDS.has(node.kind)) && transitiveDependents > 0) {
      tier = "shared-data";
    } else if (transitiveDependents > 0) tier = "shared-platform";
    else if (directDependencies > 0) tier = "application";
    analysis.set(node.id, { tier, transitiveDependents });
  }
  return analysis;
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
  if (raw.startsWith("albandrieu_")) return raw.slice("albandrieu_".length).replaceAll("_", "-");
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
    if (candidate && indexes.byId.has(String(candidate))) return indexes.byId.get(String(candidate));
  }

  const nameCandidates = [
    check?.name,
    check?.display_label,
    row?.dataset?.serviceName,
  ];
  for (const candidate of nameCandidates) {
    const name = normalize(candidate);
    if (name && indexes.byName.has(name)) return indexes.byName.get(name);
  }

  const urls = [
    check?.url,
    check?.tunnel_url,
    check?.tunnelUrl,
    row?.dataset?.serviceUrl,
    ...(Array.isArray(check?.aliases_probed) ? check.aliases_probed : []),
  ];
  for (const value of urls) {
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

function serviceGroupSection(definition, rows) {
  const section = document.createElement("section");
  section.className = "service-group";
  section.dataset.serviceGroup = definition.key;
  const heading = document.createElement("div");
  heading.className = "service-group-heading";
  heading.innerHTML = `<div><h4>${definition.label}</h4><p>${definition.description}</p></div><span>${rows.length} service${rows.length === 1 ? "" : "s"}</span>`;
  const list = document.createElement("ul");
  list.className = "health-checks service-group-list";
  rows
    .sort((left, right) => (left.textContent || "").localeCompare(right.textContent || ""))
    .forEach((row) => list.appendChild(row));
  section.append(heading, list);
  return section;
}

function assignRows(rows, checks, topologyData) {
  const indexes = topologyIndexes(topologyData);
  const analysis = analyzeTopology(topologyData);
  const buckets = new Map([...GROUPS, EXTRA_GROUP].map((group) => [group.key, []]));
  for (const row of rows) {
    const key = row.dataset.serviceKey || "";
    const check = checks?.[key] || {};
    const node = findTopologyNode(row, check, indexes);
    const tier = node ? analysis.get(node.id)?.tier || "support" : "external";
    row.dataset.criticalityTier = tier;
    const group = GROUPS.find((item) => item.key === tier) || EXTRA_GROUP;
    row.dataset.searchText = `${row.dataset.searchText || ""} ${group.label} ${group.description}`.toLowerCase();
    buckets.get(group.key).push(row);
  }
  return buckets;
}

function refreshFilter() {
  const tokens = normalize(activeFilter).split(/\s+/).filter(Boolean);
  for (const target of document.querySelectorAll("[data-service-filter-target]")) {
    const haystack = normalize(target.dataset.searchText || target.textContent || "");
    target.hidden = tokens.length > 0 && !tokens.every((token) => haystack.includes(token));
  }
  for (const group of document.querySelectorAll("[data-service-group]")) {
    const visible = [...group.querySelectorAll("[data-service-filter-target]")].some((row) => !row.hidden);
    group.hidden = !visible;
  }
  const coreHeading = document.getElementById("health-core-group-heading");
  if (coreHeading) {
    const coreRows = [...document.querySelectorAll("#health-checks > [data-service-filter-target]")];
    coreHeading.hidden = coreRows.length > 0 && !coreRows.some((row) => !row.hidden);
  }
}

export async function organizeHealthRows(data) {
  const list = document.getElementById("health-checks");
  const target = document.getElementById("health-services-groups");
  if (!list || !target) return;
  const currentRows = [...list.querySelectorAll(":scope > [data-service-filter-target]")];
  const nonCore = currentRows.filter((row) => !CORE_HEALTH_KEYS.has(row.dataset.serviceKey || ""));
  for (const row of nonCore) row.remove();
  target.innerHTML = "";

  const topologyData = await topology();
  const buckets = assignRows(nonCore, data?.checks || {}, topologyData);
  for (const definition of [...GROUPS, EXTRA_GROUP]) {
    const rows = buckets.get(definition.key) || [];
    if (rows.length > 0) target.appendChild(serviceGroupSection(definition, rows));
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
}
