import { fetchHealthBoard } from "./api-health-board.js";
import { fetchTopology } from "./api-topology-data.js";

const ROW_SELECTOR = ".health-row[data-service-filter-target]";
const FUNCTIONAL_RELATION_TYPES = new Set([
  "dependsOn",
  "consumesApi",
  "routesTo",
  "storesIn",
  "authenticatesVia",
  "partOf",
  "exposedBy",
]);
const IMPACT_RELATION_TYPES = new Set([
  ...FUNCTIONAL_RELATION_TYPES,
  "hostedBy",
]);

let latestSnapshot = null;
let latestTopology = null;
let refreshScheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function slug(value) {
  return normalize(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value), window.location.href).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function nodeIndexes(topology) {
  const byId = new Map();
  const byName = new Map();
  const byHost = new Map();
  for (const node of topology?.nodes || []) {
    byId.set(String(node.id), node);
    byName.set(normalize(node.name), node);
    for (const value of [
      node.url,
      node.internalUrl,
      ...(Array.isArray(node.environments)
        ? node.environments.map((environment) => environment?.url)
        : []),
    ]) {
      const host = hostOf(value);
      if (host && !byHost.has(host)) byHost.set(host, node);
    }
  }
  return { byId, byName, byHost };
}

function candidateIdFromKey(key) {
  const raw = String(key || "");
  if (raw.startsWith("albandrieu_")) {
    return raw.slice("albandrieu_".length).replaceAll("_", "-");
  }
  return raw.replaceAll("_", "-");
}

function findNode(row, indexes) {
  for (const value of [
    row.dataset.topologyId,
    row.dataset.serviceKey,
    candidateIdFromKey(row.dataset.serviceKey),
  ]) {
    if (value && indexes.byId.has(String(value))) {
      return indexes.byId.get(String(value));
    }
  }
  const name = normalize(row.dataset.serviceName);
  if (name && indexes.byName.has(name)) return indexes.byName.get(name);
  const host = hostOf(row.dataset.serviceUrl);
  return host ? indexes.byHost.get(host) || null : null;
}

function checkMatchesRow(check, row, node = null) {
  if (!check) return false;
  const ids = [check.id, check.service_id, check.serviceId]
    .map(slug)
    .filter(Boolean);
  const rowIds = [
    row.dataset.serviceKey,
    candidateIdFromKey(row.dataset.serviceKey),
    node?.id,
  ]
    .map(slug)
    .filter(Boolean);
  if (rowIds.some((value) => ids.includes(value))) return true;

  const names = [check.name, check.display_label].map(normalize).filter(Boolean);
  if (names.includes(normalize(row.dataset.serviceName))) return true;

  const rowHost = hostOf(row.dataset.serviceUrl);
  if (!rowHost) return false;
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  return [check.url, check.tunnel_url, check.tunnelUrl, ...aliases]
    .map(hostOf)
    .filter(Boolean)
    .includes(rowHost);
}

function findCheck(collection, row, node = null) {
  if (!collection) return null;
  const direct = collection[row.dataset.serviceKey];
  if (direct) return direct;
  const values = Array.isArray(collection)
    ? collection
    : Object.values(collection);
  return values.find((check) => checkMatchesRow(check, row, node)) || null;
}

function serviceEvidence(snapshot, row, node) {
  return {
    health: findCheck(snapshot?.healthz?.checks, row, node),
    homelab: findCheck(snapshot?.homelab?.services, row, node),
    exposure: findCheck(snapshot?.sickz?.checks, row, node),
  };
}

function truenasApps(snapshot) {
  const candidates = [
    snapshot?.homelab?.truenas?.api?.apps,
    snapshot?.healthz?.checks?.truenas_api?.apps,
  ];
  return candidates.find(Array.isArray) || [];
}

function containerRows(app) {
  const workloads = app?.active_workloads || {};
  if (Array.isArray(workloads.container_details)) {
    return workloads.container_details;
  }
  return Array.isArray(app?.containers) ? app.containers : [];
}

