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
  for (const value of [
    check?.tunnel_url,
    check?.tunnelUrl,
    check?.href,
    check?.url,
    ...(Array.isArray(check?.aliases_probed) ? check.aliases_probed : []),
  ]) {
    if (value && String(value).trim()) return String(value).trim();
  }
  return "";
}

function checkMatchesRow(check, row) {
  if (!check || !row) return false;
  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const urlHost = hostOf(row.dataset.serviceUrl);
  const checkIds = [check.service_id, check.serviceId, check.id]
    .map(normalize)
    .filter(Boolean);
  const checkNames = [check.name, check.display_label]
    .map(normalize)
    .filter(Boolean);
  const checkHosts = [
    check.url,
    check.tunnel_url,
    check.tunnelUrl,
    ...(Array.isArray(check.aliases_probed) ? check.aliases_probed : []),
  ]
    .map(hostOf)
    .filter(Boolean);

  return (
    checkIds.includes(key) ||
    checkNames.includes(name) ||
    (urlHost && checkHosts.includes(urlHost))
  );
}

function findCheck(checks, row) {
  const key = row?.dataset?.serviceKey;
  if (!checks || !row) return null;
  if (key && checks[key]) return checks[key];
  for (const check of Object.values(checks)) {
    if (checkMatchesRow(check, row)) return check;
  }
  return null;
}

function normalizedPolicy(check) {
  const value = normalize(check?.policy_status);
  return ["ok", "warn", "fail", "unknown"].includes(value)
    ? value
    : "unknown";
}

function normalizedStatus(row) {
  const explicit = normalize(row.dataset.semanticStatus);
  if (explicit) return explicit;
  if (row.querySelector(".health-led--red")) return "down";
  if (row.querySelector(".health-led--yellow, .health-led--blue"))
    return "degraded";
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
  if (Number.isFinite(status)) {
    if (status >= 200 && status < 400) return "ok";
    if (status >= 500) return "fail";
    return "warn";
  }
  return check.reachable === true ? "ok" : "unknown";
}

function policyTone(policy) {
  if (policy === "ok") return "ok";
  if (policy === "warn") return "warn";
  if (policy === "fail") return "fail";
  return "unknown";
}

function probeBadge(kind, tone, label, detail) {
  const icon = PROBE_ICONS[kind] || "•";
  const title = detail || label;
  const badge = document.createElement("span");
  badge.className = `service-probe service-probe--${tone}`;
  badge.dataset.probeKind = kind;
  badge.title = title;
  badge.setAttribute("aria-label", title);

  const iconEl = document.createElement("span");
  iconEl.className = "service-probe-icon";
  iconEl.setAttribute("aria-hidden", "true");
  iconEl.textContent = icon;

  const labelEl = document.createElement("span");
  labelEl.className = "service-probe-label";
  labelEl.textContent = label;
  badge.append(iconEl, labelEl);
  return badge;
}

function addHttpEvidence(target, check, probeKinds) {
  if (!check) return;
  const url = urlOf(check);
  const hasHttp =
    /^https?:\/\//i.test(url) ||
    check.http_status != null ||
    String(check.probe || "").toLowerCase().includes("http");
  if (!hasHttp) return;

  const status = Number(check.http_status);
  const suffix = Number.isFinite(status) ? ` ${status}` : "";
  target.appendChild(
    probeBadge(
      "http",
      reachabilityTone(check),
      `HTTP${suffix}`,
      check.reachable === true
        ? `HTTP probe reached the target${suffix ? ` with status${suffix}` : ""}`
        : check.reachable === false
          ? `HTTP probe could not reach the target${check.error ? `: ${check.error}` : ""}`
          : `HTTP probe result is not confirmed${check.warning ? `: ${check.warning}` : ""}`,
    ),
  );
  probeKinds.add("http");
}

