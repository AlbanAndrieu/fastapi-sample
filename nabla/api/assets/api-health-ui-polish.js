import { MANDATORY } from "./api-health-core.js";
import { fetchTopology } from "./api-topology-data.js";

const ROW_SELECTOR = ".health-row[data-service-key]";
const REQUIRED_TIER = "Required health check";
const PFSENSE_KEY = "pfsense";

let topologyNodes = [];
let refreshScheduled = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value), window.location.href).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function candidateId(row) {
  const key = String(row?.dataset?.serviceKey || "");
  return key.startsWith("albandrieu_")
    ? key.slice("albandrieu_".length).replaceAll("_", "-")
    : key.replaceAll("_", "-");
}

function topologyNodeFor(row) {
  const id = candidateId(row);
  const name = normalize(row?.dataset?.serviceName);
  const host = hostOf(row?.dataset?.serviceUrl);
  return (
    topologyNodes.find((node) => String(node?.id || "") === id) ||
    topologyNodes.find((node) => normalize(node?.name) === name) ||
    topologyNodes.find((node) => host && hostOf(node?.url) === host) ||
    null
  );
}

function ensureLayout() {
  const filter = document.querySelector(".service-filter--global");
  const board = document.getElementById("health-board");
  if (!filter || !board || board.closest(".service-health-layout")) return;
  const layout = document.createElement("div");
  layout.className = "service-health-layout";
  board.parentElement?.insertBefore(layout, filter);
  layout.append(filter, board);
}

function legendItem(className, label, detail) {
  return `<span class="health-legend-item ${className}" title="${detail}"><i aria-hidden="true"></i><b>${label}</b></span>`;
}

function hoverLabel(label, detail) {
  return `<span class="health-legend-hover" title="${detail}" aria-label="${label}. ${detail}"><b>${label}</b><i aria-hidden="true">ⓘ</i></span>`;
}

function enrichLegend() {
  document.getElementById("health-tier-legend")?.remove();
  const details = document.querySelector(".service-filter-legend-details");
  const legend = document.getElementById("service-probe-legend");
  if (!details || !legend) return;

  if (details.dataset.operatorLegendInitialized !== "true") {
    details.dataset.operatorLegendInitialized = "true";
    details.open = false;
  }
  const summary = details.querySelector(":scope > summary");
  if (summary) summary.textContent = "Legend · health, tiers & probe evidence";
  if (legend.dataset.healthLegendComplete === "true") return;

  legend.dataset.healthLegendComplete = "true";
  legend.innerHTML = [
    '<strong class="health-legend-title">Hover labels for details</strong>',
    '<div class="health-legend-section"><b>Evidence colors</b>',
    legendItem(
      "health-legend--green",
      "Green",
      "Confirmed healthy / operational evidence.",
    ),
    legendItem(
      "health-legend--amber",
      "Amber",
      "Warning, incomplete evidence or at-risk state; not necessarily downtime.",
    ),
    legendItem("health-legend--red", "Red", "Confirmed failure / down evidence."),
    legendItem(
      "health-legend--gray",
      "Gray",
      "Unknown, unobserved or not confirmed from this observer.",
    ),
    "</div>",
    '<div class="health-legend-section"><b>Health tiers</b>',
    hoverLabel(
      "Required infra",
      "Availability requirement for the albandrieu.com homelab/domain view; confirmed failures may affect the overall summary.",
    ),
    hoverLabel(
      "Required check",
      "Required dependency for the deep application health contract; confirmed failure is blocking.",
    ),
    hoverLabel(
      "Optional check",
      "Non-blocking integration/support probe; unavailable evidence is warning/unknown, not downtime.",
    ),
    "</div>",
    '<div class="health-legend-section"><b>Card probes</b>',
    hoverLabel("🌐 HTTP", "Latest public HTTP response evidence, such as HTTP 200/302."),
    hoverLabel("🔒 TLS", "TLS certificate validation for the public HTTPS endpoint."),
    hoverLabel("🔌 TCP", "Latest LAN/internal TCP reachability evidence."),
    hoverLabel("⚙️ API", "REST/API control-plane evidence; separate from raw listener reachability."),
    hoverLabel("↔️ WS", "WebSocket/API transport evidence where applicable."),
    hoverLabel("☁️ Tunnel", "Cloudflare Tunnel route/connectivity evidence; it does not authorize users."),
    hoverLabel("🛡️ Access", "Cloudflare Access/policy authorization evidence."),
    hoverLabel("🔑 Token", "Cloudflare Access Service Token machine-identity evidence."),
    hoverLabel("📈 Metrics", "Prometheus/runtime metrics evidence when configured."),
    hoverLabel("Public", "Externally published service endpoint; the label links to that endpoint."),
    hoverLabel("LAN", "Internal IP/port endpoint observed from the homelab/workstation runtime."),
    "</div>",
    '<div class="health-legend-section"><b>Card metadata</b>',
    hoverLabel("critical/high", "Blast-radius criticality from the topology, not a live health result."),
    hoverLabel("downstream", "Number of declared services that depend on this service."),
    hoverLabel("age", "Time since the latest probe observation used by this Card."),
    hoverLabel("latency", "Duration of the latest sampled probe."),
    hoverLabel("probing", "A refresh is currently due/running; this indicator does not change health by itself."),
    "</div>",
  ].join("");
}