function findRuntimeApp(snapshot, evidence, node) {
  const apps = truenasApps(snapshot);
  if (apps.length === 0) return null;
  const candidates = new Set(
    [
      evidence.homelab?.runtime_app,
      node?.runtime?.appId,
      node?.runtime?.containerService,
      node?.id,
      node?.name,
    ]
      .map(slug)
      .filter(Boolean),
  );
  const matches = apps.filter((app) => {
    const identities = new Set(
      [app.id, app.app_id, app.name].map(slug).filter(Boolean),
    );
    for (const container of containerRows(app)) {
      if (container?.service_name) identities.add(slug(container.service_name));
    }
    return [...candidates].some((candidate) => identities.has(candidate));
  });
  return matches.length === 1 ? matches[0] : null;
}

function runtimeTone(value) {
  const state = normalize(value);
  if (["active", "healthy", "running", "started", "up"].includes(state)) {
    return "ok";
  }
  if (["deploying", "starting", "restarting", "stopping"].includes(state)) {
    return "warn";
  }
  if (
    [
      "crashed",
      "dead",
      "down",
      "error",
      "exited",
      "failed",
      "stopped",
    ].includes(state)
  ) {
    return "fail";
  }
  return "unknown";
}

function addRuntimeBadge(tags, text, tone, detail) {
  const badge = document.createElement("span");
  badge.className = `health-meta-badge health-runtime-badge health-runtime-badge--${tone}`;
  badge.dataset.runtimeBadge = "true";
  badge.textContent = text;
  badge.title = detail;
  badge.setAttribute("aria-label", detail);
  tags.appendChild(badge);
}

function decorateRuntime(row, snapshot, evidence, node) {
  const tags = row.querySelector(".health-row-tags");
  if (!tags) return;
  tags
    .querySelectorAll("[data-runtime-badge]")
    .forEach((badge) => badge.remove());

  const app = findRuntimeApp(snapshot, evidence, node);
  const runtimeState = app?.state || evidence.homelab?.runtime_state;
  if (runtimeState) {
    addRuntimeBadge(
      tags,
      `App ${String(runtimeState).toUpperCase()}`,
      runtimeTone(runtimeState),
      `TrueNAS application runtime state: ${runtimeState}. Runtime state is independent from HTTP, TLS, Cloudflare and dependency health.`,
    );
  }
  if (!app) return;

  const containers = containerRows(app);
  for (const container of containers.slice(0, 8)) {
    const state =
      container?.health || container?.state || container?.status || "unknown";
    const name = container?.service_name || "container";
    const image = container?.image ? ` · image ${container.image}` : "";
    addRuntimeBadge(
      tags,
      `🐳 ${name} ${String(state).toUpperCase()}`,
      runtimeTone(state),
      `TrueNAS/Docker container ${name}: ${state}${image}`,
    );
  }
  if (containers.length > 8) {
    addRuntimeBadge(
      tags,
      `+${containers.length - 8} containers`,
      "unknown",
      `${containers.length} containers are reported for this TrueNAS application; the first 8 are shown inline.`,
    );
  }
}

function ensureProbeStrip(row) {
  const primary = row.querySelector(".health-row-primary");
  if (!primary) return null;
  let strip = primary.querySelector(":scope > .service-probe-strip");
  if (!strip) {
    strip = document.createElement("div");
    strip.className = "service-probe-strip";
    strip.setAttribute("aria-label", "Probe evidence");
    primary.appendChild(strip);
  }
  return strip;
}

function diagnosticBadge(kind, tone, icon, label, detail) {
  const badge = document.createElement("span");
  badge.className = `service-probe service-probe--${tone} service-probe--operator`;
  badge.dataset.probeKind = kind;
  badge.title = detail;
  badge.setAttribute("aria-label", detail);

  const iconNode = document.createElement("span");
  iconNode.className = "service-probe-icon";
  iconNode.setAttribute("aria-hidden", "true");
  iconNode.textContent = icon;
  const text = document.createElement("span");
  text.className = "service-probe-label";
  text.textContent = label;
  badge.append(iconNode, text);
  return badge;
}

function replaceOperatorProbe(strip, kind, badge) {
  strip.querySelector(`[data-operator-probe="${kind}"]`)?.remove();
  badge.dataset.operatorProbe = kind;
  strip.appendChild(badge);
}

