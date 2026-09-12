import { fetchHealthBoard } from "./api-health-board.js";

let latestSnapshot = null;
let decorateScheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function cardRow(serviceKey) {
  return document.querySelector(
    `.health-row[data-service-key="${CSS.escape(serviceKey)}"]`,
  );
}

function openServiceCard(serviceKey) {
  const row = cardRow(serviceKey);
  if (!row) return;
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.querySelector(".service-detail-trigger")?.click();
}

function serviceLink(label, serviceKey, title) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "truenas-stage-service-link";
  button.dataset.serviceKey = serviceKey;
  button.textContent = label;
  button.title = title;
  button.setAttribute("aria-label", title);
  button.addEventListener("click", () => openServiceCard(serviceKey));
  return button;
}

function stageByLabel(label) {
  const wanted = normalize(label);
  return [
    ...document.querySelectorAll("#truenas-pipeline .truenas-stage"),
  ].find(
    (stage) =>
      normalize(stage.querySelector(".truenas-stage-label")?.textContent) ===
      wanted,
  );
}

function decoratePublicDnsStage() {
  const stage = stageByLabel("DNS") || stageByLabel("DNS resolution");
  if (!stage || stage.dataset.platformDecorated === "public-dns") return;
  stage.dataset.platformDecorated = "public-dns";
  const icon = stage.querySelector(".truenas-stage-icon");
  const label = stage.querySelector(".truenas-stage-label");
  const detail = stage.querySelector(".truenas-stage-detail");
  if (icon) icon.textContent = "🌐";
  if (label) label.textContent = "Public DNS";
  if (detail) {
    const base = String(detail.textContent || "").trim();
    detail.textContent = [
      base,
      "runtime hostname resolution; DNS provider attribution is not inferred",
    ]
      .filter(Boolean)
      .join(" · ");
  }
}

function securityIcon(filter) {
  const identity = normalize(`${filter?.id || ""} ${filter?.label || ""}`);
  if (identity.includes("pfblocker")) return "🚫";
  if (identity.includes("snort")) return "🛡️";
  if (identity.includes("crowdsec")) return "👥";
  if (identity.includes("firewall") || identity.includes("pfsense/pf"))
    return "🧱";
  return "🛡️";
}

function securityTone(filter) {
  const state = normalize(filter?.state);
  if (["running", "clear"].includes(state)) return "ok";
  if (state === "blocked") return "fail";
  if (state === "stopped") return "warn";
  return "neutral";
}

function securityBadges(filters) {
  const host = document.createElement("div");
  host.className = "truenas-stage-security-badges";
  for (const filter of filters) {
    const badge = document.createElement("span");
    badge.className = `truenas-stage-security-badge truenas-stage-security-badge--${securityTone(filter)}`;
    const label = String(filter?.label || filter?.id || "security control");
    const state = String(filter?.state || "unknown");
    const detail = String(filter?.detail || "").trim();
    badge.textContent = `${securityIcon(filter)} ${label}`;
    badge.title = `${label} · ${state}${detail ? ` · ${detail}` : ""}`;
    badge.setAttribute("aria-label", badge.title);
    host.appendChild(badge);
  }
  return host;
}

function securityFiltersSignature(filters) {
  return JSON.stringify(
    filters.map((filter) => [
      filter?.id,
      filter?.label,
      filter?.state,
      filter?.detail,
    ]),
  );
}

function decoratePfSenseStage(snapshot) {
  const stage = stageByLabel("pfSense WAN ingress");
  if (!stage) return;
  const label = stage.querySelector(".truenas-stage-label");
  if (label && !label.querySelector(".truenas-stage-service-link")) {
    label.replaceChildren(
      serviceLink(
        "pfSense WAN ingress",
        "pfsense",
        "Open pfSense service diagnostics",
      ),
    );
  }
  const detail = stage.querySelector(".truenas-stage-detail");
  const filters = Array.isArray(
    snapshot?.homelab?.pfsense?.dns?.security_filters,
  )
    ? snapshot.homelab.pfsense.dns.security_filters
    : [];
  const signature = securityFiltersSignature(filters);
  if (
    detail &&
    filters.length > 0 &&
    detail.dataset.securitySignature !== signature
  ) {
    detail.replaceChildren(securityBadges(filters));
    detail.dataset.securitySignature = signature;
  }
  stage.dataset.platformDecorated = "pfsense";
}

function dnsStageState(dns) {
  const policy = normalize(dns?.policy_state);
  if (policy === "ok") return "ok";
  if (policy === "fail") return "fail";
  if (policy === "warn") return "warn";
  return "blocked";
}

function dnsStageDetail(dns) {
  const resolver = dns?.resolver || {};
  const upstream = dns?.upstream || {};
  const parts = [];
  if (resolver.running === true) parts.push("Unbound running");
  else if (resolver.running === false) parts.push("Unbound stopped");
  else parts.push("Unbound state unconfirmed");
  const count = Number(upstream.count);
  if (Number.isFinite(count)) parts.push(`${count} configured upstream(s)`);
  if (upstream.independent_from_truenas === true) {
    parts.push("TrueNAS-independent resolver path confirmed");
  } else if (upstream.truenas_only === true) {
    parts.push("upstream path depends on TrueNAS-hosted DNS");
  }
  if (dns?.reason) parts.push(String(dns.reason));
  return parts.join(" · ");
}

