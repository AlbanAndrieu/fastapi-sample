const ROW_SELECTOR = "[data-service-filter-target]";
const OBSERVED_CONTAINERS = [
  "health-checks",
  "health-services-groups",
  "sickz-checks",
  "truenas-platform",
];

let activeRow = null;
let activeTrigger = null;
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

function displayName(row) {
  return (
    String(row?.dataset?.serviceName || "").trim() ||
    row?.querySelector?.("a, strong, h3, h4")?.textContent?.trim() ||
    String(row?.dataset?.serviceKey || "Service").trim()
  );
}

function safeHttpUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(String(value), window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function metadataEntries(row) {
  const entries = [
    ["Status", normalizedStatus(row)],
    ["Key", row.dataset.serviceKey],
    ["Group", row.dataset.presentationGroup],
    ["Environment", row.dataset.environments],
    ["Exposure", row.dataset.exposureScope],
    ["Ingress", row.dataset.exposureMode],
    ["Policy", row.dataset.exposurePolicy],
    ["Change", row.dataset.healthChange],
  ];
  return entries.filter(([, value]) => String(value || "").trim());
}

function probeEntries(row) {
  return [...row.querySelectorAll(".service-probe")].map((probe) => ({
    kind: probe.dataset.probeKind || "probe",
    label:
      probe.querySelector(".service-probe-label")?.textContent?.trim() ||
      probe.dataset.probeKind ||
      "Probe",
    icon:
      probe.querySelector(".service-probe-icon")?.textContent?.trim() || "•",
    href: probe instanceof HTMLAnchorElement ? safeHttpUrl(probe.href) : null,
    detail:
      probe.getAttribute("aria-label") || probe.title || "No detail available",
    tone:
      [...probe.classList]
        .find((name) => name.startsWith("service-probe--"))
        ?.replace("service-probe--", "") || "unknown",
    disabled: probe.dataset.probeDisabled === "true",
  }));
}

function drawerSignature(row) {
  return JSON.stringify({
    name: displayName(row),
    url: safeHttpUrl(row.dataset.serviceUrl),
    metadata: metadataEntries(row),
    probes: probeEntries(row),
  });
}

function ensureDrawer() {
  let drawer = document.getElementById("service-detail-drawer");
  if (drawer) return drawer;

  drawer = document.createElement("aside");
  drawer.id = "service-detail-drawer";
  drawer.className = "service-detail-drawer";
  drawer.hidden = true;
  drawer.tabIndex = -1;
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-modal", "false");
  drawer.setAttribute("aria-labelledby", "service-detail-title");
  drawer.innerHTML = `
    <header class="service-detail-header">
      <div>
        <span class="service-detail-kicker">Service diagnostics</span>
        <h2 id="service-detail-title">Service</h2>
      </div>
      <button type="button" class="service-detail-close" aria-label="Close service details">×</button>
    </header>
    <div class="service-detail-body">
      <div id="service-detail-meta" class="service-detail-meta"></div>
      <div id="service-detail-link" class="service-detail-link"></div>
      <section aria-labelledby="service-detail-evidence-title">
        <h3 id="service-detail-evidence-title">Probe evidence</h3>
        <div id="service-detail-evidence" class="service-detail-evidence"></div>
      </section>
    </div>`;

  drawer
    .querySelector(".service-detail-close")
    ?.addEventListener("click", () => {
      closeDrawer();
    });
  document.body.appendChild(drawer);
  return drawer;
}

function renderMetadata(drawer, row) {
  const host = drawer.querySelector("#service-detail-meta");
  host?.replaceChildren();
  if (!host) return;
  for (const [label, value] of metadataEntries(row)) {
    const item = document.createElement("div");
    item.className = "service-detail-meta-item";
    const term = document.createElement("span");
    term.textContent = label;
    const content = document.createElement("strong");
    content.textContent = String(value);
    item.append(term, content);
    host.appendChild(item);
  }
}

function renderLink(drawer, row) {
  const host = drawer.querySelector("#service-detail-link");
  host?.replaceChildren();
  if (!host) return;
  const href = safeHttpUrl(row.dataset.serviceUrl);
  if (!href) return;
  const link = document.createElement("a");
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Open service ↗";
  host.appendChild(link);
}

function renderEvidence(drawer, row) {
  const host = drawer.querySelector("#service-detail-evidence");
  host?.replaceChildren();
  if (!host) return;
  const probes = probeEntries(row);
  if (probes.length === 0) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent = "No probe evidence is attached to this service row.";
    host.appendChild(empty);
    return;
  }

  for (const probe of probes) {
    const item = document.createElement("article");
    item.className = `service-detail-probe service-detail-probe--${probe.tone}`;
    if (probe.disabled) item.dataset.disabled = "true";
    const heading = document.createElement("div");
    heading.className = "service-detail-probe-heading";
    const icon = document.createElement("span");
    icon.className = "service-detail-probe-icon";
    icon.dataset.tone = probe.disabled ? "neutral" : probe.tone;
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = probe.icon;
    const label = document.createElement(probe.href ? "a" : "strong");
    label.className = "service-detail-probe-label";
    label.textContent = probe.label;
    if (label instanceof HTMLAnchorElement && probe.href) {
      label.href = probe.href;
      label.target = "_blank";
      label.rel = "noopener noreferrer";
      label.title = `Open ${probe.label} diagnostics`;
    }
    const labelWrap = document.createElement("span");
    labelWrap.className = "service-detail-probe-name";
    labelWrap.append(icon, label);
    heading.appendChild(labelWrap);
    const normalizedLabel = probe.label.trim().toLowerCase();
    const normalizedKind = probe.kind.trim().toLowerCase();
    if (normalizedKind && normalizedKind !== normalizedLabel) {
      const kind = document.createElement("span");
      kind.textContent = probe.kind;
      heading.appendChild(kind);
    }
    const detail = document.createElement("p");
    detail.textContent = probe.detail;
    item.append(heading, detail);
    host.appendChild(item);
  }
}

