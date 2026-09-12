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
  return `<span class="health-legend-item ${className}"><i aria-hidden="true"></i><b>${label}</b><small>${detail}</small></span>`;
}

function enrichLegend() {
  document.getElementById("health-tier-legend")?.remove();
  const details = document.querySelector(".service-filter-legend-details");
  const legend = document.getElementById("service-probe-legend");
  if (!details || !legend) return;

  details.open = true;
  const summary = details.querySelector(":scope > summary");
  if (summary) summary.textContent = "Legend · health, tiers & probe evidence";
  if (legend.dataset.healthLegendComplete === "true") return;

  legend.dataset.healthLegendComplete = "true";
  legend.innerHTML = [
    '<strong class="health-legend-title">How to read this screen</strong>',
    '<div class="health-legend-section"><b>Evidence colors</b>',
    legendItem(
      "health-legend--green",
      "Green",
      "confirmed healthy / operational",
    ),
    legendItem(
      "health-legend--amber",
      "Amber",
      "warning, incomplete evidence or at risk",
    ),
    legendItem("health-legend--red", "Red", "confirmed failure / down"),
    legendItem(
      "health-legend--gray",
      "Gray",
      "unknown, unobserved or not confirmed",
    ),
    "</div>",
    '<div class="health-legend-section"><b>Health tiers</b>',
    "<span><b>Required infra (albandrieu.com)</b> — availability requirement for the homelab/domain view; confirmed failures may affect the overall summary.</span>",
    "<span><b>Required health check</b> — required dependency for the deep application health contract; confirmed failure is blocking.</span>",
    "<span><b>Optional health check</b> — non-blocking integration/support probe; timeout or unavailable evidence is warning/unknown, not downtime.</span>",
    "</div>",
    '<div class="health-legend-section"><b>Probe evidence</b><span>🌐 HTTP</span><span>🔒 TLS certificate</span><span>🔌 TCP</span><span>⚙️ REST API</span><span>↔️ WebSocket</span><span>☁️ Cloudflare Tunnel</span><span>🛡️ Access / policy</span><span>🔑 Service Token</span><span>📈 Prometheus / metrics</span></div>',
    '<div class="health-legend-section"><b>Card metadata</b><span><b>critical/high</b> = blast-radius criticality</span><span><b>downstream</b> = declared dependents</span><span><b>probing</b> = refresh currently due/running; it does not change status by itself</span></div>',
  ].join("");
}

function ensureTimingColumn(row) {
  const main = row.querySelector(".health-row-main");
  if (!main) return null;
  let column = main.querySelector(":scope > .health-probe-timing-column");
  if (!column) {
    column = document.createElement("div");
    column.className = "health-probe-timing-column";
    column.setAttribute("aria-label", "Probe timing");
    main.appendChild(column);
  }
  const age = row.querySelector(".health-meta-badge--probe-age");
  const probing = row.querySelector(".health-meta-badge--probing");
  if (age && age.parentElement !== column) column.appendChild(age);
  if (probing && probing.parentElement !== column) column.appendChild(probing);
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
    ensureTimingColumn(row);
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
