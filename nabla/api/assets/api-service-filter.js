const STATUS_OPTIONS = [
  ["all", "All statuses"],
  ["operational", "Operational"],
  ["at-risk", "At risk"],
  ["degraded", "Degraded"],
  ["down", "Down"],
  ["unknown", "Unknown"],
  ["issues", "Issues only"],
];

const ENVIRONMENT_OPTIONS = [
  ["all", "All environments"],
  ["non-dev", "Production + Staging (exclude Dev)"],
  ["production", "Production"],
  ["staging", "Staging"],
  ["dev", "Dev"],
  ["defaulted", "Default production (review metadata)"],
];

const GROUP_OPTIONS = [
  ["all", "All presentation groups"],
  ["services", "Services & experiments"],
  ["core-critical", "Critical core platform"],
  ["security-controls", "Security controls"],
  ["shared-core", "Shared platform & data"],
  ["support", "Observability & support"],
  ["external", "External / optional"],
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

const FILTER_URL_PARAMS = {
  status: "health",
  environment: "environment",
  group: "group",
  exposure: "exposure",
  probe: "probe",
};

const FILTER_OPTION_VALUES = {
  status: new Set(STATUS_OPTIONS.map(([value]) => value)),
  environment: new Set(ENVIRONMENT_OPTIONS.map(([value]) => value)),
  group: new Set(GROUP_OPTIONS.map(([value]) => value)),
  exposure: new Set(EXPOSURE_OPTIONS.map(([value]) => value)),
  probe: new Set(PROBE_OPTIONS.map(([value]) => value)),
};

const FILTER_CONTROLS = {
  query: "service-filter",
  status: "service-status-filter",
  environment: "service-environment-filter",
  group: "service-group-filter",
  exposure: "service-exposure-filter",
  probe: "service-probe-filter",
};

const filters = {
  query: "",
  status: "all",
  environment: "all",
  group: "all",
  exposure: "all",
  probe: "all",
};

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
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
    selectControl("service-status-filter", "Health", STATUS_OPTIONS),
    selectControl(
      "service-environment-filter",
      "Environment",
      ENVIRONMENT_OPTIONS,
    ),
    selectControl("service-group-filter", "Presentation group", GROUP_OPTIONS),
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

function hydrateFiltersFromUrl() {
  const params = new URL(window.location.href).searchParams;
  filters.query = params.get("q") || "";
  for (const [key, parameter] of Object.entries(FILTER_URL_PARAMS)) {
    const value = params.get(parameter);
    filters[key] = FILTER_OPTION_VALUES[key].has(value) ? value : "all";
  }
}

function syncControlsFromFilters() {
  for (const [key, id] of Object.entries(FILTER_CONTROLS)) {
    const control = document.getElementById(id);
    if (control) control.value = filters[key];
  }
}

function syncFilterStateToUrl() {
  const url = new URL(window.location.href);
  if (filters.query) url.searchParams.set("q", filters.query);
  else url.searchParams.delete("q");

  for (const [key, parameter] of Object.entries(FILTER_URL_PARAMS)) {
    if (filters[key] === "all") url.searchParams.delete(parameter);
    else url.searchParams.set(parameter, filters[key]);
  }

  const next = `${url.pathname}${url.search}${url.hash}`;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next !== current) window.history.replaceState(window.history.state, "", next);
}

function statusMatches(row) {
  if (filters.status === "all") return true;
  const status = normalizedStatus(row);
  if (filters.status === "issues") return status !== "operational";
  return status === filters.status;
}

function environmentMatches(row) {
  if (filters.environment === "all") return true;
  if (filters.environment === "defaulted") {
    return row.dataset.environmentSource === "default";
  }
  const environments = String(row.dataset.environments || "")
    .split(/\s+/)
    .filter(Boolean);
  if (filters.environment === "non-dev") {
    return environments.some((environment) => environment !== "dev");
  }
  return environments.includes(filters.environment);
}

