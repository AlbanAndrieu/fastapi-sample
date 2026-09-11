import { fetchHealthBoard } from "./api-health-board.js";

const STATUS_OPTIONS = [
  ["all", "All statuses"],
  ["operational", "Operational"],
  ["at-risk", "At risk"],
  ["degraded", "Degraded"],
  ["down", "Down"],
  ["unknown", "Unknown"],
  ["issues", "Issues only"],
];

const EXPOSURE_OPTIONS = [
  ["all", "All exposure policies"],
  ["ok", "Policy compliant"],
  ["warn", "Policy warning"],
  ["fail", "Policy violation"],
  ["unknown", "Policy unknown"],
  ["unobserved", "No exposure evidence"],
  ["external", "External services"],
  ["internal", "Internal-only services"],
  ["cloudflare", "Cloudflare protected"],
  ["direct", "Direct / no tunnel"],
];

const PROBE_OPTIONS = [
  ["all", "All probe types"],
  ["http", "HTTP"],
  ["tls", "HTTPS / TLS"],
  ["tcp", "TCP"],
  ["api", "REST API"],
  ["websocket", "WebSocket"],
  ["cloudflare", "Cloudflare Tunnel"],
  ["access", "Cloudflare Access"],
  ["service-token", "Service Token"],
  ["metrics", "Prometheus / metrics"],
];

const PROBE_ICONS = {
  http: "🌐",
  tls: "🔒",
  tcp: "🔌",
  api: "⚙️",
  websocket: "↔️",
  cloudflare: "☁️",
  access: "🛡️",
  "service-token": "🔑",
  metrics: "📈",
  policy: "🛡️",
};

const LEGEND_ITEMS = [
  ["🌐", "HTTP"],
  ["🔒", "TLS certificate"],
  ["🔌", "TCP"],
  ["⚙️", "REST API"],
  ["↔️", "WebSocket"],
  ["☁️", "Cloudflare Tunnel"],
  ["🛡️", "Access / policy"],
  ["🔑", "Service Token"],
  ["📈", "Prometheus / metrics"],
];

const filters = {
  query: "",
  status: "all",
  exposure: "all",
  probe: "all",
};

let latestSnapshot = null;
let refreshScheduled = false;
let decorating = false;

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

function urlOf(check) {
  const aliases = Array.isArray(check?.aliases_probed)
    ? check.aliases_probed
    : [];
  const candidates = [
    check?.tunnel_url,
    check?.tunnelUrl,
    check?.href,
    check?.url,
    ...aliases,
  ];
  for (const value of candidates) {
    if (value && String(value).trim()) return String(value).trim();
  }
  return "";
}

function checkMatchesRow(check, row) {
  if (!check || !row) return false;

  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const rowHost = hostOf(row.dataset.serviceUrl);
  const ids = [check.service_id, check.serviceId, check.id]
    .map(normalize)
    .filter(Boolean);
  const names = [check.name, check.display_label]
    .map(normalize)
    .filter(Boolean);
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  const hosts = [check.url, check.tunnel_url, check.tunnelUrl, ...aliases]
    .map(hostOf)
    .filter(Boolean);

  return (
    ids.includes(key) ||
    names.includes(name) ||
    Boolean(rowHost && hosts.includes(rowHost))
  );
}

function findCheck(checks, row) {
  if (!checks || !row) return null;
  const key = row.dataset.serviceKey;
  if (key && checks[key]) return checks[key];
  for (const check of Object.values(checks)) {
    if (checkMatchesRow(check, row)) return check;
  }
  return null;
}

function normalizedPolicy(check) {
  const policy = normalize(check?.policy_status);
  if (["ok", "warn", "fail", "unknown"].includes(policy)) return policy;
  return "unknown";
}

function normalizedStatus(row) {
  const explicit = normalize(row.dataset.semanticStatus);
  if (explicit) return explicit;
  if (row.querySelector(".health-led--red")) return "down";
  if (row.querySelector(".health-led--yellow, .health-led--blue")) {
    return "degraded";
  }
  if (row.querySelector(".health-led--gray")) return "unknown";
  if (row.querySelector(".health-led--green")) return "operational";
  return "unknown";
}

