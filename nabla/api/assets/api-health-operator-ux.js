const SECTION_DEFINITIONS = [
  {
    id: "health-board",
    label: "Health",
    metric: () =>
      visibleRatio(
        "#health-checks > [data-service-filter-target], #health-services-groups [data-service-filter-target]",
      ),
  },
  {
    id: "sickz-board-title",
    label: "Exposure",
    metric: () => visibleRatio("#sickz-checks > [data-service-filter-target]"),
  },
  {
    id: "truenas-platform",
    label: "TrueNAS",
    metric: () =>
      String(
        document.querySelectorAll("#truenas-probe-list .truenas-probe-row")
          .length || "—",
      ),
  },
  {
    id: "runtime-topology",
    label: "Runtime",
    metric: () =>
      document.getElementById("runtime-instance-count")?.textContent?.trim() ||
      "—",
  },
];

const ISSUE_STATUSES = new Set(["at-risk", "degraded", "down"]);
const STATUS_RANK = {
  operational: 0,
  "at-risk": 1,
  degraded: 2,
  down: 3,
};

let baselineStatuses = null;
let refreshScheduled = false;

function uniqueElements(selector) {
  return [...new Set(document.querySelectorAll(selector))];
}

function visibleRatio(selector) {
  const rows = uniqueElements(selector);
  if (rows.length === 0) return "—";
  const visible = rows.filter((row) => !row.hidden).length;
  return visible === rows.length
    ? String(rows.length)
    : `${visible}/${rows.length}`;
}

function scrollToSection(id) {
  const target = document.getElementById(id);
  if (!target) return;
  const reducedMotion = window.matchMedia?.(
    "(prefers-reduced-motion: reduce)",
  )?.matches;
  target.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "start",
  });
}

function ensureSectionNavigation() {
  let nav = document.getElementById("service-section-navigation");
  if (nav) return nav;
  const summary = document.getElementById("service-filter-health-summary");
  if (!summary) return null;

  nav = document.createElement("nav");
  nav.id = "service-section-navigation";
  nav.className = "service-filter-health-summary";
  nav.setAttribute("aria-label", "Health board sections");
  nav.style.gridTemplateColumns = "repeat(auto-fit, minmax(6rem, 1fr))";

  for (const section of SECTION_DEFINITIONS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "service-filter-health-chip";
    button.dataset.sectionTarget = section.id;

    const metric = document.createElement("strong");
    metric.dataset.sectionMetric = section.id;
    metric.textContent = "—";
    const label = document.createElement("span");
    label.textContent = section.label;
    button.append(metric, label);
    button.addEventListener("click", () => scrollToSection(section.id));
    nav.appendChild(button);
  }

  summary.insertAdjacentElement("afterend", nav);
  return nav;
}

function refreshSectionNavigation() {
  const nav = ensureSectionNavigation();
  if (!nav) return;
  for (const section of SECTION_DEFINITIONS) {
    const metric = nav.querySelector(`[data-section-metric="${section.id}"]`);
    if (!metric) continue;
    const value = section.metric();
    metric.textContent = value;
    metric.parentElement?.setAttribute(
      "aria-label",
      `${section.label} section · ${value}`,
    );
  }
}

function normalizedStatus(row) {
  const explicit = String(row?.dataset?.semanticStatus || "").trim();
  if (explicit) return explicit;
  if (row?.querySelector?.(".health-led--red")) return "down";
  if (row?.querySelector?.(".health-led--yellow, .health-led--blue")) {
    return "degraded";
  }
  if (row?.querySelector?.(".health-led--green")) return "operational";
  return "unknown";
}

function statusKey(row, index) {
  const scope = row.closest("#sickz-checks")
    ? "exposure"
    : row.id === "truenas-platform"
      ? "truenas"
      : "health";
  const identity =
    row.dataset.serviceKey ||
    row.dataset.serviceName ||
    row.id ||
    row.dataset.searchText ||
    `row-${index}`;
  return `${scope}:${identity}`;
}

function collectStatuses() {
  const entries = new Map();
  const rows = uniqueElements("[data-service-filter-target]");
  rows.forEach((row, index) => {
    entries.set(statusKey(row, index), {
      status: normalizedStatus(row),
      row,
    });
  });
  return entries;
}

