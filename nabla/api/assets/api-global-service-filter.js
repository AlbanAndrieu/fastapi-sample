const STATUS_CHIPS = [
  ["all", "All"],
  ["operational", "Operational"],
  ["at-risk", "At risk"],
  ["degraded", "Degraded"],
  ["down", "Down"],
  ["unknown", "Unknown"],
];

// Fixed SVG paths. Filter values and icon markup are local constants, not service data.
const STATUS_ICON_PATHS = {
  all: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  operational: '<path d="M4 12.5l5 5L20 6"/>',
  "at-risk": '<path d="M12 3L2.5 20h19L12 3z"/><path d="M12 9v5m0 3h.01"/>',
  degraded: '<path d="M2 13h5l3-6 4 10 3-4h5"/>',
  down: '<circle cx="12" cy="12" r="9"/><path d="M8 8l8 8m0-8l-8 8"/>',
  unknown: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.6 2.6 0 0 1 5 1c0 2-2.5 2-2.5 4m0 3h.01"/>',
};

function statusIcon(status) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${STATUS_ICON_PATHS[status]}</svg>`;
}

const ACTIVE_FILTERS = [
  ["status", "Health", "service-status-filter"],
  ["environment", "Environment", "service-environment-filter"],
  ["group", "Group", "service-group-filter"],
  ["exposure", "Exposure", "service-exposure-filter"],
  ["probe", "Probe", "service-probe-filter"],
];

const STICKY_HYSTERESIS_PX = 8;
let refreshScheduled = false;
let stickyRefreshScheduled = false;

function normalizedStatus(row) {
  const explicit = String(row?.dataset?.semanticStatus || "").trim();
  if (explicit) return explicit;
  if (row?.querySelector?.(".health-led--red")) return "down";
  if (row?.querySelector?.(".health-led--yellow, .health-led--blue")) {
    return "degraded";
  }
  if (row?.querySelector?.(".health-led--gray")) return "unknown";
  if (row?.querySelector?.(".health-led--green")) return "operational";
  return "unknown";
}

function healthRows() {
  return [
    ...new Set([
      ...document.querySelectorAll(
        "#health-checks > [data-service-filter-target], #health-services-groups [data-service-filter-target]",
      ),
    ]),
  ];
}

function statusCounts() {
  const counts = Object.fromEntries(
    STATUS_CHIPS.map(([status]) => [status, 0]),
  );
  const rows = healthRows();
  counts.all = rows.length;
  for (const row of rows) {
    const status = normalizedStatus(row);
    if (status !== "all" && Object.hasOwn(counts, status)) {
      counts[status] += 1;
    } else if (!Object.hasOwn(counts, status)) {
      // A new server status must never silently count as operational.
      counts.unknown += 1;
    }
  }
  return counts;
}

function setStatusFilter(status) {
  const select = document.getElementById("service-status-filter");
  if (!select) return;
  select.value = select.value === status ? "all" : status;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function renderStatusChips(host) {
  const counts = statusCounts();
  const selected =
    document.getElementById("service-status-filter")?.value || "all";
  for (const [status, label] of STATUS_CHIPS) {
    let button = host.querySelector(`[data-global-status-filter="${status}"]`);
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "service-filter-health-chip";
      button.dataset.globalStatusFilter = status;
      button.addEventListener("click", () => setStatusFilter(status));
      host.appendChild(button);
    }
    const enabled = selected === status;
    button.setAttribute("aria-pressed", String(enabled));
    button.setAttribute("aria-label", `${label}: ${counts[status]} services`);
    button.dataset.tooltip = `${label} · ${enabled ? "On" : "Off"}`;
    button.removeAttribute("title");
    button.innerHTML =
      `<span class="service-filter-health-icon">${statusIcon(status)}</span>` +
      `<strong class="service-filter-health-count">${counts[status]}</strong>` +
      `<span class="service-filter-health-name">${label}</span>`;
  }
}

function ensureHeader(host) {
  if (document.getElementById("service-filter-global-heading")) return;
  const header = document.createElement("div");
  header.className = "service-filter-global-heading";
  header.innerHTML =
    '<div><h2 id="service-filter-global-heading">Service health and filters</h2>' +
    "<p>Choose a status, then refine the services. Select a service to view its probes.</p></div>" +
    '<div class="service-filter-heading-actions"><span class="service-filter-scope">Global view</span>' +
    '<button type="button" class="service-filter-density-toggle" id="service-filter-density-toggle" aria-expanded="true">Collapse</button></div>';
  host.prepend(header);
}

function ensureStatusSummary(host) {
  let summary = document.getElementById("service-filter-health-summary");
  if (!summary) {
    summary = document.createElement("div");
    summary.id = "service-filter-health-summary";
    summary.className = "service-filter-health-summary";
    summary.setAttribute("aria-label", "Service health summary filters");
    const heading = document.getElementById("service-filter-global-heading");
    heading?.parentElement?.parentElement?.insertAdjacentElement(
      "afterend",
      summary,
    );
    if (!summary.isConnected) host.prepend(summary);
  }
  renderStatusChips(summary);
}

function compactProbeLegend(host) {
  const legend = document.getElementById("service-probe-legend");
  if (!legend || legend.closest(".service-filter-legend-details")) return;
  const details = document.createElement("details");
  details.className = "service-filter-legend-details";
  const summary = document.createElement("summary");
  summary.textContent = "Legend / how to read";
  details.append(summary, legend);
  host.appendChild(details);
}

function mapTrueNasStatus() {
  const panel = document.getElementById("truenas-platform");
  const state = document.getElementById("truenas-platform-state");
  if (!panel || !state) return;
  panel.dataset.presentationGroup = "core-critical";
  panel.dataset.environments = "production";
  panel.dataset.environmentSource = "runtime";
  // Filter by visible measured protocol stages, not the declared capabilities.
  const allowed = new Set(["dns", "tcp", "tls", "http", "api", "websocket"]);
  const protocols = new Set(
    [
      ...panel.querySelectorAll(
        ".truenas-stage:not(.truenas-stage--blocked) .truenas-stage-protocol",
      ),
    ]
      .map((node) => String(node.textContent || "").trim().toLowerCase())
      .filter((name) => allowed.has(name)),
  );
  panel.dataset.probeKinds = [...protocols].join(" ");
  const className = state.className;
  if (className.includes("--ok")) panel.dataset.semanticStatus = "operational";
  else if (className.includes("--warn"))
    panel.dataset.semanticStatus = "degraded";
  else if (className.includes("--fail")) panel.dataset.semanticStatus = "down";
  else panel.dataset.semanticStatus = "unknown";
}

function currentFilterState() {
  return {
    query: document.getElementById("service-filter")?.value || "",
    status: document.getElementById("service-status-filter")?.value || "all",
    environment:
      document.getElementById("service-environment-filter")?.value || "all",
    group: document.getElementById("service-group-filter")?.value || "all",
    exposure:
      document.getElementById("service-exposure-filter")?.value || "all",
    probe: document.getElementById("service-probe-filter")?.value || "all",
  };
}

function activeFilterLabel(id, value) {
  const select = document.getElementById(id);
  return select?.selectedOptions?.[0]?.textContent || value;
}

function clearActiveFilter(key, id) {
  const control = document.getElementById(id);
  if (!control) return;
  control.value = key === "query" ? "" : "all";
  control.dispatchEvent(
    new Event(key === "query" ? "input" : "change", { bubbles: true }),
  );
}

function ensureActiveFilters(host) {
  let active = document.getElementById("service-filter-active");
  if (active) return active;
  active = document.createElement("div");
  active.id = "service-filter-active";
  active.className = "service-filter-active";
  active.setAttribute("aria-label", "Active service filters");
  const result = document.getElementById("service-filter-result");
  result?.insertAdjacentElement("beforebegin", active);
  if (!active.isConnected) host.appendChild(active);
  return active;
}

function renderActiveFilters(host, state = currentFilterState()) {
  const active = ensureActiveFilters(host);
  active.replaceChildren();
  const entries = [];
  if (state.query) {
    entries.push(["query", "Search", "service-filter", state.query]);
  }
  for (const [key, label, id] of ACTIVE_FILTERS) {
    if (state[key] && state[key] !== "all") {
      entries.push([key, label, id, activeFilterLabel(id, state[key])]);
    }
  }

  active.hidden = entries.length === 0;
  for (const [key, label, id, value] of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "service-filter-active-chip";
    button.dataset.filterKey = key;
    button.title = `Remove ${label.toLowerCase()} filter`;
    button.setAttribute(
      "aria-label",
      `Remove ${label.toLowerCase()} filter: ${value}`,
    );
    const text = document.createElement("span");
    text.textContent = `${label}: ${value}`;
    const remove = document.createElement("strong");
    remove.setAttribute("aria-hidden", "true");
    remove.textContent = "×";
    button.append(text, remove);
    button.addEventListener("click", () => clearActiveFilter(key, id));
    active.appendChild(button);
  }
}

function refreshGlobalFilter(state) {
  const host = document.querySelector(".service-filter--global");
  if (!host) return;
  mapTrueNasStatus();
  ensureStatusSummary(host);
  renderActiveFilters(host, state || currentFilterState());
}

function scheduleRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    refreshGlobalFilter();
  });
}

function installKeyboardShortcuts() {
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const editing =
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      target?.isContentEditable;
    if (event.key === "/" && !editing) {
      event.preventDefault();
      document.getElementById("service-filter")?.focus();
      return;
    }
    if (
      event.key === "Escape" &&
      document.activeElement?.id === "service-filter"
    ) {
      document.getElementById("service-filter-clear")?.click();
    }
  });
}

function mobileFilterViewport() {
  return window.matchMedia("(max-width: 720px)").matches;
}

function syncCompactState(host) {
  const stuck = host.dataset.stuck === "true";
  const userCompact = host.dataset.userCompact === "true";
  const stuckExpanded = host.dataset.stuckExpanded === "true";
  const mobile = mobileFilterViewport();
  const mobileCompact =
    mobile && host.dataset.mobileExpanded !== "true";
  const compact =
    userCompact || mobileCompact || (stuck && !stuckExpanded);
  host.classList.toggle("service-filter--compact", compact);
  host.dataset.expanded = String(!compact);
  const button = document.getElementById("service-filter-density-toggle");
  if (button) {
    const state = currentFilterState();
    const activeCount = Object.entries(state).filter(
      ([key, value]) => key === "query" ? Boolean(value.trim()) : value !== "all",
    ).length;
    button.textContent = mobile
      ? compact
        ? "Filters"
        : "Hide filters"
      : compact
        ? "Expand"
        : "Collapse";
    if (activeCount) button.textContent += ` (${activeCount})`;
    button.setAttribute("aria-expanded", String(!compact));
  }
}

function refreshStickyState(host, sentinel) {
  const parsedTop = Number.parseFloat(window.getComputedStyle(host).top);
  const stickyTop = Number.isFinite(parsedTop) ? parsedTop : 0;
  const sentinelTop = sentinel.getBoundingClientRect().top;
  const wasStuck = host.dataset.stuck === "true";
  const stuck = wasStuck
    ? sentinelTop <= stickyTop + STICKY_HYSTERESIS_PX
    : sentinelTop < stickyTop - STICKY_HYSTERESIS_PX;
  if (stuck !== wasStuck) {
    host.dataset.stuck = String(stuck);
    if (!stuck) host.dataset.stuckExpanded = "false";
  }
  syncCompactState(host);
}

function scheduleStickyRefresh(host, sentinel) {
  if (stickyRefreshScheduled) return;
  stickyRefreshScheduled = true;
  window.requestAnimationFrame(() => {
    stickyRefreshScheduled = false;
    refreshStickyState(host, sentinel);
  });
}

function installCompactStickyMode(host) {
  const sentinel = document.createElement("div");
  sentinel.className = "service-filter-sticky-sentinel";
  sentinel.setAttribute("aria-hidden", "true");
  host.insertAdjacentElement("beforebegin", sentinel);
  host.dataset.stuck = "false";
  host.dataset.userCompact = "false";
  host.dataset.stuckExpanded = "false";
  host.dataset.mobileExpanded = "false";

  const toggle = document.getElementById("service-filter-density-toggle");
  toggle?.addEventListener("click", () => {
    const compact = host.classList.contains("service-filter--compact");
    if (mobileFilterViewport()) {
      host.dataset.mobileExpanded = String(compact);
      host.dataset.userCompact = "false";
      host.dataset.stuckExpanded = String(
        compact && host.dataset.stuck === "true",
      );
      syncCompactState(host);
      return;
    }
    if (compact) {
      host.dataset.userCompact = "false";
      host.dataset.stuckExpanded =
        host.dataset.stuck === "true" ? "true" : "false";
    } else {
      host.dataset.userCompact = "true";
      host.dataset.stuckExpanded = "false";
    }
    syncCompactState(host);
  });

  const refreshSticky = () => scheduleStickyRefresh(host, sentinel);
  window.addEventListener("scroll", refreshSticky, { passive: true });
  window.addEventListener("resize", refreshSticky, { passive: true });
  window.addEventListener("pageshow", refreshSticky);
  syncCompactState(host);
  refreshSticky();
}

export function installGlobalServiceFilter() {
  const host = document.querySelector(".service-filter");
  const board = document.getElementById("health-board");
  if (!host || !board) return;

  host.classList.add("service-filter--global");
  host.setAttribute("aria-labelledby", "service-filter-global-heading");
  board.insertAdjacentElement("beforebegin", host);

  const searchLabel = host.querySelector('label[for="service-filter"]');
  if (searchLabel) searchLabel.textContent = "Search services";
  const reset = document.getElementById("service-filter-clear");
  if (reset) reset.textContent = "Reset";
  ensureHeader(host);
  ensureStatusSummary(host);
  ensureActiveFilters(host);
  compactProbeLegend(host);
  installCompactStickyMode(host);

  document.addEventListener("service-filter-changed", (event) => {
    refreshGlobalFilter(event.detail);
    syncCompactState(host);
  });

  const status = document.getElementById("service-status-filter");
  status?.addEventListener("change", scheduleRefresh);

  const trueNasState = document.getElementById("truenas-platform-state");
  if (trueNasState) {
    new MutationObserver(() => {
      mapTrueNasStatus();
      status?.dispatchEvent(new Event("change", { bubbles: true }));
    }).observe(trueNasState, {
      attributes: true,
      attributeFilter: ["class"],
      childList: true,
      subtree: true,
    });
  }

  new MutationObserver(scheduleRefresh).observe(board, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["data-semantic-status", "hidden"],
  });
  installKeyboardShortcuts();
  scheduleRefresh();
}