function reachabilityTone(check) {
  if (!check) return "unknown";
  if (check.skipped === true) return "neutral";
  if (check.reachable === false) return "fail";
  if (check.reachable == null) return "unknown";

  const status = Number(check.http_status);
  if (!Number.isFinite(status)) {
    return check.reachable === true ? "ok" : "unknown";
  }
  if (status >= 200 && status < 400) return "ok";
  if (status >= 500) return "fail";
  return "warn";
}

function policyTone(policy) {
  if (policy === "ok") return "ok";
  if (policy === "warn") return "warn";
  if (policy === "fail") return "fail";
  return "unknown";
}

function probeBadge(kind, tone, label, detail) {
  const badge = document.createElement("span");
  badge.className = `service-probe service-probe--${tone}`;
  badge.dataset.probeKind = kind;
  badge.title = detail || label;
  badge.setAttribute("aria-label", detail || label);

  const icon = document.createElement("span");
  icon.className = "service-probe-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = PROBE_ICONS[kind] || "•";

  const text = document.createElement("span");
  text.className = "service-probe-label";
  text.textContent = label;
  badge.append(icon, text);
  return badge;
}

function httpDetail(check, suffix) {
  if (check.reachable === true) {
    return `HTTP probe reached the target${suffix}`;
  }
  if (check.reachable === false) {
    const error = check.error ? `: ${check.error}` : "";
    return `HTTP probe could not reach the target${error}`;
  }
  const warning = check.warning ? `: ${check.warning}` : "";
  return `HTTP probe result is not confirmed${warning}`;
}

function addHttpEvidence(target, check, kinds) {
  if (!check) return;
  const url = urlOf(check);
  const probe = normalize(check.probe);
  const hasHttp =
    /^https?:\/\//i.test(url) ||
    check.http_status != null ||
    probe.includes("http");
  if (!hasHttp) return;

  const status = Number(check.http_status);
  const label = Number.isFinite(status) ? `HTTP ${status}` : "HTTP";
  const suffix = Number.isFinite(status) ? ` with status ${status}` : "";
  target.appendChild(
    probeBadge("http", reachabilityTone(check), label, httpDetail(check, suffix)),
  );
  kinds.add("http");
}

