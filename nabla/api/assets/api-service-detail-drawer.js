import { fetchHealthBoard } from "./api-health-board.js";
import { gatusCoverage, gatusCatalogueCoverage } from "./api-service-gatus-coverage.js";
import { serviceRelations } from "./api-service-relations.js";
import { fetchTopology } from "./api-topology-data.js";
import { EVIDENCE_GROUPS, evidenceAdvice, evidenceCounts, evidenceGroup, requestedServiceId, sanitizedEvidence, validServiceId } from "./api-service-evidence-ux.js";

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
let nextTopologyRetryAt = 0;
let evidenceIssuesOnly = false;
const navigationTrail = [];

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
    ["Exposure policy", row.dataset.exposurePolicy],
    ["Security posture", row.dataset.exposureSummary],
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
  return [...row.querySelectorAll(".service-probe")]
    .filter((probe) => probe.dataset.probeKind !== "issues")
    .map((probe) => ({
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
      <div class="service-detail-header-actions">
        <button type="button" id="service-detail-back" class="service-detail-back" hidden>← Back</button>
        <button type="button" class="service-detail-close" aria-label="Close service details">×</button>
      </div>
    </header>
    <div class="service-detail-body">
      <div id="service-detail-meta" class="service-detail-meta"></div>
      <div id="service-detail-link" class="service-detail-link"></div>
      <div id="service-detail-summary" class="service-detail-summary" aria-live="polite"></div>
      <section aria-labelledby="service-detail-exposure-title">
        <h3 id="service-detail-exposure-title">Exposure security policy</h3>
        <div id="service-detail-exposure" class="service-detail-exposure"></div>
      </section>
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
  drawer.querySelector("#service-detail-back")?.addEventListener("click", () => {
    const previous = navigationTrail.pop();
    const target = previous && matchingCatalogueRow(previous);
    if (target) openDrawer(target, target.querySelector(":scope > .service-detail-trigger"), { recordTrail: false });
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
  const key = catalogueRouteId(row);
  if (key) {
    const permalink = document.createElement("a");
    const url = new URL(window.location.href);
    url.searchParams.set("service", key);
    permalink.href = url.href;
    permalink.textContent = "Direct link to diagnostics";
    host.appendChild(permalink);
  }
}

function renderExposurePolicy(drawer, row) {
  const host = drawer.querySelector("#service-detail-exposure");
  host?.replaceChildren();
  if (!host) return;
  const verdict = String(row.dataset.exposureVerdict || "unknown");
  const summary = String(row.dataset.exposureSummary || "Exposure policy not verified");
  host.dataset.exposureVerdict = verdict;
  const status = document.createElement("strong");
  status.className = "service-detail-exposure-verdict";
  status.textContent = summary;
  const description = document.createElement("p");
  description.textContent =
    "Security posture is independent of application uptime. " +
    "An internal-only service must not expose a public HTTP entry point, " +
    "even when it returns HTTP 401 or 403. Cloudflare Tunnel is routing; " +
    "Access is the authorization layer.";
  const sickzLink = document.createElement("a");
  // Prefer the matching /sickz row when it exists; otherwise use the
  // section anchor. No external URL or guess from a shared host is needed.
  const key = String(row.dataset.topologyId || "");
  const exposureRow = key && document.getElementById(`service-exposure-${key}`);
  sickzLink.href = exposureRow ? `#${exposureRow.id}` : "#sickz-checks";
  sickzLink.textContent = "Review /sickz outside-in evidence";
  sickzLink.addEventListener("click", () => closeDrawer({ restoreFocus: false }));
  host.append(status, description, sickzLink);
}

function renderEvidence(drawer, row) {
  const host = drawer.querySelector("#service-detail-evidence");
  if (!host) return;
  host.replaceChildren();
  const probes = probeEntries(row);
  const counts = evidenceCounts(probes);
  const filter = document.createElement("label");
  filter.className = "service-detail-issues-filter";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = evidenceIssuesOnly;
  checkbox.addEventListener("change", () => {
    evidenceIssuesOnly = checkbox.checked;
    renderEvidence(drawer, row);
  });
  filter.append(checkbox, document.createTextNode(" Show failed and warning signals only"));
  const count = document.createElement("small");
  count.textContent = counts.failed + " failed · " + counts.warning + " warning · " +
    counts.unknown + " unknown · " + counts.notRun + " not run";
  host.append(filter, count);
  if (probes.length === 0) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent = "No probe evidence attached; service health is unverified.";
    host.appendChild(empty);
    return;
  }
  const rank = { fail: 0, warn: 1, unknown: 2, neutral: 3, ok: 4 };
  const visible = probes.filter((probe) => !evidenceIssuesOnly ||
    (!probe.disabled && ["fail", "warn"].includes(probe.tone)));
  if (visible.length === 0) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent = "No failed or warning probes in the observed snapshot. Unknown or missing checks are not evidence of success.";
    host.appendChild(empty);
    return;
  }
  for (const category of EVIDENCE_GROUPS) {
    const grouped = visible.filter((probe) => evidenceGroup(probe) === category)
      .sort((left, right) => (rank[left.tone] ?? 2) - (rank[right.tone] ?? 2));
    if (!grouped.length) continue;
    const section = document.createElement("details");
    section.className = "service-detail-evidence-group";
    section.open = evidenceIssuesOnly || grouped.some((probe) => ["fail", "warn"].includes(probe.tone));
    const summary = document.createElement("summary");
    const failures = grouped.filter((probe) => probe.tone === "fail" && !probe.disabled).length;
    summary.textContent = category + " · " + grouped.length + " signals" +
      (failures ? " · " + failures + " FAILED" : "");
    section.appendChild(summary);
    for (const probe of grouped) {
      const item = document.createElement("article");
      item.className = "service-detail-probe service-detail-probe--" + (probe.disabled ? "unknown" : probe.tone);
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
      }
      const labelWrap = document.createElement("span");
      labelWrap.className = "service-detail-probe-name";
      labelWrap.append(icon, label);
      heading.appendChild(labelWrap);
      const state = document.createElement("span");
      state.className = "service-detail-probe-state";
      state.textContent = probe.disabled ? "NOT RUN" :
        probe.tone === "ok" ? "UP" :
        probe.tone === "fail" ? "FAILED" :
        probe.tone === "warn" ? "WARNING" : "UNVERIFIED";
      heading.appendChild(state);
      const detail = document.createElement("p");
      detail.textContent = sanitizedEvidence(probe.detail);
      item.append(heading, detail);
      if (["fail", "warn"].includes(probe.tone) && !probe.disabled) {
        const advice = evidenceAdvice(probe);
        const explanation = document.createElement("p");
        explanation.className = "service-detail-probe-advice";
        explanation.textContent = advice.reason + " Action: " + advice.action;
        item.appendChild(explanation);
      }
      section.appendChild(item);
    }
    host.appendChild(section);
  }
}

function catalogueRouteId(row) {
  const id = String(row?.dataset?.topologyId || row?.dataset?.serviceKey || "");
  return validServiceId(id) ? id : null;
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
  link.textContent = target && entry.name === entry.id
    ? displayName(target)
    : entry.name;
  wrap.appendChild(link);
  const detail = document.createElement("small");
  const cardState = target ? `card: ${normalizedStatus(target)}` : "card not shown";
  detail.textContent = [
    type || entry.type, status, entry.required ? "required" : "",
    cardState,
  ].filter(Boolean).join(" · ");
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
  const disabled = probeEntries(row).filter((probe) => probe.disabled).length;
  const timestamp = latestSnapshot?.platform_metrics?.generated_at;
  const observationTime = Number.isFinite(Date.parse(timestamp)) ? " · Metrics snapshot: " + new Date(timestamp).toLocaleString() : " · Metrics snapshot: unverified";
  host.textContent = probes.length
    ? `Diagnostics · ${failed} failed · ${warnings} warning · ${unknown} unknown · ${disabled} not run · ${probes.length} reported signals. See the grouped evidence below.` + observationTime
    : "No direct probe evidence; this is not proof of service health." + observationTime;
  host.dataset.tone = failed > 0 ? "fail" : warnings > 0 ? "warn" : "unknown";
}

function renderGatusFleet(drawer, row) {
  const section = drawer.querySelector("#service-detail-gatus-section");
  const host = drawer.querySelector("#service-detail-gatus");
  if (!host || !section) return;
  host.replaceChildren();
  const isGatus = row.dataset.serviceKey === "gatus" ||
    row.dataset.topologyId === "gatus" ||
    row.dataset.serviceKey === "albandrieu_gatus";
  section.hidden = !isGatus;
  if (!isGatus) return;
  const fleet = gatusCoverage(latestSnapshot);
  const ids = [...new Set([...document.querySelectorAll(
    "#health-services-groups [data-service-filter-target]"
  )].map((card) => catalogueRouteId(card)).filter(Boolean))];
  const catalogue = gatusCatalogueCoverage(latestSnapshot, ids);
  const coverageSummary = document.createElement("p");
  coverageSummary.className = "service-detail-coverage";
  coverageSummary.textContent = catalogue.state === "observed"
    ? "Catalogue sampled: " + catalogue.withSamples + "/" + catalogue.catalogueTotal +
      " visible cards · " + catalogue.withoutSamples.length + " with no labelled sample. " +
      "Gatus monitor configuration parity has not been verified."
    : "Catalogue coverage unknown: " + catalogue.reason +
      ". No monitor can be marked UP from this snapshot.";
  host.appendChild(coverageSummary);
  const totals = document.createElement("p");
  totals.className = "service-detail-empty";
  totals.textContent = fleet.state !== "observed"
    ? `Gatus coverage unavailable: ${fleet.reason}. No probes declared healthy.`
    : `${fleet.up} UP · ${fleet.down} DOWN · ${fleet.observedServices} labelled services · ${fleet.observedProbes} protocol probes. This is not full catalogue coverage.`;
  host.appendChild(totals);
  if (fleet.state !== "observed") return;
  if (catalogue.withoutSamples.length) {
    const heading = document.createElement("strong");
    heading.className = "service-detail-relation-group";
    heading.textContent = "Visible catalogue cards with no sampled monitor (" +
      catalogue.withoutSamples.length + ")";
    host.appendChild(heading);
    for (const id of catalogue.withoutSamples.slice(0, 25)) {
      host.appendChild(linkedCatalogueItem({ id, name: id }, {
        type: "No sample", status: "not proven monitored",
      }));
    }
    if (catalogue.withoutSamples.length > 25) {
      const tail = document.createElement("p");
      tail.className = "service-detail-empty";
      tail.textContent = "Additional cards have no usable Gatus evidence.";
      host.appendChild(tail);
    }
  }
  // The catalogue can contain services with no Gatus monitor. Never show
  // those as green, nor treat a healthy Gatus scheduler as healthy targets.
  const views = [
    ["Failing checks", fleet.failures, "observed DOWN"],
    ["Checks without usable samples", fleet.missing, "NOT OBSERVED"],
    ["Successful checks", fleet.successes, "observed UP"],
  ];
  for (const [title, entries, status] of views) {
    const heading = document.createElement("strong");
    heading.className = "service-detail-relation-group";
    heading.textContent = `${title} (${entries.length})`;
    host.appendChild(heading);
    if (entries.length === 0) {
      const empty = document.createElement("p");
      empty.className = "service-detail-empty";
      empty.textContent = "None in this bounded snapshot.";
      host.appendChild(empty);
      continue;
    }
    entries.slice(0, 25).forEach((entry) => {
      host.appendChild(linkedCatalogueItem(
        { id: entry.id, name: entry.id },
        { type: entry.type, status },
      ));
    });
    if (entries.length > 25) {
      const more = document.createElement("p");
      more.className = "service-detail-empty";
      more.textContent = `${entries.length - 25} more; open the private Gatus console.`;
      host.appendChild(more);
    }
  }
  const caveat = document.createElement("p");
  caveat.className = "service-detail-empty";
  caveat.textContent =
    "Unlisted catalogue services have unknown Gatus coverage. " +
    "A successful Gatus scrape proves only that its metrics endpoint responds.";
  host.appendChild(caveat);
}

function renderDrawer(row, { force = false } = {}) {
  const drawer = ensureDrawer();
  const signature = JSON.stringify({
    row: drawerSignature(row),
    topologySource: latestTopology?.source,
    topologyNodes: latestTopology?.nodes?.length,
    telemetryCheckedAt: latestSnapshot?.platform_metrics?.generated_at,
    exposure: row.dataset.exposureSummary,
    exposureVerdict: row.dataset.exposureVerdict,
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
  renderExposurePolicy(drawer, row);
  renderEvidence(drawer, row);
  renderProbeSummary(drawer, row);
  renderRelations(drawer, row);
  renderGatusFleet(drawer, row);
  drawer.dataset.serviceKey = serviceKey;
  drawer.dataset.renderSignature = signature;
}

function updateServiceUrl(row) {
  const id = catalogueRouteId(row);
  if (!id) return;
  const url = new URL(window.location.href);
  if (url.searchParams.get("service") === id) return;
  url.searchParams.set("service", id);
  window.history.pushState(window.history.state, "", url);
}

function syncDrawerFromUrl() {
  const id = requestedServiceId(window.location.search);
  if (!id) {
    if (activeRow) closeDrawer({ restoreFocus: false, syncUrl: false });
    return;
  }
  const row = matchingCatalogueRow(id);
  if (row && (!activeRow || catalogueRouteId(activeRow) !== id)) {
    openDrawer(row, row.querySelector(":scope > .service-detail-trigger"), {
      syncUrl: false, recordTrail: false,
    });
  }
}

function openDrawer(row, trigger, { syncUrl = true, recordTrail = true } = {}) {
  if (!row) return;
  if (activeRow && activeRow !== row) {
    if (recordTrail) {
      const oldId = catalogueRouteId(activeRow);
      if (oldId) navigationTrail.push(oldId);
      if (navigationTrail.length > 20) navigationTrail.shift();
    }
    delete activeRow.dataset.detailSelected;
  }
  activeRow = row;
  activeIdentity = rowIdentity(row);
  activeTrigger = trigger || null;
  activeRow.dataset.detailSelected = "true";
  renderDrawer(row, { force: true });
  const drawer = ensureDrawer();
  drawer.hidden = false;
  const back = drawer.querySelector("#service-detail-back");
  if (back) back.hidden = navigationTrail.length === 0;
  if (syncUrl) updateServiceUrl(row);
  drawer.focus({ preventScroll: true });
  document.dispatchEvent(new CustomEvent("service-detail-selected", { detail: { serviceId: catalogueRouteId(row) } }));
}

function closeDrawer({ restoreFocus = true, syncUrl = true } = {}) {
  const drawer = document.getElementById("service-detail-drawer");
  if (drawer) drawer.hidden = true;
  if (activeRow) delete activeRow.dataset.detailSelected;
  const trigger = activeTrigger;
  activeRow = null;
  activeTrigger = null;
  activeIdentity = null;
  navigationTrail.length = 0;
  if (syncUrl) {
    const url = new URL(window.location.href);
    if (url.searchParams.has("service")) {
      url.searchParams.delete("service");
      window.history.replaceState(window.history.state, "", url);
    }
  }
  if (restoreFocus && trigger?.isConnected) {
    trigger.focus({ preventScroll: true });
  }
}

function updateDetailTrigger(row, trigger) {
  const counts = evidenceCounts(probeEntries(row));
  const text = counts.failed ? "Details · " + counts.failed + " failed"
    : counts.warning ? "Details · " + counts.warning + " warning" : "Details";
  if (trigger.textContent !== text) trigger.textContent = text;
  const tone = counts.failed ? "fail" : counts.warning ? "warn" : "neutral";
  if (trigger.dataset.issues !== tone) trigger.dataset.issues = tone;
  const title = "Open diagnostics for " + displayName(row) +
    ": " + counts.failed + " failed, " + counts.warning + " warnings, " +
    counts.unknown + " unknown, " + counts.notRun + " not run";
  if (trigger.getAttribute("aria-label") !== title) {
    trigger.setAttribute("aria-label", title);
  }
}

function ensureDetailTrigger(row) {
  if (!(row instanceof HTMLElement)) return;
  const current = row.querySelector(":scope > .service-detail-trigger");
  if (current) {
    updateDetailTrigger(row, current);
    return;
  }
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "service-detail-trigger";
  updateDetailTrigger(row, trigger);
  trigger.setAttribute("aria-haspopup", "dialog");
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
        "data-exposure-verdict",
        "data-exposure-summary",
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
    // Public-topology may initially return 401/403 before an owner session.
    // Retry only on board refresh and at most every two minutes, not per card.
    if ((!latestTopology || !latestTopology.nodes?.length) &&
        Date.now() >= nextTopologyRetryAt) {
      nextTopologyRetryAt = Date.now() + 120000;
      fetchTopology({ force: true }).then((topology) => {
        latestTopology = topology;
        scheduleActiveRefresh();
      }).catch(() => {});
    }
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
  document.addEventListener("health-board-refreshed", () => {
    // Rows may be replaced asynchronously after the board event.
    window.requestAnimationFrame(() => {
      decorateRows();
      document.querySelectorAll(ROW_SELECTOR).forEach((row) => {
        const trigger = row.querySelector(":scope > .service-detail-trigger");
        if (!trigger) return;
        updateDetailTrigger(row, trigger);
      });
      syncDrawerFromUrl();
    });
  });
  window.addEventListener("popstate", syncDrawerFromUrl);
  syncDrawerFromUrl();
}