function clearChangeMarkers() {
  document.querySelectorAll("[data-health-change]").forEach((row) => {
    delete row.dataset.healthChange;
  });
}

function classifyChange(previous, current) {
  if (previous === current || previous === "unknown" || current === "unknown") {
    return null;
  }
  if (ISSUE_STATUSES.has(previous) && current === "operational") {
    return "recovered";
  }
  const previousRank = STATUS_RANK[previous];
  const currentRank = STATUS_RANK[current];
  if (
    Number.isFinite(previousRank) &&
    Number.isFinite(currentRank) &&
    currentRank > previousRank &&
    ISSUE_STATUSES.has(current)
  ) {
    return "regressed";
  }
  return null;
}

function ensureChangeSummary() {
  let summary = document.getElementById("service-health-changes");
  if (summary) return summary;
  const nav = ensureSectionNavigation();
  if (!nav) return null;
  summary = document.createElement("div");
  summary.id = "service-health-changes";
  summary.className = "service-filter-active";
  summary.setAttribute("aria-live", "polite");
  summary.setAttribute("aria-label", "Health changes since last refresh");
  nav.insertAdjacentElement("afterend", summary);
  return summary;
}

function focusFirstChange(kind) {
  const row = document.querySelector(`[data-health-change="${kind}"]`);
  if (!row) return;
  const reducedMotion = window.matchMedia?.(
    "(prefers-reduced-motion: reduce)",
  )?.matches;
  row.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "center",
  });
}

function changeChip(kind, count) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "service-filter-active-chip";
  const label = kind === "regressed" ? "new issues" : "recovered";
  const symbol = kind === "regressed" ? "⚠" : "✓";
  button.innerHTML = `<span>Since last refresh · ${count} ${label}</span><strong aria-hidden="true">${symbol}</strong>`;
  button.setAttribute("aria-label", `${count} ${label} since last refresh`);
  button.addEventListener("click", () => focusFirstChange(kind));
  return button;
}

function renderChanges(changes) {
  const summary = ensureChangeSummary();
  if (!summary) return;
  summary.replaceChildren();
  const regressions = changes.filter((change) => change.kind === "regressed");
  const recoveries = changes.filter((change) => change.kind === "recovered");
  if (regressions.length === 0 && recoveries.length === 0) {
    summary.hidden = true;
    return;
  }
  summary.hidden = false;
  if (regressions.length)
    summary.appendChild(changeChip("regressed", regressions.length));
  if (recoveries.length)
    summary.appendChild(changeChip("recovered", recoveries.length));
}

function compareRefreshStatuses() {
  const current = collectStatuses();
  clearChangeMarkers();
  if (baselineStatuses === null) {
    baselineStatuses = new Map(
      [...current].map(([key, value]) => [key, value.status]),
    );
    renderChanges([]);
    return;
  }

  const changes = [];
  for (const [key, value] of current) {
    const previous = baselineStatuses.get(key);
    if (!previous) continue;
    const kind = classifyChange(previous, value.status);
    if (!kind) continue;
    value.row.dataset.healthChange = kind;
    changes.push({ key, kind, previous, current: value.status });
  }
  baselineStatuses = new Map(
    [...current].map(([key, value]) => [key, value.status]),
  );
  renderChanges(changes);
}

function scheduleNavigationRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    refreshSectionNavigation();
  });
}

function observeSectionMetrics() {
  const observer = new MutationObserver(scheduleNavigationRefresh);
  for (const id of [
    "health-checks",
    "health-services-groups",
    "sickz-checks",
    "truenas-probe-list",
    "runtime-topology",
  ]) {
    const target = document.getElementById(id);
    if (!target) continue;
    observer.observe(target, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden", "class", "data-semantic-status"],
    });
  }
  document.addEventListener(
    "service-filter-changed",
    scheduleNavigationRefresh,
  );
}

export function installHealthOperatorUx() {
  ensureSectionNavigation();
  ensureChangeSummary();
  refreshSectionNavigation();
  observeSectionMetrics();
  document.addEventListener("health-board-refreshed", () => {
    window.requestAnimationFrame(() => {
      compareRefreshStatuses();
      refreshSectionNavigation();
    });
  });
}
