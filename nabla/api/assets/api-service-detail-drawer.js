import { fetchHealthBoard } from "./api-health-board.js";
import { gatusCoverage, gatusServiceEvidence } from "./api-service-gatus-coverage.js";
import { serviceRelations } from "./api-service-relations.js";
import { fetchTopology } from "./api-topology-data.js";

const ROW_SELECTOR = "[data-service-filter-target]";
const OBSERVED_CONTAINERS = [
  "health-checks",
  "health-services-groups",
  "sickz-checks",
  "truenas-platform",
];

let activeRow = null;
let activeTrigger = null;
let activeIdentity = null;
let refreshScheduled = false;
let latestTopology = null;
let latestSnapshot = null;

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

function rowIdentity(row) {
  if (!row) return null;
  return {
    topologyId: String(row.dataset.topologyId || "").trim(),
    serviceKey: String(row.dataset.serviceKey || "").trim(),
    serviceName: String(row.dataset.serviceName || "").trim(),
    serviceUrl: safeHttpUrl(row.dataset.serviceUrl) || "",
  };
}

function sameIdentity(row, identity) {
  if (!row || !identity) return false;
  const candidate = rowIdentity(row);
  for (const key of ["topologyId", "serviceKey", "serviceName", "serviceUrl"]) {
    if (identity[key] && candidate?.[key] === identity[key]) return true;
  }
  return false;
}

function replacementRow(identity) {
  if (!identity) return null;
  return [...document.querySelectorAll(ROW_SELECTOR)].find((row) =>
    sameIdentity(row, identity),
  );
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
    ["Local health", row.dataset.localState],
    ["Dependency health", row.dataset.dependencyState],
    ["Risk", row.dataset.riskState],
    ["Downstream impact", Number(row.dataset.downstreamCount) > 0
      ? row.dataset.downstreamCount : ""],
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
      <div id="service-detail-summary" class="service-detail-summary" aria-live="polite"></div>
      <section aria-labelledby="service-detail-relations-title">
        <h3 id="service-detail-relations-title">Related catalogue services</h3>
        <div id="service-detail-relations" class="service-detail-relations"></div>
      </section>
      <section id="service-detail-gatus-section" aria-labelledby="service-detail-gatus-title" hidden>
        <h3 id="service-detail-gatus-title">Gatus monitored services</h3>
        <div id="service-detail-gatus" class="service-detail-relations"></div>
      </section>
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
  const rank = { fail: 0, warn: 1, unknown: 2, neutral: 3, ok: 4 };
  const probes = probeEntries(row).sort(
    (left, right) => (rank[left.tone] ?? 2) - (rank[right.tone] ?? 2)
  );
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
    const state = document.createElement("span");
    state.className = "service-detail-probe-state";
    state.textContent = probe.disabled
      ? "NOT RUN"
      : probe.tone === "ok"
        ? "UP"
        : probe.tone === "fail"
          ? "FAILED"
          : probe.tone === "warn"
            ? "WARNING"
            : "UNVERIFIED";
    heading.appendChild(state);
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

function matchingCatalogueRow(id) {
  const candidates = [...document.querySelectorAll(ROW_SELECTOR)].filter(
    (row) =>
      row.dataset.topologyId === id ||
      row.dataset.serviceKey === id ||
      row.dataset.serviceKey?.replace(/^albandrieu_/, "").replaceAll("_", "-") === id,
  );
  // Never choose an arbitrary destination when multiple cards share an ID.
  if (candidates.length === 1) return candidates[0];
  // The health and external views may contain the same canonical identity.
  // Prefer the canonical grouped health service without guessing by name.
  const primary = candidates.filter((row) =>
    row.closest("#health-services-groups")
  );
  return primary.length === 1 ? primary[0] : null;
}

function linkedCatalogueItem(entry, { status = "", type = "" } = {}) {
  const target = matchingCatalogueRow(entry.id);
  const wrap = document.createElement("div");
  wrap.className = "service-detail-relation";
  const link = document.createElement(target ? "button" : "span");
  if (target) {
    link.type = "button";
    link.className = "service-detail-relation-link";
    link.addEventListener("click", () => {
      openDrawer(target, target.querySelector(":scope > .service-detail-trigger"));
    });
    link.setAttribute("aria-label", `View ${entry.name} service diagnostics`);
  }
  link.textContent = entry.name;
  wrap.appendChild(link);
  const detail = document.createElement("small");
  detail.textContent = [type || entry.type, status, entry.required ? "required" : ""]
    .filter(Boolean).join(" · ");
  wrap.appendChild(detail);
  return wrap;
}

function renderRelations(drawer, row) {
  const host = drawer.querySelector("#service-detail-relations");
  host?.replaceChildren();
  if (!host) return;
  const id = row.dataset.topologyId;
  const relations = serviceRelations(latestTopology, id);
  const groups = [
    ["Upstream / dependencies", relations.dependencies],
    ["Downstream / dependents", relations.dependents],
  ];
  let found = false;
  for (const [label, items] of groups) {
    if (!items.length) continue;
    found = true;
    const title = document.createElement("strong");
    title.className = "service-detail-relation-group";
    title.textContent = label;
    host.appendChild(title);
    items.forEach((item) => host.appendChild(linkedCatalogueItem(item)));
  }
  if (!found) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent = latestTopology?.nodes?.length
      ? "No published dependencies for this catalogue identity."
      : "Public topology unavailable; relations not verified.";
    host.appendChild(empty);
  }
}