function consolidateTelemetry(row) {
  let column = row.querySelector(":scope > .health-row-telemetry");
  if (!column) {
    column = document.createElement("div");
    column.className = "health-row-telemetry";
    row.appendChild(column);
  }
  column.setAttribute("aria-label", "Probe freshness, latency and refresh state");
  column.title =
    "Probe telemetry: freshness/age, latest latency and whether a refresh is currently probing.";

  const badges = [
    ...row.querySelectorAll(
      ".health-meta-badge--probe-age, .health-meta-badge--probe-latency, .health-meta-badge--probing",
    ),
  ];
  for (const badge of badges) {
    if (badge.parentElement !== column) column.appendChild(badge);
    if (badge.classList.contains("health-meta-badge--probing")) {
      const help =
        "Probe refresh is currently due/running. This is activity evidence only and does not degrade the service by itself.";
      badge.title = help;
      badge.setAttribute("aria-label", help);
    }
  }

  for (const legacy of row.querySelectorAll(".health-probe-timing-column")) {
    if (!legacy.children.length) legacy.remove();
  }
  return column;
}

function moveTierNextToName(row) {
  const primary = row.querySelector(".health-row-primary");
  const name = row.querySelector(".health-row-name");
  const note = row.querySelector(".health-meta-note");
  if (!primary || !name || !note) return;
  if (row.dataset.serviceKey === PFSENSE_KEY) note.textContent = REQUIRED_TIER;
  note.classList.add("health-tier-inline");
  if (note.parentElement !== primary || note.previousElementSibling !== name) {
    name.insertAdjacentElement("afterend", note);
  }
}

function ensureDescriptionHelp(row) {
  const node = topologyNodeFor(row);
  const description = String(node?.description || "").trim();
  const name = row.querySelector(".health-row-name");
  if (!name || !description) return;
  row.dataset.serviceDescription = description;
  let help = name.querySelector(".service-description-help");
  if (!help) {
    help = document.createElement("button");
    help.type = "button";
    help.className = "service-description-help";
    help.textContent = "ⓘ";
    name.appendChild(help);
  }
  help.title = description;
  help.setAttribute(
    "aria-label",
    `About ${row.dataset.serviceName || "this service"}: ${description}`,
  );
}

function decorateRows() {
  for (const row of document.querySelectorAll(ROW_SELECTOR)) {
    moveTierNextToName(row);
    ensureDescriptionHelp(row);
    consolidateTelemetry(row);
  }
}

function scheduleRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    ensureLayout();
    enrichLegend();
    decorateRows();
  });
}

function observeHealthBoard() {
  const board = document.getElementById("health-board");
  if (!board) return;
  new MutationObserver(scheduleRefresh).observe(board, {
    childList: true,
    subtree: true,
  });
}

export function installHealthUiPolish() {
  MANDATORY.add(PFSENSE_KEY);
  ensureLayout();
  enrichLegend();
  decorateRows();
  observeHealthBoard();
  document.addEventListener("health-board-refreshed", scheduleRefresh);
  fetchTopology()
    .then((topology) => {
      topologyNodes = Array.isArray(topology?.nodes) ? topology.nodes : [];
      scheduleRefresh();
    })
    .catch(() => {
      topologyNodes = [];
    });
}
