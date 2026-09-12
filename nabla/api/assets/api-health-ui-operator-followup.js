import { fetchHealthBoard } from "./api-health-board.js";

const CLOUDFLARE_ICON =
  "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/cloudflare.svg";

let latestSnapshot = null;
let catalogPromise = null;
let runtimeDiagnosticsState = null;
let scheduled = false;

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

function healthRow(serviceKey) {
  const wanted = identity(serviceKey);
  return [...document.querySelectorAll(".health-row[data-service-key]")].find(
    (row) => identity(row.dataset.serviceKey) === wanted,
  );
}

function openDiagnostics(serviceKey) {
  const row = healthRow(serviceKey);
  if (!row) return false;
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.querySelector(".service-detail-trigger")?.click();
  return true;
}

function openTrueNasDiagnostics() {
  const panel = document.getElementById("truenas-platform");
  panel?.scrollIntoView({ behavior: "smooth", block: "center" });
  panel?.querySelector(".service-detail-trigger")?.click();
}

function pinTrueNasPlatform() {
  const panel = document.getElementById("truenas-platform");
  if (!panel) return;
  panel.hidden = false;
  panel.dataset.filterPinned = "true";
}

function stageByLabel(predicate) {
  return [...document.querySelectorAll("#truenas-pipeline .truenas-stage")].find(
    (stage) =>
      predicate(normalize(stage.querySelector(".truenas-stage-label")?.textContent)),
  );
}

function serviceButton(label, serviceKey, title, iconSrc = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "truenas-stage-service-link truenas-stage-diagnostic-link";
  button.title = title;
  button.setAttribute("aria-label", title);
  if (iconSrc) {
    const icon = document.createElement("img");
    icon.src = iconSrc;
    icon.alt = "";
    icon.width = 16;
    icon.height = 16;
    icon.loading = "lazy";
    button.appendChild(icon);
  }
  const text = document.createElement("span");
  text.textContent = label;
  button.appendChild(text);
  button.addEventListener("click", () => openDiagnostics(serviceKey));
  return button;
}

function decoratePublicDns() {
  const stage = stageByLabel((label) => label === "public dns");
  const label = stage?.querySelector(".truenas-stage-label");
  if (!stage || !label || label.dataset.cloudflareLinked === "true") return;
  label.dataset.cloudflareLinked = "true";
  label.replaceChildren(
    document.createTextNode("Public DNS · "),
    serviceButton(
      "Cloudflare",
      "cloudflare",
      "Open Cloudflare DNS and provider diagnostics",
      CLOUDFLARE_ICON,
    ),
  );
  const detail = stage.querySelector(".truenas-stage-detail");
  if (detail && !normalize(detail.textContent).includes("cloudflare")) {
    const base = detail.textContent || "Public hostname resolution";
    detail.textContent = `${base} · public DNS is primarily managed in Cloudflare`;
  }
}

function decorateTrueNasApiStage() {
  const stage = stageByLabel((label) => label.includes("truenas api"));
  const label = stage?.querySelector(".truenas-stage-label");
  if (!stage || !label || label.dataset.coreDiagnosticsLinked === "true") return;
  const text = label.textContent?.trim() || "TrueNAS API";
  label.dataset.coreDiagnosticsLinked = "true";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "truenas-stage-service-link truenas-stage-diagnostic-link";
  button.textContent = text;
  button.title = "Open Core drill-down · TrueNAS platform + API diagnostics";
  button.addEventListener("click", openTrueNasDiagnostics);
  label.replaceChildren(button);
}

function deduplicateProbeEvidence() {
  const rows = document.querySelectorAll(".health-row[data-service-filter-target]");
  for (const row of rows) {
    for (const strip of row.querySelectorAll(".service-probe-strip")) {
      const seen = new Set();
      const badges = [...strip.querySelectorAll("[data-probe-kind]")];
      for (const badge of badges.reverse()) {
        const key = badge.dataset.probeKind || "";
        if (!key || !seen.has(key)) {
          seen.add(key);
          continue;
        }
        badge.remove();
      }
    }
    const telemetry = [...row.querySelectorAll(":scope > .health-row-telemetry")];
    for (const duplicate of telemetry.slice(0, -1)) duplicate.remove();
  }
}