function groupMatches(row) {
  if (filters.group === "all") return true;
  return row.dataset.presentationGroup === filters.group;
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

function probeMatches(row) {
  if (filters.probe === "all") return true;
  return String(row.dataset.probeKinds || "")
    .split(/\s+/)
    .includes(filters.probe);
}

function queryMatches(row) {
  const tokens = normalize(filters.query).split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const haystack = normalize(
    [
      row.dataset.searchText,
      row.textContent,
      row.dataset.presentationGroup,
      row.dataset.environments,
      row.dataset.probeKinds,
      row.dataset.exposurePolicy,
      row.dataset.exposureScope,
      row.dataset.exposureMode,
    ].join(" "),
  );
  return tokens.every((token) => haystack.includes(token));
}

function isFiltering() {
  return (
    Boolean(filters.query) ||
    filters.status !== "all" ||
    filters.environment !== "all" ||
    filters.group !== "all" ||
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
  if (filters.status !== "all") active.push(`health=${filters.status}`);
  if (filters.environment !== "all") {
    active.push(`environment=${filters.environment}`);
  }
  if (filters.group !== "all") active.push(`group=${filters.group}`);
  if (filters.exposure !== "all") active.push(`exposure=${filters.exposure}`);
  if (filters.probe !== "all") active.push(`probe=${filters.probe}`);
  if (filters.query) active.push(`search=“${filters.query}”`);
  const details = active.length ? ` · ${active.join(" · ")}` : "";
  result.textContent = `${visible}/${rows.length} diagnostic views visible${details}`;
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

function notifyFilterChanged() {
  document.dispatchEvent(
    new CustomEvent("service-filter-changed", {
      detail: { ...filters },
    }),
  );
}

export function refreshServiceFilter() {
  const rows = [...document.querySelectorAll("[data-service-filter-target]")];
  for (const row of rows) {
    row.hidden = !(
      queryMatches(row) &&
      statusMatches(row) &&
      environmentMatches(row) &&
      groupMatches(row) &&
      exposureMatches(row) &&
      probeMatches(row)
    );
  }
  updateGroupVisibility();
  updateFilterResult(rows);
  updateCollapseButton();
  syncIssuesButton();
  notifyFilterChanged();
}

function clearFilters() {
  filters.query = "";
  filters.status = "all";
  filters.environment = "all";
  filters.group = "all";
  filters.exposure = "all";
  filters.probe = "all";
  syncControlsFromFilters();
  syncFilterStateToUrl();
  refreshServiceFilter();
}

function bindSelect(id, key) {
  const select = document.getElementById(id);
  select?.addEventListener("change", () => {
    filters[key] = select.value;
    syncFilterStateToUrl();
    refreshServiceFilter();
  });
}

function installFilterEvents() {
  const input = document.getElementById("service-filter");
  const clear = document.getElementById("service-filter-clear");
  const issues = document.getElementById("service-expand-issues");
  const collapse = document.getElementById("service-collapse-all");

  input?.addEventListener("input", () => {
    filters.query = input.value;
    syncFilterStateToUrl();
    refreshServiceFilter();
  });
  bindSelect("service-status-filter", "status");
  bindSelect("service-environment-filter", "environment");
  bindSelect("service-group-filter", "group");
  bindSelect("service-exposure-filter", "exposure");
  bindSelect("service-probe-filter", "probe");

  clear?.addEventListener("click", () => {
    clearFilters();
    input?.focus();
  });
  issues?.addEventListener("click", () => {
    filters.status = filters.status === "issues" ? "all" : "issues";
    const status = document.getElementById("service-status-filter");
    if (status) status.value = filters.status;
    syncFilterStateToUrl();
    refreshServiceFilter();
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
  window.addEventListener("popstate", () => {
    hydrateFiltersFromUrl();
    syncControlsFromFilters();
    refreshServiceFilter();
  });
}

export function installServiceFilter() {
  ensureFilterControls();
  hydrateFiltersFromUrl();
  syncControlsFromFilters();
  installFilterEvents();
  syncFilterStateToUrl();
  refreshServiceFilter();
}
