import { fetchHealthBoard } from "./api-health-board.js";

const HISTORY_LIMIT = 50;

let latestSnapshot = null;
let scheduled = false;
const postureHistory = [];

function stateClass(state) {
  if (state === "running" || state === "clear" || state === "ok") return "ok";
  if (state === "blocked" || state === "stopped" || state === "fail") {
    return "fail";
  }
  if (state === "in_path" || state === "observed" || state === "warn") {
    return "warn";
  }
  return "unknown";
}

function stateIcon(state) {
  const tone = stateClass(state);
  if (tone === "ok") return "●";
  if (tone === "fail") return "💀";
  if (tone === "warn") return "◐";
  return "?";
}

function ensureContainer() {
  let container = document.getElementById("pfsense-security-posture");
  if (container) return container;
  const target = document.getElementById("truenas-platform-target");
  if (!target) return null;
  container = document.createElement("div");
  container.id = "pfsense-security-posture";
  container.className = "pfsense-security-posture";
  target.insertAdjacentElement("afterend", container);
  return container;
}

function postureFromSnapshot(snapshot) {
  const homelab = snapshot?.homelab || {};
  const pathMode = homelab?.truenas?.diagnostics?.path_mode || "unknown";
  const dns = homelab?.pfsense?.dns || {};
  const filters = Array.isArray(dns.security_filters)
    ? dns.security_filters.map((filter) => ({
        id: String(filter?.id || ""),
        label: String(filter?.label || filter?.id || "security filter"),
        state: String(filter?.state || "unknown"),
      }))
    : [];
  return {
    observedAt:
      snapshot?.generated_at || homelab?.checked_at || new Date().toISOString(),
    pathMode,
    policyState: String(dns.policy_state || "unknown"),
    filters,
  };
}

function recordPosture(snapshot) {
  const posture = postureFromSnapshot(snapshot);
  postureHistory.unshift(posture);
  postureHistory.splice(HISTORY_LIMIT);
}

function appendChips(container, posture) {
  const chips = document.createElement("div");
  chips.className = "pfsense-security-posture-chips";
  for (const filter of posture.filters) {
    const chip = document.createElement("span");
    const state = filter.state;
    chip.className = `pfsense-security-posture-chip pfsense-security-posture-chip--${stateClass(state)}`;
    chip.textContent = `${stateIcon(state)} ${filter.label} ${state}`;
    const directLan = posture.pathMode === "direct_lan";
    chip.title = directLan
      ? `${filter.label}: ${state}. Observed through the read-only pfSense control path; this control is not on the current direct-LAN TrueNAS probe path.`
      : `${filter.label}: ${state}. This posture is observed on the pfSense WAN/security path.`;
    chips.appendChild(chip);
  }

  if (posture.filters.length === 0) {
    const chip = document.createElement("span");
    chip.className = `pfsense-security-posture-chip pfsense-security-posture-chip--${stateClass(posture.policyState)}`;
    chip.textContent = `${stateIcon(posture.policyState)} pfSense ${posture.policyState}`;
    chips.appendChild(chip);
  }
  container.appendChild(chips);
}

function historyLabel(posture) {
  const summary = posture.filters
    .map((filter) => `${filter.label}=${filter.state}`)
    .join(" · ");
  return summary || `pfSense=${posture.policyState}`;
}

function appendHistory(container) {
  if (postureHistory.length === 0) return;
  const details = document.createElement("details");
  details.className = "pfsense-security-posture-history";
  const summary = document.createElement("summary");
  summary.textContent = `History · ${postureHistory.length}/${HISTORY_LIMIT} observations`;
  details.appendChild(summary);

  const list = document.createElement("ol");
  for (const posture of postureHistory) {
    const item = document.createElement("li");
    const time = document.createElement("time");
    time.dateTime = posture.observedAt;
    time.textContent = posture.observedAt;
    const text = document.createElement("span");
    text.textContent = historyLabel(posture);
    item.append(time, text);
    list.appendChild(item);
  }
  details.appendChild(list);
  container.appendChild(details);
}

function render() {
  scheduled = false;
  const container = ensureContainer();
  if (!container || !latestSnapshot) return;

  const posture = postureFromSnapshot(latestSnapshot);
  if (posture.filters.length === 0 && posture.policyState === "unknown") {
    container.hidden = true;
    container.replaceChildren();
    return;
  }

  const directLan = posture.pathMode === "direct_lan";
  container.hidden = false;
  container.dataset.pathMode = posture.pathMode;
  container.replaceChildren();

  const heading = document.createElement("strong");
  heading.textContent = directLan
    ? "pfSense security posture · out-of-band from current LAN probe"
    : "pfSense WAN ingress security posture";
  container.appendChild(heading);
  appendChips(container, posture);
  appendHistory(container);
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.setTimeout(() => window.requestAnimationFrame(render), 0);
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  if (latestSnapshot) recordPosture(latestSnapshot);
  schedule();
}

export function installPfsenseSecurityPosture() {
  document.addEventListener("health-board-refreshed", refresh);
  refresh();
}