function makePlaneLabelLink(label) {
  const strong = label.querySelector(":scope > strong");
  if (!strong || strong.querySelector("a")) return;
  const target = label.querySelector(":scope > a, :scope > span");
  const raw = String(
    target?.getAttribute?.("href") || target?.textContent || "",
  ).trim();
  if (!raw || raw === "LAN target unavailable") return;
  const href = /^https?:\/\//i.test(raw) ? raw : `http://${raw}`;
  const link = document.createElement("a");
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = strong.textContent || "Open";
  link.title = `Open ${raw}`;
  strong.replaceChildren(link);
}

function linkProbePlanes() {
  const labels = document.querySelectorAll(
    ".service-probe-plane-label--public, .service-probe-plane-label--lan",
  );
  labels.forEach(makePlaneLabelLink);
}

async function loadCatalog() {
  if (catalogPromise) return catalogPromise;
  catalogPromise = fetch("/api/homelab-services", {
    headers: { Accept: "application/json" },
  })
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);
  return catalogPromise;
}

function catalogServices(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.services)) return payload.services;
  return [];
}

async function replaceLegacyExposureLabels() {
  const services = catalogServices(await loadCatalog());
  if (services.length === 0) return;
  const byIdentity = new Map();
  for (const service of services) {
    const description = String(service?.description || "").trim();
    if (!description) continue;
    for (const value of [
      service?.id,
      service?.name,
      service?.tunnelUrl,
      service?.url,
    ]) {
      const key = identity(value);
      if (key) byIdentity.set(key, description);
    }
  }
  for (const row of document.querySelectorAll("#sickz-checks .health-row")) {
    const tags = row.querySelector(".health-row-tags");
    if (!tags?.textContent?.includes("Legacy inverse-reachability target")) {
      continue;
    }
    const candidates = [
      row.dataset.serviceKey,
      row.dataset.serviceName,
      row.dataset.serviceUrl,
      row.querySelector(".sickz-target-link")?.href,
    ];
    const description = candidates
      .map((value) => byIdentity.get(identity(value)))
      .find(Boolean);
    if (description) tags.textContent = description;
  }
}

function familyMessage(family, successText, permission) {
  if (!family) return "inventory not confirmed";
  if (family.success === false || family.state === "error") {
    const error = family.error ? ` · ${family.error}` : "";
    return `inventory unavailable${error} · verify ${permission}`;
  }
  const count = Number(family.total_count ?? family.result_count);
  return Number.isFinite(count) ? successText(count) : "inventory not confirmed";
}

function updateProviderItem(section, label, text, warn = false) {
  const item = [...section.querySelectorAll(".service-provider-item")].find(
    (candidate) =>
      normalize(candidate.querySelector("strong")?.textContent) === normalize(label),
  );
  const detail = item?.querySelector("div > span");
  if (!item || !detail) return;
  if (detail.textContent !== text) detail.textContent = text;
  item.title = text;
  item.classList.toggle("service-provider-item--warn", warn);
}

function reconcileCloudflareDrawer() {
  const selected = document.querySelector(
    '.health-row[data-service-key="cloudflare"][data-detail-selected="true"]',
  );
  const section = document.querySelector("[data-provider-diagnostics-section]");
  if (!selected || !section || !latestSnapshot) return;
  const control = latestSnapshot?.homelab?.cloudflare?.control_plane || {};
  const apps = control.access_applications;
  const policies = control.access_reusable_policies;
  const tokens = control.access_service_tokens;
  updateProviderItem(
    section,
    "Access applications",
    familyMessage(
      apps,
      (count) => `${count} application(s) visible`,
      "Access Apps and Policies Read",
    ),
    apps?.success === false,
  );
  updateProviderItem(
    section,
    "Reusable policies",
    familyMessage(
      policies,
      (count) => `${count} policy object(s) visible`,
      "Access Apps and Policies Read",
    ),
    policies?.success === false,
  );
  updateProviderItem(
    section,
    "Service Tokens",
    familyMessage(
      tokens,
      (count) => `${count} Service Token(s) visible`,
      "Access Service Tokens Read",
    ),
    tokens?.success === false,
  );
}