function metricEvidence(evidence, node) {
  const health = evidence.health || evidence.homelab || {};
  const monitoring = node?.monitoring || {};
  const candidates = [
    monitoring.url,
    monitoring.target,
    health.url,
    health.path,
  ].filter(Boolean);
  const target = candidates.find((value) => /\/metrics(?:$|[?#])/i.test(String(value))) || "";
  const values = [
    health.prometheus_up,
    health.metrics_up,
    health.telemetry_available,
    health.metrics_available,
  ];
  return {
    declared: Boolean(target),
    target: String(target),
    values,
    observed: values.some((value) => value === true || value === false),
  };
}

function decorateExposureAndMetrics(row, evidence, node) {
  const strip = ensureProbeStrip(row);
  if (!strip) return;

  const external = evidence.exposure?.external;
  if (typeof external === "boolean") {
    replaceOperatorProbe(
      strip,
      "external",
      diagnosticBadge(
        "external",
        external ? "ok" : "fail",
        "🌍",
        `external=${String(external)}`,
        external
          ? "Declared exposure: external=true. The service is expected to have an externally reachable entry point subject to its ingress/security policy."
          : "Declared exposure: external=false. The service is intended to remain internal-only; red is used here as the requested visual boolean, not as an outage verdict.",
      ),
    );
  }

  const metrics = metricEvidence(evidence, node);
  if (metrics.declared || metrics.observed) {
    let tone = "unknown";
    if (metrics.values.some((value) => value === true)) tone = "ok";
    else if (metrics.values.some((value) => value === false)) tone = "fail";

    strip
      .querySelectorAll('[data-probe-kind="metrics"]')
      .forEach((badge) => badge.remove());
    replaceOperatorProbe(
      strip,
      "prometheus",
      diagnosticBadge(
        "metrics",
        tone,
        "📈",
        "Prometheus",
        [
          metrics.declared
            ? `Declared metrics endpoint: ${metrics.target}`
            : "Prometheus/metrics evidence is present.",
          tone === "ok"
            ? "Metrics evidence is available."
            : tone === "fail"
              ? "Metrics evidence reports unavailable."
              : "Metrics endpoint is declared but current Prometheus evidence is not confirmed.",
        ].join(" "),
      ),
    );
  }
}

function cleanDuplicatedExposureNote(row) {
  const note = row.querySelector(".health-meta-note");
  if (!note) return;
  const duplicatePatterns = [
    /^external=(true|false)$/i,
    /^Cloudflare expected$/i,
    /^Cloudflare (not )?observed$/i,
    /^Cloudflare Default-Deny$/i,
    /^Service token Access /i,
    /^\d+ Access polic(?:y|ies)$/i,
    /^direct exposure \/ no Cloudflare$/i,
    /^security mode unspecified$/i,
  ];
  const remaining = String(note.textContent || "")
    .split(" · ")
    .map((part) => part.trim())
    .filter(Boolean)
    .filter(
      (part) =>
        !duplicatePatterns.some((pattern) => pattern.test(part)),
    );
  if (remaining.length === 0) note.remove();
  else note.textContent = remaining.join(" · ");
}

function reverseImpactAdjacency(topology) {
  const adjacency = new Map();
  for (const relation of topology?.relations || []) {
    if (
      relation?.strength !== "required" ||
      !IMPACT_RELATION_TYPES.has(relation?.type)
    ) {
      continue;
    }
    if (!adjacency.has(relation.target)) {
      adjacency.set(relation.target, new Set());
    }
    adjacency.get(relation.target).add(relation.source);
  }
  return adjacency;
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
  return [...seen];
}

function assignAnchors(rows, indexes) {
  const canonical = new Map();
  for (const row of rows) {
    const node = findNode(row, indexes);
    if (!node) continue;
    row.dataset.topologyId = node.id;
    const exposureRow = Boolean(row.closest("#sickz-checks"));
    const preferredId = exposureRow
      ? `service-exposure-${node.id}`
      : `service-${node.id}`;
    row.id = preferredId;
    if (!exposureRow || !canonical.has(node.id)) {
      canonical.set(node.id, preferredId);
    }
  }
  return canonical;
}

function createLinkedList(title, ids, indexes, anchors) {
  const container = document.createElement("div");
  container.className = "service-hover-list";
  const heading = document.createElement("strong");
  heading.textContent = title;
  container.appendChild(heading);
  if (ids.length === 0) {
    const empty = document.createElement("span");
    empty.textContent = "None declared";
    container.appendChild(empty);
    return container;
  }
  for (const id of ids) {
    const node = indexes.byId.get(id);
    const link = document.createElement("a");
    link.href = `#${anchors.get(id) || `service-${id}`}`;
    link.textContent = node?.name || id;
    link.title = `${node?.name || id} · ${node?.kind || "service"}`;
    container.appendChild(link);
  }
  return container;
}

function decorateDownstream(row, node, topology, indexes, anchors) {
  const tags = row.querySelector(".health-row-tags");
  if (!tags || !node) return;
  const downstream = collectReachable(
    node.id,
    reverseImpactAdjacency(topology),
  );
  let badge = tags.querySelector(".health-meta-badge--impact");
  if (downstream.length === 0) {
    badge?.querySelector(".service-hover-popover")?.remove();
    return;
  }
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "health-meta-badge health-meta-badge--impact";
    tags.appendChild(badge);
  }
  badge.classList.add("health-downstream-badge");
  badge.textContent = `${downstream.length} downstream`;
  badge.tabIndex = 0;
  badge.setAttribute(
    "aria-label",
    `${downstream.length} downstream dependent services; hover or focus for links`,
  );
  const popover = document.createElement("span");
  popover.className = "service-hover-popover";
  popover.appendChild(
    createLinkedList("Downstream impact", downstream, indexes, anchors),
  );
  badge.appendChild(popover);
}

function helpSummary(evidence, node, runtimeApp) {
  const lines = [
    "Runtime, reachability, dependencies and edge security are independent evidence layers.",
  ];
  const runtimeState = runtimeApp?.state || evidence.homelab?.runtime_state;
  if (runtimeState) lines.push(`TrueNAS app: ${runtimeState}`);
  if (evidence.homelab?.local_state) {
    lines.push(`Local health: ${evidence.homelab.local_state}`);
  }
  if (evidence.homelab?.effective_state) {
    lines.push(`Effective health: ${evidence.homelab.effective_state}`);
  }
  if (typeof evidence.exposure?.external === "boolean") {
    lines.push(`Exposure: external=${String(evidence.exposure.external)}`);
  }
  if (node?.monitoring) {
    const target =
      node.monitoring.url ||
      node.monitoring.target ||
      [node.monitoring.host, node.monitoring.port].filter(Boolean).join(":");
    lines.push(
      `Monitoring: ${node.monitoring.type}${target ? ` · ${target}` : ""}`,
    );
  }
  return lines;
}

function decorateHelp(row, evidence, node, runtimeApp) {
  const tags = row.querySelector(".health-row-tags");
  if (!tags) return;
  tags.querySelector(".service-help-badge")?.remove();
  const badge = document.createElement("span");
  badge.className = "service-help-badge";
  badge.tabIndex = 0;
  badge.textContent = "?";
  badge.setAttribute("role", "note");
  badge.setAttribute(
    "aria-label",
    `How to read diagnostics for ${row.dataset.serviceName || node?.name || "service"}`,
  );
  const popover = document.createElement("span");
  popover.className = "service-hover-popover service-help-popover";
  const heading = document.createElement("strong");
  heading.textContent = "How to read this service";
  popover.appendChild(heading);
  for (const line of helpSummary(evidence, node, runtimeApp)) {
    const detail = document.createElement("span");
    detail.textContent = line;
    popover.appendChild(detail);
  }
  badge.appendChild(popover);
  tags.appendChild(badge);
}

function relationData(topology, nodeId) {
  const dependencies = [];
  const downstream = [];
  for (const relation of topology?.relations || []) {
    if (
      relation.source === nodeId &&
      FUNCTIONAL_RELATION_TYPES.has(relation.type)
    ) {
      dependencies.push(relation);
    }
    if (
      relation.target === nodeId &&
      IMPACT_RELATION_TYPES.has(relation.type)
    ) {
      downstream.push(relation);
    }
  }
  return { dependencies, downstream };
}

function drawerRelationSection(
  title,
  relations,
  direction,
  indexes,
  anchors,
) {
  const block = document.createElement("div");
  block.className = "service-detail-relation-block";
  const heading = document.createElement("strong");
  heading.textContent = title;
  block.appendChild(heading);
  if (relations.length === 0) {
    const empty = document.createElement("span");
    empty.className = "service-detail-empty";
    empty.textContent = "None declared";
    block.appendChild(empty);
    return block;
  }
  const list = document.createElement("ul");
  for (const relation of relations) {
    const id = direction === "target" ? relation.target : relation.source;
    const node = indexes.byId.get(id);
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `#${anchors.get(id) || `service-${id}`}`;
    link.textContent = node?.name || id;
    const meta = document.createElement("span");
    meta.textContent = `${relation.type} · ${relation.strength || "required"}`;
    item.append(link, meta);
    list.appendChild(item);
  }
  block.appendChild(list);
  return block;
}

function metricItem(label, value) {
  if (value == null || value === "") return null;
  const item = document.createElement("div");
  item.className = "service-detail-metric";
  const term = document.createElement("span");
  term.textContent = label;
  const content = document.createElement("strong");
  content.textContent = String(value);
  item.append(term, content);
  return item;
}

function addDrawerSection(host, title, id) {
  const section = document.createElement("section");
  section.dataset.operatorSection = id;
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.appendChild(heading);
  host.appendChild(section);
  return section;
}

function renderRuntimeSection(body, runtimeApp, evidence) {
  const runtime = addDrawerSection(
    body,
    "TrueNAS / Docker runtime",
    "runtime",
  );
  const grid = document.createElement("div");
  grid.className = "service-detail-metrics";
  [
    metricItem("App", runtimeApp?.name || evidence.homelab?.runtime_app),
    metricItem(
      "App state",
      runtimeApp?.state || evidence.homelab?.runtime_state,
    ),
    metricItem("Runtime reachable", evidence.homelab?.runtime_reachable),
    metricItem("Runtime stale", evidence.homelab?.runtime_stale),
  ]
    .filter(Boolean)
    .forEach((item) => grid.appendChild(item));
  runtime.appendChild(grid);

  const containers = containerRows(runtimeApp);
  if (containers.length === 0) return;
  const list = document.createElement("ul");
  list.className = "service-detail-container-list";
  for (const container of containers) {
    const item = document.createElement("li");
    const state =
      container?.health || container?.state || container?.status || "unknown";
    const name = container?.service_name || "container";
    item.textContent = `${name} · ${state}${container?.image ? ` · ${container.image}` : ""}`;
    list.appendChild(item);
  }
  runtime.appendChild(list);
}

function renderRelationsSection(body, topology, node, indexes, anchors) {
  if (!node) return;
  const relations = relationData(topology, node.id);
  const section = addDrawerSection(
    body,
    "Dependencies & downstream",
    "dependencies",
  );
  const grid = document.createElement("div");
  grid.className = "service-detail-relations";
  grid.append(
    drawerRelationSection(
      "Depends on",
      relations.dependencies,
      "target",
      indexes,
      anchors,
    ),
    drawerRelationSection(
      "Direct downstream",
      relations.downstream,
      "source",
      indexes,
      anchors,
    ),
  );
  const allDownstream = collectReachable(
    node.id,
    reverseImpactAdjacency(topology),
  );
  grid.appendChild(
    createLinkedList(
      "Transitive downstream",
      allDownstream,
      indexes,
      anchors,
    ),
  );
  section.appendChild(grid);
}

function renderPerformanceSection(body, evidence, node) {
  const section = addDrawerSection(body, "Service performance", "performance");
  const grid = document.createElement("div");
  grid.className = "service-detail-metrics";
  const health = evidence.homelab || evidence.health || {};
  const metrics = [
    metricItem(
      "Probe latency",
      health.latency_ms != null
        ? `${health.latency_ms} ms`
        : health.elapsed_ms != null
          ? `${health.elapsed_ms} ms`
          : null,
    ),
    metricItem(
      "Evidence age",
      health.observation_age_seconds != null
        ? `${health.observation_age_seconds} s`
        : null,
    ),
    metricItem(
      "Direct probe age",
      health.direct_probe_age_seconds != null
        ? `${health.direct_probe_age_seconds} s`
        : null,
    ),
    metricItem(
      "Internal probe age",
      health.internal_probe_age_seconds != null
        ? `${health.internal_probe_age_seconds} s`
        : null,
    ),
    metricItem(
      "Probe interval",
      health.probe_interval_seconds != null
        ? `${health.probe_interval_seconds} s`
        : null,
    ),
    metricItem(
      "Next probe",
      health.next_probe_in_seconds != null
        ? `${health.next_probe_in_seconds} s`
        : null,
    ),
    metricItem(
      "Prometheus target",
      metricEvidence(evidence, node).target || null,
    ),
  ].filter(Boolean);
  metrics.forEach((item) => grid.appendChild(item));
  section.appendChild(grid);
  if (metrics.length === 0) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent =
      "No per-service timing/metrics evidence is currently attached to this row.";
    section.appendChild(empty);
  }
}

function renderEnhancedDrawer(row, snapshot, topology, indexes, anchors) {
  const drawer = document.getElementById("service-detail-drawer");
  const body = drawer?.querySelector(".service-detail-body");
  if (!body || !row) return;
  body
    .querySelectorAll("[data-operator-section]")
    .forEach((section) => section.remove());

  const node = findNode(row, indexes);
  const evidence = serviceEvidence(snapshot, row, node);
  const runtimeApp = findRuntimeApp(snapshot, evidence, node);
  renderRuntimeSection(body, runtimeApp, evidence);
  renderRelationsSection(body, topology, node, indexes, anchors);
  renderPerformanceSection(body, evidence, node);
}

function decorateRows(snapshot, topology) {
  const rows = [...document.querySelectorAll(ROW_SELECTOR)];
  if (rows.length === 0) return;
  const indexes = nodeIndexes(topology);
  const anchors = assignAnchors(rows, indexes);

  for (const row of rows) {
    const node = findNode(row, indexes);
    const evidence = serviceEvidence(snapshot, row, node);
    const runtimeApp = findRuntimeApp(snapshot, evidence, node);
    decorateRuntime(row, snapshot, evidence, node);
    decorateExposureAndMetrics(row, evidence, node);
    cleanDuplicatedExposureNote(row);
    decorateDownstream(row, node, topology, indexes, anchors);
    decorateHelp(row, evidence, node, runtimeApp);
  }

  const selected = document.querySelector(
    `${ROW_SELECTOR}[data-detail-selected="true"]`,
  );
  if (selected) {
    renderEnhancedDrawer(selected, snapshot, topology, indexes, anchors);
  }
}

async function refreshDiagnostics() {
  try {
    const [snapshot, topology] = await Promise.all([
      fetchHealthBoard(),
      fetchTopology(),
    ]);
    latestSnapshot = snapshot;
    latestTopology = topology;
    decorateRows(snapshot, topology);
  } catch {
    // Base health UI remains authoritative if additive diagnostics cannot load.
  }
}

function scheduleRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    if (latestSnapshot && latestTopology) {
      decorateRows(latestSnapshot, latestTopology);
    } else {
      refreshDiagnostics();
    }
  });
}

function schedulePostRenderPasses() {
  scheduleRefresh();
  window.setTimeout(scheduleRefresh, 120);
  window.setTimeout(scheduleRefresh, 500);
}

function installDrawerEnhancement() {
  document.addEventListener(
    "click",
    (event) => {
      const trigger =
        event.target instanceof Element
          ? event.target.closest(".service-detail-trigger")
          : null;
      const row = trigger?.closest(ROW_SELECTOR);
      if (!row) return;
      window.setTimeout(() => {
        if (!latestSnapshot || !latestTopology) return;
        const indexes = nodeIndexes(latestTopology);
        const anchors = assignAnchors(
          [...document.querySelectorAll(ROW_SELECTOR)],
          indexes,
        );
        renderEnhancedDrawer(
          row,
          latestSnapshot,
          latestTopology,
          indexes,
          anchors,
        );
      }, 0);
    },
    true,
  );
}

export function installServiceOperatorDiagnostics() {
  installDrawerEnhancement();
  document.addEventListener("health-board-refreshed", () => {
    refreshDiagnostics().then(schedulePostRenderPasses);
  });
  schedulePostRenderPasses();
}
