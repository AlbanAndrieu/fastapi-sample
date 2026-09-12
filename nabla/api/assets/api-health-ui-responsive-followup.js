const IMPLEMENTATION_NOTE =
  "TrueNAS flow rendered from bounded /api/homelab/probes first; aggregate health enriches the view when available.";
const DRAWER_SETTLE_MS = 3000;
const retainedDrawerSections = new Map();
let drawerSyncScheduled = false;
let boardSyncScheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function identity(value) {
  return normalize(value)
    .replace(/^albandrieu[-_]/, "")
    .replace(/[^a-z0-9]+/g, "");
}

function selectedRow() {
  return document.querySelector(
    '[data-service-filter-target][data-detail-selected="true"]',
  );
}

function rowStatus(row) {
  const explicit = String(row?.dataset?.semanticStatus || "").trim();
  if (explicit) return explicit;
  if (row?.querySelector?.(".health-led--red")) return "down";
  if (row?.querySelector?.(".health-led--yellow, .health-led--blue")) {
    return "degraded";
  }
  if (row?.querySelector?.(".health-led--green")) return "operational";
  return "unknown";
}

function statusLabel(status) {
  if (status === "at-risk") return "At risk";
  return `${status.charAt(0).toUpperCase()}${status.slice(1)}`;
}

function rowReason(row) {
  const detail = row
    ?.querySelector?.(".health-row-detail")
    ?.textContent?.trim();
  if (detail) return detail;
  if (row?.id === "truenas-platform") {
    return (
      document.getElementById("truenas-platform-state")?.textContent?.trim() ||
      ""
    );
  }
  return "";
}

function stripRedundantTargets(row) {
  if (!row.closest("#sickz-checks")) return;
  const detail = row.querySelector(".health-row-detail");
  if (!detail) return;
  let text = String(detail.textContent || "");
  text = text.replace(
    /Not probed \(LAN(?: \/ internal network)? skip\)\./i,
    "External exposure policy probe skipped from trusted LAN; LAN/TCP probes are independent.",
  );

  const match = text.match(/\s+Targets:\s+(.+)$/i);
  if (match) {
    const names = new Set(
      [row.dataset.serviceName, row.dataset.serviceKey]
        .map(identity)
        .filter(Boolean),
    );
    const targets = match[1].split(" · ").map(identity).filter(Boolean);
    if (targets.length > 0 && targets.every((target) => names.has(target))) {
      text = text.slice(0, match.index).trim();
    }
  }
  if (detail.textContent !== text) detail.textContent = text;
}

function annotateStatus(row) {
  stripRedundantTargets(row);
  const reason = rowReason(row);
  if (!reason) return;
  const status = rowStatus(row);
  const title = `${statusLabel(status)}: ${reason}`;
  row.dataset.statusReason = reason;
  const led = row.querySelector(".health-led");
  if (led) {
    led.title = title;
    led.setAttribute("aria-label", title);
  }
}

function ensureDrawerReason() {
  const row = selectedRow();
  const drawer = document.getElementById("service-detail-drawer");
  const body = drawer?.querySelector(".service-detail-body");
  if (!row || !body || drawer?.hidden) return;
  const reason = rowReason(row);
  let section = body.querySelector('[data-followup-section="status-reason"]');
  if (!reason) {
    section?.remove();
    return;
  }
  if (!section) {
    section = document.createElement("section");
    section.dataset.followupSection = "status-reason";
    section.className = "service-detail-status-reason";
    const evidence = body
      .querySelector("#service-detail-evidence")
      ?.closest("section");
    if (evidence) evidence.insertAdjacentElement("beforebegin", section);
    else body.appendChild(section);
  }
  const status = rowStatus(row);
  section.dataset.tone = status;
  section.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = "Current status reason";
  const text = document.createElement("p");
  text.textContent = reason;
  section.append(heading, text);
}

function operatorSectionMeaning(section, id) {
  if (!section) return 0;
  if (id === "runtime") {
    return section.querySelectorAll(".service-detail-metric strong").length;
  }
  if (id === "dependencies") {
    return section.querySelectorAll("a").length;
  }
  return section.textContent?.trim() ? 1 : 0;
}

function cacheKey(row, sectionId) {
  const service =
    row?.dataset?.serviceKey ||
    row?.dataset?.serviceName ||
    row?.id ||
    "service";
  return `${service}:${sectionId}`;
}