function reconcileLocalPfSense() {
  if (latestSnapshot?.runtime?.runtime_mode !== "local") return;
  const platform = latestSnapshot?.healthz?.checks?.pfsense || {};
  if (platform.reachable !== true) return;
  const row = document.querySelector("#sickz-pfsense-wrap .sickz-pfsense-row");
  const detail = row?.querySelector(".health-row-detail");
  const led = row?.querySelector(".health-led");
  if (!row || !detail || !led) return;
  if (!normalize(detail.textContent).includes("not probed")) return;
  detail.textContent =
    "External exposure-policy probe skipped from the trusted workstation/LAN vantage point; pfSense REST/API reachability is independently confirmed from this runtime.";
  led.className = "health-led health-led--blue";
  led.title =
    "Partial evidence: pfSense API reachable; external exposure policy intentionally not probed from LAN";
}

function clearLegacySickzHint() {
  const hint = document.getElementById("sickz-lan-hint");
  if (!hint) return;
  if (normalize(hint.textContent).startsWith("lan skip")) {
    hint.hidden = true;
    hint.textContent = "";
  }
}

function ensureRuntimeNotices() {
  const host = document.getElementById("sickz-lan-hint")?.parentElement;
  if (!host || !latestSnapshot) return;
  let notices = document.getElementById("runtime-feature-notices");
  if (!notices) {
    notices = document.createElement("div");
    notices.id = "runtime-feature-notices";
    notices.className = "runtime-feature-notices";
    host.appendChild(notices);
  }
  const messages = [];
  if (latestSnapshot?.homelab?.internal_probes_enabled === false) {
    messages.push(
      "HOMELAB_INTERNAL_PROBES_ENABLED=false — LAN/TCP fan-out is disabled; internal reachability remains unknown and is excluded from probe coverage.",
    );
  }
  if (runtimeDiagnosticsState === false) {
    messages.push(
      "RUNTIME_DIAGNOSTICS_ENABLED=false — local /v1/runtime metadata, logs and error-buffer endpoints are not registered.",
    );
  }
  const signature = messages.join("\n");
  if (notices.dataset.signature === signature) return;
  notices.dataset.signature = signature;
  notices.replaceChildren();
  for (const message of messages) {
    const note = document.createElement("p");
    note.textContent = message;
    notices.appendChild(note);
  }
  notices.hidden = messages.length === 0;
}

async function detectRuntimeDiagnostics() {
  if (
    runtimeDiagnosticsState != null ||
    latestSnapshot?.runtime?.runtime_mode !== "local"
  ) {
    return;
  }
  const response = await fetch("/v1/runtime/metadata", {
    headers: { Accept: "application/json" },
  }).catch(() => null);
  if (!response) return;
  runtimeDiagnosticsState = response.status === 404 ? false : true;
}

function apply() {
  scheduled = false;
  pinTrueNasPlatform();
  decoratePublicDns();
  decorateTrueNasApiStage();
  deduplicateProbeEvidence();
  linkProbePlanes();
  clearLegacySickzHint();
  reconcileCloudflareDrawer();
  reconcileLocalPfSense();
  ensureRuntimeNotices();
  void replaceLegacyExposureLabels();
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(apply);
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  await detectRuntimeDiagnostics();
  schedule();
}

export function installHealthUiOperatorFollowup() {
  document.addEventListener("service-filter-changed", schedule);
  document.addEventListener("health-board-refreshed", refresh);
  document.addEventListener(
    "click",
    (event) => {
      if (
        event.target instanceof Element &&
        event.target.closest(".service-detail-trigger")
      ) {
        window.setTimeout(schedule, 0);
      }
    },
    true,
  );
  refresh();
}