function addTlsEvidence(target, check, kinds) {
  if (!check) return;
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  const hasHttps =
    /^https:\/\//i.test(urlOf(check)) ||
    aliases.some((value) => /^https:\/\//i.test(String(value)));
  if (!hasHttps) return;

  let tone = "unknown";
  let detail = "HTTPS target exists but TLS trust was not confirmed";
  if (check.skipped === true) {
    tone = "neutral";
    detail = "TLS validation was intentionally skipped from this vantage point";
  } else if (check.tls_trusted === true) {
    tone = "ok";
    detail = "HTTPS certificate chain and hostname were validated";
  } else if (check.tls_trusted === false) {
    tone = "fail";
    detail = "HTTPS certificate validation failed";
  }

  target.appendChild(probeBadge("tls", tone, "TLS", detail));
  kinds.add("tls");
}

function addTcpEvidence(target, check, kinds) {
  if (!check) return;
  const probe = normalize(check.probe);
  const protocol = normalize(check.protocol);
  const url = urlOf(check);
  const hasTcp =
    probe.includes("tcp") ||
    protocol === "tcp" ||
    Boolean(check.host && check.port != null && !/^https?:\/\//i.test(url));
  if (!hasTcp) return;

  const endpoint =
    check.host && check.port != null ? ` ${check.host}:${check.port}` : "";
  const error = check.error ? `: ${check.error}` : "";
  target.appendChild(
    probeBadge(
      "tcp",
      reachabilityTone(check),
      "TCP",
      `TCP connectivity probe${endpoint}${error}`,
    ),
  );
  kinds.add("tcp");
}

function addApiEvidence(target, key, check, kinds) {
  if (!check) return;
  const probe = normalize(check.probe);
  const path = String(check.path || "");
  const hasApi =
    probe.includes("api") ||
    path.startsWith("/api/") ||
    ["pfsense", "truenas_api"].includes(String(key || ""));
  if (!hasApi) return;

  const detail = `Authenticated/read-only API evidence${path ? ` via ${path}` : ""}`;
  target.appendChild(
    probeBadge("api", reachabilityTone(check), "API", detail),
  );
  kinds.add("api");

  const hasWebsocket =
    probe.includes("websocket") || String(key || "") === "truenas_api";
  if (!hasWebsocket) return;
  target.appendChild(
    probeBadge(
      "websocket",
      reachabilityTone(check),
      "WS",
      "WebSocket API connectivity evidence",
    ),
  );
  kinds.add("websocket");
}

function tunnelEvidence(exposure) {
  const expected = exposure.tunnel_secure === true;
  const observed = exposure.cloudflare_tunnel_observed;
  if (expected && observed === true) {
    return ["ok", "Cloudflare Tunnel is expected and observed"];
  }
  if (expected && observed === false) {
    return ["fail", "Cloudflare Tunnel is expected but was not observed"];
  }
  if (!expected && observed === true) {
    return [
      "warn",
      "Cloudflare Tunnel was observed although direct exposure is declared",
    ];
  }
  if (exposure.tunnel_secure === false) {
    return [
      "neutral",
      "Cloudflare Tunnel is not required by the declared exposure policy",
    ];
  }
  return ["unknown", "Cloudflare Tunnel evidence is not confirmed"];
}

function accessEvidence(exposure) {
  const policyCount = Number(exposure.cloudflare_access_policy_count);
  const hasCount = Number.isFinite(policyCount);
  let tone = "unknown";
  if (exposure.cloudflare_default_deny === true && policyCount > 0) {
    tone = "ok";
  } else if (
    exposure.cloudflare_default_deny === true &&
    policyCount === 0
  ) {
    tone = "fail";
  } else if (hasCount) {
    tone = policyCount > 0 ? "ok" : "warn";
  }

  const countDetail = hasCount
    ? ` · ${policyCount} ${policyCount === 1 ? "policy" : "policies"}`
    : "";
  return [
    tone,
    `Cloudflare Access Default-Deny=${String(exposure.cloudflare_default_deny)}${countDetail}`,
  ];
}

function addCloudflareEvidence(target, exposure, kinds) {
  if (!exposure) return;
  const hasTunnel =
    exposure.tunnel_secure != null ||
    exposure.cloudflare_tunnel_observed != null ||
    exposure.cloudflare_default_deny != null ||
    exposure.cloudflare_access_policy_count != null;
  if (!hasTunnel) return;

  const [tunnelTone, tunnelDetail] = tunnelEvidence(exposure);
  target.appendChild(
    probeBadge("cloudflare", tunnelTone, "Tunnel", tunnelDetail),
  );
  kinds.add("cloudflare");

  const hasAccess =
    exposure.cloudflare_default_deny != null ||
    Number.isFinite(Number(exposure.cloudflare_access_policy_count));
  if (hasAccess) {
    const [accessTone, accessDetail] = accessEvidence(exposure);
    target.appendChild(
      probeBadge("access", accessTone, "Access", accessDetail),
    );
    kinds.add("access");
  }

  if (exposure.cloudflare_service_auth_attempted !== true) return;
  const passed = exposure.cloudflare_service_token_access_passed;
  const httpStatus = Number(exposure.cloudflare_service_token_http_status);
  const statusLabel = Number.isFinite(httpStatus) ? ` ${httpStatus}` : "";
  let tone = "unknown";
  if (passed === true) tone = "ok";
  else if (passed === false) tone = "fail";

  const result =
    passed === true
      ? "authenticated successfully"
      : passed === false
        ? "authentication failed"
        : "result is unknown";
  target.appendChild(
    probeBadge(
      "service-token",
      tone,
      `Token${statusLabel}`,
      `Cloudflare Access Service Token ${result}${statusLabel ? ` · HTTP${statusLabel}` : ""}`,
    ),
  );
  kinds.add("service-token");
}

function metricTone(check) {
  if (!check) return null;
  const values = [
    check.prometheus_up,
    check.metrics_up,
    check.telemetry_available,
    check.metrics_available,
  ];
  if (values.some((value) => value === true)) return "ok";
  if (values.some((value) => value === false)) return "fail";
  const source = normalize(
    [check.source, check.metric_source, check.telemetry_source]
      .filter(Boolean)
      .join(" "),
  );
  return source.includes("prometheus") ? "unknown" : null;
}

function addMetricEvidence(target, check, kinds) {
  const tone = metricTone(check);
  if (!tone) return;

  let detail = "Prometheus/metrics source is declared but current evidence is unknown";
  if (tone === "ok") detail = "Prometheus/metrics evidence is available";
  else if (tone === "fail") {
    detail = "Prometheus/metrics evidence reports unavailable";
  }
  target.appendChild(probeBadge("metrics", tone, "Metrics", detail));
  kinds.add("metrics");
}

function setExposureMetadata(row, exposure) {
  if (!exposure) {
    row.dataset.exposurePolicy = "unobserved";
    row.dataset.exposureScope = "unobserved";
    row.dataset.exposureMode = "unobserved";
    return;
  }

  row.dataset.exposurePolicy = normalizedPolicy(exposure);
  if (exposure.external === true) row.dataset.exposureScope = "external";
  else if (exposure.external === false) row.dataset.exposureScope = "internal";
  else row.dataset.exposureScope = "unknown";

  if (exposure.tunnel_secure === true) {
    row.dataset.exposureMode = "cloudflare";
  } else if (exposure.tunnel_secure === false) {
    row.dataset.exposureMode = "direct";
  } else {
    row.dataset.exposureMode = "unknown";
  }
}

function decorateRow(row, snapshot) {
  const healthChecks = snapshot?.healthz?.checks || {};
  const homelabChecks = snapshot?.homelab?.checks || {};
  const sickzChecks = snapshot?.sickz?.checks || {};
  const key = row.dataset.serviceKey || "";
  const health =
    findCheck(healthChecks, row) || findCheck(homelabChecks, row) || null;
  const exposure = findCheck(sickzChecks, row);
  const primary = row.querySelector(".health-row-primary");
  if (!primary) return;

  setExposureMetadata(row, exposure);
  const kinds = new Set();
  const strip = document.createElement("div");
  strip.className = "service-probe-strip";
  strip.setAttribute("aria-label", "Probe evidence");

  const mainEvidence = health || exposure;
  addHttpEvidence(strip, mainEvidence, kinds);
  addTlsEvidence(strip, exposure || mainEvidence, kinds);
  addTcpEvidence(strip, mainEvidence, kinds);
  addApiEvidence(strip, key, mainEvidence, kinds);
  addCloudflareEvidence(strip, exposure, kinds);
  addMetricEvidence(strip, health, kinds);

  if (exposure?.policy_status) {
    const policy = normalizedPolicy(exposure);
    const detail =
      exposure.policy_detail || `Exposure security policy: ${policy}`;
    strip.appendChild(
      probeBadge("policy", policyTone(policy), "Policy", detail),
    );
  }

  row.dataset.probeKinds = [...kinds].join(" ");
  const signature = strip.textContent + strip.innerHTML;
  const existing = primary.querySelector(":scope > .service-probe-strip");
  if (existing?.dataset.signature === signature) return;
  if (existing) existing.remove();
  strip.dataset.signature = signature;
  if (strip.children.length > 0) primary.appendChild(strip);
}

function selectControl(id, label, options) {
  const wrapper = document.createElement("label");
  wrapper.className = "service-filter-facet";
  wrapper.htmlFor = id;

  const caption = document.createElement("span");
  caption.textContent = label;
  const select = document.createElement("select");
  select.id = id;
  for (const [value, text] of options) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.appendChild(option);
  }
  wrapper.append(caption, select);
  return wrapper;
}

function appendLegend(host) {
  const legend = document.createElement("div");
  legend.id = "service-probe-legend";
  legend.className = "service-probe-legend";

  const title = document.createElement("strong");
  title.textContent = "Probe evidence";
  legend.appendChild(title);
  for (const [icon, label] of LEGEND_ITEMS) {
    const item = document.createElement("span");
    item.textContent = `${icon} ${label}`;
    legend.appendChild(item);
  }
  const help = document.createElement("small");
  help.textContent =
    "green = operational · amber = warning · red = failed · gray = unknown / not confirmed";
  legend.appendChild(help);
  host.appendChild(legend);
}

function ensureFilterControls() {
  const host = document.querySelector(".service-filter");
  if (!host || document.getElementById("service-filter-facets")) return;

  const facets = document.createElement("div");
  facets.id = "service-filter-facets";
  facets.className = "service-filter-facets";
  facets.append(
    selectControl("service-status-filter", "Status", STATUS_OPTIONS),
    selectControl(
      "service-exposure-filter",
      "Exposure security policy",
      EXPOSURE_OPTIONS,
    ),
    selectControl("service-probe-filter", "Probe", PROBE_OPTIONS),
  );
  host.appendChild(facets);

  const result = document.createElement("div");
  result.id = "service-filter-result";
  result.className = "service-filter-result";
  result.setAttribute("aria-live", "polite");
  host.appendChild(result);
  appendLegend(host);
}

function exposureMatches(row) {
  if (filters.exposure === "all") return true;
  if (filters.exposure === "external") {
    return row.dataset.exposureScope === "external";
  }
  if (filters.exposure === "internal") {
    return row.dataset.exposureScope === "internal";
  }
  if (filters.exposure === "cloudflare") {
    return row.dataset.exposureMode === "cloudflare";
  }
  if (filters.exposure === "direct") {
    return row.dataset.exposureMode === "direct";
  }
  return row.dataset.exposurePolicy === filters.exposure;
}

function statusMatches(row) {
  if (filters.status === "all") return true;
  const status = normalizedStatus(row);
  if (filters.status === "issues") return status !== "operational";
  return status === filters.status;
}

function queryMatches(row) {
  const tokens = normalize(filters.query).split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const haystack = normalize(
    [
      row.dataset.searchText,
      row.textContent,
      row.dataset.probeKinds,
      row.dataset.exposurePolicy,
      row.dataset.exposureScope,
      row.dataset.exposureMode,
    ].join(" "),
  );
  return tokens.every((token) => haystack.includes(token));
}

function probeMatches(row) {
  if (filters.probe === "all") return true;
  return String(row.dataset.probeKinds || "")
    .split(/\s+/)
    .includes(filters.probe);
}

function isFiltering() {
  return (
    Boolean(filters.query) ||
    filters.status !== "all" ||
    filters.exposure !== "all" ||
    filters.probe !== "all"
  );
}

function updateGroupVisibility() {
  for (const group of document.querySelectorAll("[data-service-group]")) {
    const rows = [...group.querySelectorAll("[data-service-filter-target]")];
    const visible = rows.some((row) => !row.hidden);
    group.hidden = !visible;
    if (isFiltering() && visible) group.open = true;
  }
}

function updateFilterResult(rows) {
  const result = document.getElementById("service-filter-result");
  if (!result) return;
  const visible = rows.filter((row) => !row.hidden).length;
  const active = [];
  if (filters.status !== "all") active.push(`status=${filters.status}`);
  if (filters.exposure !== "all") active.push(`exposure=${filters.exposure}`);
  if (filters.probe !== "all") active.push(`probe=${filters.probe}`);
  if (filters.query) active.push(`search=“${filters.query}”`);
  const details = active.length ? ` · ${active.join(" · ")}` : "";
  result.textContent = `${visible}/${rows.length} diagnostic rows visible${details}`;
}

function updateCollapseButton() {
  const button = document.getElementById("service-collapse-all");
  if (!button) return;
  const groups = [
    ...document.querySelectorAll("[data-service-group]:not([hidden])"),
  ];
  const anyOpen = groups.some((group) => group.open);
  button.textContent = anyOpen ? "Collapse" : "Expand";
  button.setAttribute("aria-expanded", String(anyOpen));
  button.title = anyOpen
    ? "Collapse all visible service groups"
    : "Expand all visible service groups";
}

function syncIssuesButton() {
  const button = document.getElementById("service-expand-issues");
  if (!button) return;
  const active = filters.status === "issues";
  button.textContent = active ? "All" : "Issues";
  button.setAttribute("aria-pressed", String(active));
}

function applyFilters() {
  const rows = [...document.querySelectorAll("[data-service-filter-target]")];
  for (const row of rows) {
    row.hidden = !(
      queryMatches(row) &&
      statusMatches(row) &&
      exposureMatches(row) &&
      probeMatches(row)
    );
  }
  updateGroupVisibility();
  updateFilterResult(rows);
  updateCollapseButton();
  syncIssuesButton();
}

function clearFilters() {
  filters.query = "";
  filters.status = "all";
  filters.exposure = "all";
  filters.probe = "all";

  const input = document.getElementById("service-filter");
  const status = document.getElementById("service-status-filter");
  const exposure = document.getElementById("service-exposure-filter");
  const probe = document.getElementById("service-probe-filter");
  if (input) input.value = "";
  if (status) status.value = "all";
  if (exposure) exposure.value = "all";
  if (probe) probe.value = "all";
  applyFilters();
}

function installFilterEvents() {
  const input = document.getElementById("service-filter");
  const clear = document.getElementById("service-filter-clear");
  const issues = document.getElementById("service-expand-issues");
  const collapse = document.getElementById("service-collapse-all");
  const status = document.getElementById("service-status-filter");
  const exposure = document.getElementById("service-exposure-filter");
  const probe = document.getElementById("service-probe-filter");

  input?.addEventListener("input", () => {
    filters.query = input.value;
    applyFilters();
  });
  status?.addEventListener("change", () => {
    filters.status = status.value;
    applyFilters();
  });
  exposure?.addEventListener("change", () => {
    filters.exposure = exposure.value;
    applyFilters();
  });
  probe?.addEventListener("change", () => {
    filters.probe = probe.value;
    applyFilters();
  });
  clear?.addEventListener("click", () => {
    clearFilters();
    input?.focus();
  });
  issues?.addEventListener("click", () => {
    filters.status = filters.status === "issues" ? "all" : "issues";
    if (status) status.value = filters.status;
    applyFilters();
  });
  collapse?.addEventListener("click", () => {
    const groups = [
      ...document.querySelectorAll("[data-service-group]:not([hidden])"),
    ];
    const shouldOpen = !groups.some((group) => group.open);
    for (const group of groups) group.open = shouldOpen;
    updateCollapseButton();
  });
  document.addEventListener(
    "toggle",
    (event) => {
      if (event.target?.matches?.("[data-service-group]")) {
        updateCollapseButton();
      }
    },
    true,
  );
}

async function decorateRows() {
  if (decorating) return;
  decorating = true;
  try {
    latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
    if (latestSnapshot) {
      const rows = document.querySelectorAll(
        ".health-row[data-service-filter-target]",
      );
      for (const row of rows) decorateRow(row, latestSnapshot);
    }
    applyFilters();
  } finally {
    decorating = false;
  }
}

function scheduleRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    decorateRows();
  });
}

export function installServiceDiagnostics() {
  ensureFilterControls();
  installFilterEvents();
  const board = document.getElementById("health-board");
  if (board) {
    const observer = new MutationObserver(scheduleRefresh);
    observer.observe(board, { childList: true, subtree: true });
  }
  scheduleRefresh();
}