function renderDrawer(row, { force = false } = {}) {
  const drawer = ensureDrawer();
  const signature = drawerSignature(row);
  const serviceKey = String(row.dataset.serviceKey || row.dataset.serviceName || "");
  if (
    !force &&
    drawer.dataset.serviceKey === serviceKey &&
    drawer.dataset.renderSignature === signature
  ) {
    return;
  }
  const title = drawer.querySelector("#service-detail-title");
  if (title) title.textContent = displayName(row);
  renderMetadata(drawer, row);
  renderLink(drawer, row);
  renderEvidence(drawer, row);
  drawer.dataset.serviceKey = serviceKey;
  drawer.dataset.renderSignature = signature;
}

function openDrawer(row, trigger) {
  if (!row) return;
  if (activeRow && activeRow !== row) delete activeRow.dataset.detailSelected;
  activeRow = row;
  activeTrigger = trigger || null;
  activeRow.dataset.detailSelected = "true";
  renderDrawer(row, { force: true });
  const drawer = ensureDrawer();
  drawer.hidden = false;
  drawer.focus({ preventScroll: true });
}

function closeDrawer({ restoreFocus = true } = {}) {
  const drawer = document.getElementById("service-detail-drawer");
  if (drawer) drawer.hidden = true;
  if (activeRow) delete activeRow.dataset.detailSelected;
  const trigger = activeTrigger;
  activeRow = null;
  activeTrigger = null;
  if (restoreFocus && trigger?.isConnected)
    trigger.focus({ preventScroll: true });
}

function ensureDetailTrigger(row) {
  if (!(row instanceof HTMLElement)) return;
  if (row.querySelector(":scope > .service-detail-trigger")) return;
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "service-detail-trigger";
  trigger.textContent = "Details";
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute(
    "aria-label",
    `Open diagnostics for ${displayName(row)}`,
  );
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    openDrawer(row, trigger);
  });
  row.appendChild(trigger);
}

function decorateRows(root = document) {
  if (root instanceof HTMLElement && root.matches(ROW_SELECTOR)) {
    ensureDetailTrigger(root);
  }
  root.querySelectorAll?.(ROW_SELECTOR).forEach(ensureDetailTrigger);
}

function scheduleActiveRefresh() {
  if (!activeRow || refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    if (!activeRow?.isConnected) {
      closeDrawer({ restoreFocus: false });
      return;
    }
    renderDrawer(activeRow);
  });
}

function observeRows() {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node instanceof HTMLElement) decorateRows(node);
      });
    }
    scheduleActiveRefresh();
  });

  for (const id of OBSERVED_CONTAINERS) {
    const container = document.getElementById(id);
    if (!container) continue;
    observer.observe(container, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: [
        "class",
        "data-semantic-status",
        "data-health-change",
        "data-exposure-policy",
        "data-exposure-scope",
        "data-exposure-mode",
      ],
    });
  }
}

function installKeyboardClose() {
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !ensureDrawer().hidden) {
      event.preventDefault();
      closeDrawer();
    }
  });
}

export function installServiceDetailDrawer() {
  ensureDrawer();
  decorateRows();
  observeRows();
  installKeyboardClose();
  document.addEventListener("service-filter-changed", scheduleActiveRefresh);
  document.addEventListener("health-board-refreshed", scheduleActiveRefresh);
}
