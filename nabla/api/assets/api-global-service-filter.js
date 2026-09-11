const STATUS_CHIPS = [
  ["operational", "Operational"],
  ["at-risk", "At risk"],
  ["degraded", "Degraded"],
  ["down", "Down"],
  ["unknown", "Unknown"],
];

let refreshScheduled = false;

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
  const counts = Object.fromEntries(STATUS_CHIPS.map(([status]) => [status, 0]));
  for (const row of healthRows()) {
    const status = normalizedStatus(row);
    if (Object.hasOwn(counts, status)) counts[status] += 1;
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
    button.setAttribute("aria-pressed", String(selected === status));
    button.innerHTML = `<strong>${counts[status]}</strong><span>${label}</span>`;
  }
}

function ensureHeader(host) {
  if (document.getElementById("service-filter-global-heading")) return;
  const header = document.createElement("div");
  header.className = "service-filter-global-heading";
  header.innerHTML =
    '<div><h2 id="service-filter-global-heading">Service health and filters</h2>' +
    "<p>Services remain the primary outcome; critical core, security, exposure and support evidence share one operator filter.</p></div>" +
    '<span class="service-filter-scope">Global view</span>';
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
  summary.textContent = "Probe evidence legend";
  details.append(summary, legend);
  host.appendChild(details);
}

function mapTrueNasStatus() {
  const panel = document.getElementById("truenas-platform");
  const state = document.getElementById("truenas-platform-state");
  if (!panel || !state) return;
  panel.dataset.presentationGroup = "core-critical";
  const className = state.className;
  if (className.includes("--ok")) panel.dataset.semanticStatus = "operational";
  else if (className.includes("--warn")) panel.dataset.semanticStatus = "degraded";
  else if (className.includes("--fail")) panel.dataset.semanticStatus = "down";
  else panel.dataset.semanticStatus = "unknown";
}

function refreshGlobalFilter() {
  const host = document.querySelector(".service-filter--global");
  if (!host) return;
  mapTrueNasStatus();
  ensureStatusSummary(host);
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
    if (event.key === "Escape" && document.activeElement?.id === "service-filter") {
      document.getElementById("service-filter-clear")?.click();
    }
  });
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
  ensureHeader(host);
  ensureStatusSummary(host);
  compactProbeLegend(host);

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
