import { fetchHealthBoard } from "./api-health-board.js";

let latestSnapshot = null;
let scheduled = false;

function stateClass(state) {
  if (state === "running" || state === "clear" || state === "ok") return "ok";
  if (state === "blocked" || state === "stopped" || state === "fail") return "fail";
  if (state === "in_path" || state === "observed" || state === "warn") return "warn";
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

function render() {
  scheduled = false;
  const container = ensureContainer();
  if (!container || !latestSnapshot) return;

  const homelab = latestSnapshot.homelab || {};
  const pathMode = homelab?.truenas?.diagnostics?.path_mode || "unknown";
  const dns = homelab?.pfsense?.dns || {};
  const filters = Array.isArray(dns.security_filters) ? dns.security_filters : [];
  const directLan = pathMode === "direct_lan";

  if (filters.length === 0 && !dns.policy_state) {
    container.hidden = true;
    container.replaceChildren();
    return;
  }

  container.hidden = false;
  container.dataset.pathMode = pathMode;
  const heading = document.createElement("strong");
  heading.textContent = directLan
    ? "pfSense security posture · out-of-band from current LAN probe"
    : "pfSense WAN ingress security posture";
  container.appendChild(heading);

  const chips = document.createElement("div");
  chips.className = "pfsense-security-posture-chips";
  for (const filter of filters) {
    const chip = document.createElement("span");
    const state = String(filter?.state || "unknown");
    chip.className = `pfsense-security-posture-chip pfsense-security-posture-chip--${stateClass(state)}`;
    const label = filter?.label || filter?.id || "security filter";
    chip.textContent = `${stateIcon(state)} ${label} ${state}`;
    chip.title = directLan
      ? `${label}: ${state}. Observed through the read-only pfSense control path; this control is not on the current direct-LAN TrueNAS probe path.`
      : `${label}: ${state}. This posture is observed on the pfSense WAN/security path.`;
    chips.appendChild(chip);
  }

  if (filters.length === 0) {
    const chip = document.createElement("span");
    chip.className = `pfsense-security-posture-chip pfsense-security-posture-chip--${stateClass(dns.policy_state)}`;
    chip.textContent = `${stateIcon(dns.policy_state)} pfSense ${dns.policy_state || "unknown"}`;
    chips.appendChild(chip);
  }
  container.appendChild(chips);
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  window.setTimeout(() => window.requestAnimationFrame(render), 0);
}

async function refresh() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  schedule();
}

export function installPfsenseSecurityPosture() {
  document.addEventListener("health-board-refreshed", refresh);
  refresh();
}