function addTlsEvidence(target, check, probeKinds) {
  if (!check) return;
  const url = urlOf(check);
  const hasHttps =
    /^https:\/\//i.test(url) ||
    (Array.isArray(check.aliases_probed) &&
      check.aliases_probed.some((value) => /^https:\/\//i.test(String(value))));
  if (!hasHttps) return;

  const tone =
    check.skipped === true
      ? "neutral"
      : check.tls_trusted === true
        ? "ok"
        : check.tls_trusted === false
          ? "fail"
          : "unknown";
  const detail =
    check.tls_trusted === true
      ? "HTTPS certificate chain and hostname were validated"
      : check.tls_trusted === false
        ? "HTTPS certificate validation failed"
        : check.skipped === true
          ? "TLS validation was intentionally skipped from this vantage point"
          : "HTTPS target exists but TLS trust was not confirmed";
  target.appendChild(probeBadge("tls", tone, "TLS", detail));
  probeKinds.add("tls");
}

function addTcpEvidence(target, check, probeKinds) {
  if (!check) return;
  const probe = normalize(check.probe);
  const protocol = normalize(check.protocol);
  const url = urlOf(check);
  const hasTcp =
    probe.includes("tcp") ||
    protocol === "tcp" ||
    (check.host && check.port != null && !/^https?:\/\//i.test(url));
  if (!hasTcp) return;

  const endpoint =
    check.host && check.port != null ? ` ${check.host}:${check.port}` : "";
  target.appendChild(
    probeBadge(
      "tcp",
      reachabilityTone(check),
      "TCP",
      `TCP connectivity probe${endpoint}${check.error ? `: ${check.error}` : ""}`,
    ),
  );
  probeKinds.add("tcp");
}

function addApiEvidence(target, key, check, probeKinds) {
  if (!check) return;
  const probe = normalize(check.probe);
  const path = String(check.path || "");
  const hasApi =
    probe.includes("api") ||
    path.startsWith("/api/") ||
    ["pfsense", "truenas_api"].includes(String(key || ""));
  if (!hasApi) return;

  target.appendChild(
    probeBadge(
      "api",
      reachabilityTone(check),
      "API",
      `Authenticated/read-only API evidence${path ? ` via ${path}` : ""}`,
    ),
  );
  probeKinds.add("api");

  if (probe.includes("websocket") || String(key || "") === "truenas_api") {
    target.appendChild(
      probeBadge(
        "websocket",
        reachabilityTone(check),
        "WS",
        "WebSocket API connectivity evidence",
      ),
    );
    probeKinds.add("websocket");
  }
}

function addCloudflareEvidence(target, exposure, probeKinds) {
  if (!exposure) return;
  const expected = exposure.tunnel_secure === true;
  const observed = exposure.cloudflare_tunnel_observed;
  const hasTunnelEvidence =
    exposure.tunnel_secure != null ||
    observed != null ||
    exposure.cloudflare_default_deny != null ||
    exposure.cloudflare_access_policy_count != null;
  if (!hasTunnelEvidence) return;

  let tunnelTone = "unknown";
  let tunnelDetail = "Cloudflare Tunnel evidence is not confirmed";
  if (expected && observed === true) {
    tunnelTone = "ok";
    tunnelDetail = "Cloudflare Tunnel is expected and observed";
  } else if (expected && observed === false) {
    tunnelTone = "fail";
    tunnelDetail = "Cloudflare Tunnel is expected but was not observed";
  } else if (!expected && observed === true) {
    tunnelTone = "warn";
    tunnelDetail = "Cloudflare Tunnel was observed although direct exposure is declared";
  } else if (exposure.tunnel_secure === false) {
    tunnelTone = "neutral";
    tunnelDetail = "Cloudflare Tunnel is not required by the declared exposure policy";
  }
  target.appendChild(
    probeBadge("cloudflare", tunnelTone, "Tunnel", tunnelDetail),
  );
  probeKinds.add("cloudflare");

  const policyCount = Number(exposure.cloudflare_access_policy_count);
  if (
    exposure.cloudflare_default_deny != null ||
    Number.isFinite(policyCount)
  ) {
    let accessTone = "unknown";
    if (exposure.cloudflare_default_deny === true && policyCount > 0)
      accessTone = "ok";
    else if (exposure.cloudflare_default_deny === true && policyCount === 0)
      accessTone = "fail";
    else if (Number.isFinite(policyCount)) accessTone = policyCount > 0 ? "ok" : "warn";

    target.appendChild(
      probeBadge(
        "access",
        accessTone,
        "Access",
        `Cloudflare Access Default-Deny=${String(exposure.cloudflare_default_deny)}${Number.isFinite(policyCount) ? ` · ${policyCount} policy${policyCount === 1 ? "" : "ies"}` : ""}`,
      ),
    );
    probeKinds.add("access");
  }

  if (exposure.cloudflare_service_auth_attempted === true) {
    const passed = exposure.cloudflare_service_token_access_passed;
    target.appendChild(
      probeBadge(
        "service-token",
        passed === true ? "ok" : passed === false ? "fail" : "unknown",
        "Token",
        passed === true
          ? "Cloudflare Access Service Token authenticated successfully"
          : passed === false
            ? "Cloudflare Access Service Token authentication failed"
            : "Cloudflare Access Service Token result is unknown",
      ),
    );
    probeKinds.add("service-token");
  }
}

function metricEvidence(check) {
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
    [check.source, check.metric_source, check.telemetry_source].filter(Boolean).join(" "),
  );
  return source.includes("prometheus") ? "unknown" : null;
}

function addMetricEvidence(target, check, probeKinds) {
  const tone = metricEvidence(check);
  if (!tone) return;
  target.appendChild(
    probeBadge(
      "metrics",
      tone,
      "Metrics",
      tone === "ok"
        ? "Prometheus/metrics evidence is available"
        : tone === "fail"
          ? "Prometheus/metrics evidence reports unavailable"
          : "Prometheus/metrics source is declared but current evidence is unknown",
    ),
  );
  probeKinds.add("metrics");
}

function exposureMetadata(row, exposure) {
  if (!exposure) {
    row.dataset.exposurePolicy = "unobserved";
    row.dataset.exposureScope = "unobserved";
    row.dataset.exposureMode = "unobserved";
    return;
  }
  row.dataset.exposurePolicy = normalizedPolicy(exposure);
  row.dataset.exposureScope =
    exposure.external === true
      ? "external"
      : exposure.external === false
        ? "internal"
        : "unknown";
  row.dataset.exposureMode =
    exposure.tunnel_secure === true
      ? "cloudflare"
      : exposure.tunnel_secure === false
        ? "direct"
        : "unknown";
}

function decorateRow(row, snapshot) {
  const healthChecks = snapshot?.healthz?.checks || {};
  const homelabChecks = snapshot?.homelab?.checks || {};
  const sickzChecks = snapshot?.sickz?.checks || {};
  const key = row.dataset.serviceKey || "";
  const health =
    findCheck(healthChecks, row) || findCheck(homelabChecks, row) || null;
  const exposure = findCheck(sickzChecks, row) || null;
  const primary = row.querySelector(".health-row-primary");
  if (!primary) return;

  exposureMetadata(row, exposure);
  const probeKinds = new Set();
  const strip = document.createElement("div");
  strip.className = "service-probe-strip";
  strip.setAttribute("aria-label", "Probe evidence");

  const mainEvidence = health || exposure;
  addHttpEvidence(strip, mainEvidence, probeKinds);
  addTlsEvidence(strip, exposure || mainEvidence, probeKinds);
  addTcpEvidence(strip, mainEvidence, probeKinds);
  addApiEvidence(strip, key, mainEvidence, probeKinds);
  addCloudflareEvidence(strip, exposure, probeKinds);
  addMetricEvidence(strip, health, probeKinds);

  if (exposure?.policy_status) {
    const policy = normalizedPolicy(exposure);
    strip.appendChild(
      probeBadge(
        "policy",
        policyTone(policy),
        "Policy",
        exposure.policy_detail || `Exposure security policy: ${policy}`,
      ),
    );
  }

  row.dataset.probeKinds = [...probeKinds].join(" ");
  const signature = strip.innerHTML;
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

  const result = document.createElement("div");
  result.id = "service-filter-result";
  result.className = "service-filter-result";
  result.setAttribute("aria-live", "polite");

  const legend = document.createElement("div");
  legend.id = "service-probe-legend";
  legend.className = "service-probe-legend";
  legend.innerHTML =
    '<strong>Probe evidence</strong><span>🌐 HTTP</span><span>🔒 TLS</span><span>🔌 TCP</span><span>⚙️ API</span><span>↔️ WebSocket</span><span>☁️ Tunnel</span><span>🛡️ Access / policy</span><span>🔑 Service Token</span><span>📈 Metrics</span><small>green = operational · amber = warning · red = failed · gray = unknown / not confirmed</small>';

  host.append(facets, result, legend);
}

function exposureMatches(row) {
  if (filters.exposure === "all") return true;
  if (filters.exposure === "external")
    return row.dataset.exposureScope === "external";
  if (filters.exposure === "internal")
    return row.dataset.exposureScope === "internal";
  if (filters.exposure === "cloudflare")
    return row.dataset.exposureMode === "cloudflare";
  if (filters.exposure === "direct")
    return row.dataset.exposureMode === "direct";
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

function updateGroupVisibility() {
  const filtering =
    Boolean(filters.query) ||
    filters.status !== "all" ||
    filters.exposure !== "all" ||
    filters.probe !== "all";
  for (const group of document.querySelectorAll("[data-service-group]")) {
    const rows = [...group.querySelectorAll("[data-service-filter-target]")];
    const visible = rows.some((row) => !row.hidden);
    group.hidden = !visible;
    if (filtering && visible) group.open = true;
  }
}

function updateFilterResult(rows) {
  const result = document.getElementById("service-filter-result");
  if (!result) return;
  const visible = rows.filter((row) => !row.hidden).length;
  const active = [];
  if (filters.status !== "all") active.push(`status=${filters.status}`);
  if (filters.exposure !== "all")
    active.push(`exposure=${filters.exposure}`);
  if (filters.probe !== "all") active.push(`probe=${filters.probe}`);
  if (filters.query) active.push(`search=“${filters.query}”`);
  result.textContent = `${visible}/${rows.length} diagnostic rows visible${active.length ? ` · ${active.join(" · ")}` : ""}`;
}

function applyFilters() {
  const rows = [
    ...document.querySelectorAll("[data-service-filter-target]"),
  ];
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
}

function updateCollapseButton() {
  const button = document.getElementById("service-collapse-all");
  if (!button) return;
  const visibleGroups = [
    ...document.querySelectorAll("[data-service-group]:not([hidden])"),
  ];
  const anyOpen = visibleGroups.some((group) => group.open);
  button.textContent = anyOpen ? "Collapse" : "Expand";
  button.setAttribute("aria-expanded", String(anyOpen));
  button.title = anyOpen
    ? "Collapse all visible service groups"
    : "Expand all visible service groups";
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
    issues.textContent = filters.status === "issues" ? "All" : "Issues";
    issues.setAttribute(
      "aria-pressed",
      String(filters.status === "issues"),
    );
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
      if (event.target?.matches?.("[data-service-group]"))
        updateCollapseButton();
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
      for (const row of document.querySelectorAll(
        ".health-row[data-service-filter-target]",
      )) {
        decorateRow(row, latestSnapshot);
      }
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