function restoreSection(body, row, sectionId) {
  const selector = `[data-operator-section="${sectionId}"]`;
  const section = body.querySelector(selector);
  const strength = operatorSectionMeaning(section, sectionId);
  const key = cacheKey(row, sectionId);
  const cached = retainedDrawerSections.get(key);
  if (strength > 0) {
    retainedDrawerSections.set(key, {
      html: section.outerHTML,
      strength,
      observedAt: Date.now(),
    });
    return;
  }
  if (!cached || Date.now() - cached.observedAt > DRAWER_SETTLE_MS) return;

  const template = document.createElement("template");
  template.innerHTML = cached.html.trim();
  const restored = template.content.firstElementChild;
  if (!restored) return;
  restored.classList.add("service-detail-section--retained");
  restored.dataset.retainedDuringRefresh = "true";
  if (section) {
    section.replaceWith(restored);
    return;
  }
  const performance = body.querySelector(
    '[data-operator-section="performance"]',
  );
  if (performance) performance.insertAdjacentElement("beforebegin", restored);
  else body.appendChild(restored);
}

function stabilizeDrawer() {
  const row = selectedRow();
  const body = document
    .getElementById("service-detail-drawer")
    ?.querySelector(".service-detail-body");
  if (!row || !body) return;
  restoreSection(body, row, "runtime");
  restoreSection(body, row, "dependencies");
  ensureDrawerReason();
}

function scheduleDrawerSync() {
  if (drawerSyncScheduled) return;
  drawerSyncScheduled = true;
  window.requestAnimationFrame(() => {
    drawerSyncScheduled = false;
    stabilizeDrawer();
  });
}

function ensureTrueNasInfo() {
  const panel = document.getElementById("truenas-platform");
  const target = document.getElementById("truenas-platform-target");
  const error = document.getElementById("truenas-platform-error");
  if (!panel || !target || !error) return;

  const parts = String(error.textContent || "")
    .split(" · ")
    .map((part) => part.trim())
    .filter(Boolean);
  const filtered = parts.filter((part) => part !== IMPLEMENTATION_NOTE);
  if (filtered.length !== parts.length) {
    error.textContent = filtered.join(" · ");
    if (filtered.length === 0) error.hidden = true;
  }

  let info = document.getElementById("truenas-platform-info");
  if (!info) {
    info = document.createElement("p");
    info.id = "truenas-platform-info";
    info.className = "truenas-platform-info";
    target.insertAdjacentElement("afterend", info);
  }
  info.textContent =
    "Probe-first rendering: bounded /api/homelab/probes paints the TrueNAS flow quickly; aggregate health only enriches it. This is an information/freshness note, not an error.";
}

function applyRuntimeLayout() {
  const mode = String(
    document.getElementById("runtime-topology")?.dataset?.runtimeMode || "",
  ).toLowerCase();
  const workstation = mode === "local";
  document.body.classList.toggle("health-ui--workstation", workstation);
  if (!workstation) return;

  const actions = document.querySelector(".service-filter-heading-actions");
  if (!actions || document.getElementById("service-filter-dock-toggle")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.id = "service-filter-dock-toggle";
  button.className = "service-filter-density-toggle service-filter-dock-toggle";
  const stored = window.localStorage.getItem("fastapi-health-filter-docked");
  const defaultDocked = window.matchMedia("(min-width: 1500px)").matches;
  let docked = stored == null ? defaultDocked : stored === "true";
  const sync = () => {
    document.body.classList.toggle("health-ui-filter-docked", docked);
    button.textContent = docked ? "Undock" : "Dock left";
    button.setAttribute("aria-pressed", String(docked));
  };
  button.addEventListener("click", () => {
    docked = !docked;
    window.localStorage.setItem("fastapi-health-filter-docked", String(docked));
    sync();
  });
  actions.appendChild(button);
  sync();
}

function syncBoard() {
  document
    .querySelectorAll("[data-service-filter-target]")
    .forEach((row) => annotateStatus(row));
  ensureTrueNasInfo();
  applyRuntimeLayout();
  scheduleDrawerSync();
}

function scheduleBoardSync() {
  if (boardSyncScheduled) return;
  boardSyncScheduled = true;
  window.requestAnimationFrame(() => {
    boardSyncScheduled = false;
    syncBoard();
  });
}

function observeDrawer() {
  const body = document
    .getElementById("service-detail-drawer")
    ?.querySelector(".service-detail-body");
  if (!body) return;
  new MutationObserver(scheduleDrawerSync).observe(body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}

function observeTrueNasError() {
  const error = document.getElementById("truenas-platform-error");
  if (!error) return;
  new MutationObserver(scheduleBoardSync).observe(error, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["hidden"],
  });
}

export function installHealthUiResponsiveFollowup() {
  applyRuntimeLayout();
  observeDrawer();
  observeTrueNasError();
  document.addEventListener("health-board-refreshed", scheduleBoardSync);
  document.addEventListener("service-filter-changed", scheduleBoardSync);
  document.addEventListener("click", (event) => {
    if (
      event.target instanceof Element &&
      event.target.closest(".service-detail-trigger")
    ) {
      window.setTimeout(scheduleDrawerSync, 0);
    }
  });
  scheduleBoardSync();
}