function renderProbeSummary(drawer, row) {
  const host = drawer.querySelector("#service-detail-summary");
  if (!host) return;
  const probes = probeEntries(row).filter((probe) => !probe.disabled);
  const failed = probes.filter((probe) => probe.tone === "fail").length;
  const warnings = probes.filter((probe) => probe.tone === "warn").length;
  const unknown = probes.filter((probe) =>
    !["ok", "fail", "warn"].includes(probe.tone)
  ).length;
  host.textContent = probes.length
    ? `Probe evidence · ${failed} failing · ${warnings} warning · ${unknown} unverified · ${probes.length} observed badges`
    : "No direct probe evidence; this is not proof of service health.";
  host.dataset.tone = failed > 0 ? "fail" : warnings > 0 ? "warn" : "unknown";
}

function renderGatusFleet(drawer, row) {
  const section = drawer.querySelector("#service-detail-gatus-section");
  const host = drawer.querySelector("#service-detail-gatus");
  if (!host || !section) return;
  host.replaceChildren();
  const isGatus = row.dataset.serviceKey === "gatus" ||
    row.dataset.topologyId === "gatus";
  section.hidden = !isGatus;
  if (!isGatus) return;
  const fleet = gatusCoverage(latestSnapshot);
  const totals = document.createElement("p");
  totals.className = "service-detail-empty";
  totals.textContent = fleet.state !== "observed"
    ? `Gatus coverage unavailable: ${fleet.reason}. No probes declared healthy.`
    : `${fleet.up} UP · ${fleet.down} DOWN · ${fleet.observedServices} labelled services · ${fleet.observedProbes} protocol probes. This is not full catalogue coverage.`;
  host.appendChild(totals);
  if (fleet.state !== "observed") return;
  if (fleet.failures.length === 0) {
    const note = document.createElement("p");
    note.className = "service-detail-empty";
    note.textContent = "No failed labelled probes observed in this snapshot. Missing or stale checks remain unverified.";
    host.appendChild(note);
  }
  fleet.failures.slice(0, 20).forEach((failure) => {
    host.appendChild(linkedCatalogueItem(
      { id: failure.id, name: failure.id },
      { type: failure.type, status: "observed DOWN" },
    ));
  });
  if (fleet.failures.length > 20) {
    const more = document.createElement("p");
    more.className = "service-detail-empty";
    more.textContent = `${fleet.failures.length - 20} more failed probes; see the private Gatus console.`;
    host.appendChild(more);
  }
}

function renderDrawer(row, { force = false } = {}) {
  const drawer = ensureDrawer();
  const signature = JSON.stringify({
    row: drawerSignature(row),
    topologySource: latestTopology?.source,
    topologyNodes: latestTopology?.nodes?.length,
    telemetryCheckedAt: latestSnapshot?.platform_metrics?.generated_at,
  });
  const serviceKey = String(
    row.dataset.serviceKey || row.dataset.serviceName || "",
  );
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
  renderProbeSummary(drawer, row);
  renderRelations(drawer, row);
  renderGatusFleet(drawer, row);
  drawer.dataset.serviceKey = serviceKey;
  drawer.dataset.renderSignature = signature;
}

function openDrawer(row, trigger) {
  if (!row) return;
  if (activeRow && activeRow !== row) delete activeRow.dataset.detailSelected;
  activeRow = row;
  activeIdentity = rowIdentity(row);
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
  activeIdentity = null;
  if (restoreFocus && trigger?.isConnected) {
    trigger.focus({ preventScroll: true });
  }
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

function reattachActiveRow() {
  if (activeRow?.isConnected) return true;
  const replacement = replacementRow(activeIdentity);
  if (!replacement) return false;
  activeRow = replacement;
  activeRow.dataset.detailSelected = "true";
  activeTrigger =
    activeRow.querySelector(":scope > .service-detail-trigger") ||
    activeTrigger;
  return true;
}

function scheduleActiveRefresh() {
  if (!activeRow || refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    if (!reattachActiveRow()) {
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
        "data-topology-id",
        "data-local-state",
        "data-dependency-state",
        "data-risk-state",
        "data-downstream-count",
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
  // Reuse the same cached public topology and health snapshot as the board.
  // Do not request one provider endpoint per card or probe.
  fetchTopology().then((topology) => {
    latestTopology = topology;
    scheduleActiveRefresh();
  }).catch(() => {});
  document.addEventListener("health-board-refreshed", () => {
    fetchHealthBoard().then((snapshot) => {
      latestSnapshot = snapshot;
      scheduleActiveRefresh();
    }).catch(() => {
      latestSnapshot = null;
      scheduleActiveRefresh();
    });
  });
  ensureDrawer();
  decorateRows();
  observeRows();
  installKeyboardClose();
  document.addEventListener("service-filter-changed", scheduleActiveRefresh);
  document.addEventListener("health-board-refreshed", scheduleActiveRefresh);
}