function createConnector(broken = false) {
  const item = document.createElement("div");
  item.className = `truenas-connector${broken ? " truenas-connector--broken" : ""}`;
  item.setAttribute("aria-hidden", "true");
  item.dataset.platformSynthetic = "pfsense-dns-connector";
  return item;
}

function createPfSenseDnsStage(dns) {
  const state = dnsStageState(dns);
  const detailText = dnsStageDetail(dns);
  const stage = document.createElement("div");
  stage.className = `truenas-stage truenas-stage--${state}`;
  stage.dataset.platformSynthetic = "pfsense-dns";
  stage.title = detailText;

  const icon = document.createElement("span");
  icon.className = "truenas-stage-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "🌐";

  const label = document.createElement("span");
  label.className = "truenas-stage-label";
  label.appendChild(
    serviceLink(
      "pfSense DNS / Unbound",
      "pfsense",
      "Open pfSense DNS and security diagnostics",
    ),
  );

  const time = document.createElement("span");
  time.className = "truenas-stage-time";
  time.textContent = "observed posture";

  const detail = document.createElement("span");
  detail.className = "truenas-stage-detail";
  detail.textContent = detailText;
  stage.append(icon, label, time, detail);
  return stage;
}

function updatePfSenseDnsStage(stage, connector, dns) {
  const state = dnsStageState(dns);
  const detailText = dnsStageDetail(dns);
  const className = `truenas-stage truenas-stage--${state}`;
  if (stage.className !== className) stage.className = className;
  if (stage.title !== detailText) stage.title = detailText;
  const detail = stage.querySelector(".truenas-stage-detail");
  if (detail && detail.textContent !== detailText)
    detail.textContent = detailText;
  const broken = state === "fail";
  const connectorClass = `truenas-connector${broken ? " truenas-connector--broken" : ""}`;
  if (connector && connector.className !== connectorClass) {
    connector.className = connectorClass;
  }
}

function insertPfSenseDnsStage(snapshot) {
  const pipeline = document.getElementById("truenas-pipeline");
  const pfsense = stageByLabel("pfSense WAN ingress");
  const dns = snapshot?.homelab?.pfsense?.dns;
  if (!pipeline || !pfsense || !dns) return;

  let stage = pipeline.querySelector('[data-platform-synthetic="pfsense-dns"]');
  let syntheticConnector = pipeline.querySelector(
    '[data-platform-synthetic="pfsense-dns-connector"]',
  );
  if (!stage) {
    stage = createPfSenseDnsStage(dns);
    syntheticConnector = createConnector(dnsStageState(dns) === "fail");
    pfsense.insertAdjacentElement("afterend", syntheticConnector);
    syntheticConnector.insertAdjacentElement("afterend", stage);
  }
  updatePfSenseDnsStage(stage, syntheticConnector, dns);
}

function hideUnprovenIngressBanner(snapshot) {
  const banner = document.getElementById("truenas-ingress-block");
  if (!banner) return;
  const state = String(
    snapshot?.homelab?.pfsense?.dns?.ingress_block?.state || "unknown",
  );
  if (state === "blocked") return;
  if (banner.hidden && banner.childNodes.length === 0) return;
  banner.hidden = true;
  banner.open = false;
  banner.replaceChildren();
}

function removeImplementationNote() {
  const node = document.getElementById("truenas-platform-error");
  if (!node || node.hidden) return;
  const implementationNote =
    "TrueNAS flow rendered from bounded /api/homelab/probes first; aggregate health enriches the view when available.";
  const text = String(node.textContent || "");
  if (!text.includes(implementationNote)) return;
  const parts = text
    .split(" · ")
    .map((part) => part.trim())
    .filter((part) => part && part !== implementationNote);
  node.textContent = parts.join(" · ");
  if (parts.length === 0) node.hidden = true;
}

function decorateFlow(snapshot) {
  decoratePublicDnsStage();
  decoratePfSenseStage(snapshot);
  insertPfSenseDnsStage(snapshot);
  hideUnprovenIngressBanner(snapshot);
  removeImplementationNote();
}

function scheduleDecorate(snapshot = latestSnapshot) {
  if (snapshot) latestSnapshot = snapshot;
  if (decorateScheduled) return;
  decorateScheduled = true;
  window.requestAnimationFrame(() => {
    decorateScheduled = false;
    if (latestSnapshot) decorateFlow(latestSnapshot);
  });
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  scheduleDecorate();
}

export function installPlatformFlowUi() {
  const pipeline = document.getElementById("truenas-pipeline");
  if (pipeline) {
    new MutationObserver(() => scheduleDecorate()).observe(pipeline, {
      childList: true,
      subtree: true,
    });
  }
  const ingress = document.getElementById("truenas-platform");
  if (ingress) {
    new MutationObserver(() => scheduleDecorate()).observe(ingress, {
      childList: true,
      subtree: true,
    });
  }
  document.addEventListener("health-board-refreshed", refresh);
  refresh();
}
