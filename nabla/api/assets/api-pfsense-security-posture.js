import { fetchHealthBoard } from "./api-health-board.js";

const HISTORY_LIMIT = 50;

let latestSnapshot = null;
let scheduled = false;
let historyOpen = false;
const postureHistory = [];

function stateClass(state) {
  if (
    state === "running" ||
    state === "clear" ||
    state === "ok" ||
    state === "in_path" ||
    state === "observed"
  ) {
    return "ok";
  }
  if (state === "blocked" || state === "stopped" || state === "fail") {
    return "fail";
  }
  if (state === "warn") return "warn";
  return "unknown";
}

function stateIcon(state) {
  const tone = stateClass(state);
  if (tone === "ok") return "●";
  if (tone === "fail") return "💀";
  if (tone === "warn") return "◐";
  return "?";
}

function displayState(state) {
  if (state === "in_path") return "in path";
  if (state === "not_observed") return "not observed";
  return state.replaceAll("_", " ");
}

function stateMeaning(filter, posture) {
  const state = filter.state;
  if (filter.id === "firewall" && state === "in_path") {
    return posture.pathMode === "direct_lan"
      ? "pfSense/PF is present on the observed security/control path. This is path evidence, not a block or failure; the current direct-LAN TrueNAS probe can bypass that WAN firewall path."
      : "pfSense/PF is present on the observed ingress/security path. This is expected path evidence, not a block or degraded state."
  }
  if (state === "running") {
    return `${filter.label} is reported running by the read-only pfSense service-state observation.`;
  }
  if (state === "clear") {
    return `${filter.label} telemetry is clear for the observed request/source; this does not prove the service is running unless runtime state is also observed.`;
  }
  if (state === "blocked") {
    return `${filter.label} has explicit block evidence for the observed path/source.`;
  }
  if (state === "stopped") {
    return `${filter.label} is explicitly reported stopped.`;
  }
  if (state === "unknown" || state === "not_observed") {
    return `${filter.label} state is not confirmed by the current read-only observation.`;
  }
  return `${filter.label}: ${displayState(state)}.`;
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

function historyLabel(posture) {
  const summary = posture.filters
    .map((filter) => `${filter.label}=${displayState(filter.state)}`)
    .join(" · ");
  return summary || `pfSense=${displayState(posture.policyState)}`;
}

function recordPosture(snapshot) {
  const posture = postureFromSnapshot(snapshot);
  const previous = postureHistory[0];
  if (
    previous?.observedAt === posture.observedAt &&
    historyLabel(previous) === historyLabel(posture)
  ) {
    return;
  }
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
    chip.textContent = `${stateIcon(state)} ${filter.label} ${displayState(state)}`;
    chip.title = stateMeaning(filter, posture);
    chip.setAttribute("aria-label", stateMeaning(filter, posture));
    chips.appendChild(chip);
  }

  if (posture.filters.length === 0) {
    const chip = document.createElement("span");
    chip.className = `pfsense-security-posture-chip pfsense-security-posture-chip--${stateClass(posture.policyState)}`;
    chip.textContent = `${stateIcon(posture.policyState)} pfSense ${displayState(posture.policyState)}`;
    chip.title = "pfSense policy state from the latest read-only observation.";
    chips.appendChild(chip);
  }
  container.appendChild(chips);
}

function appendHistory(container) {
  if (postureHistory.length === 0) return;
  const details = document.createElement("details");
  details.className = "pfsense-security-posture-history";
  details.open = historyOpen;
  details.addEventListener("toggle", () => {
    historyOpen = details.open;
  });
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
  const existingHistory = container.querySelector(
    ".pfsense-security-posture-history",
  );
  if (existingHistory) historyOpen = existingHistory.open;
  container.hidden = false;
  container.dataset.pathMode = posture.pathMode;
  container.replaceChildren();

  const heading = document.createElement("strong");
  heading.textContent = directLan
    ? "pfSense security posture · out-of-band from current LAN probe"
    : "pfSense WAN ingress security posture";
  heading.title = directLan
    ? "The workstation/TrueNAS probe is currently using a direct LAN path. pfSense security state is still useful control-plane evidence, but it is not necessarily inline for that direct IP connection."
    : "Security-control state observed on the pfSense ingress path.";
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
