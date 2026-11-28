// The legacy pfSense, Snort and pfBlockerNG inventory is historical after
// Freebox cutover; do not statically advertise these as active controls.
const PLATFORM_ITEMS = [
  ["🧱", "Network edge · current router evidence"],
  ["👥", "CrowdSec"],
  ["🌐", "Public / resolver DNS"],
  ["🩷", "Retired · historical, not failed"],
];

function appendPlatformLegend() {
  const legend = document.getElementById("service-probe-legend");
  if (!legend || legend.dataset.platformLegend === "true") return;
  legend.dataset.platformLegend = "true";

  for (const [icon, label] of PLATFORM_ITEMS) {
    const item = document.createElement("span");
    item.textContent = `${icon} ${label}`;
    legend.appendChild(item);
  }

  const semantics = document.createElement("small");
  semantics.className = "service-probe-legend-model";
  semantics.textContent =
    "Cards = canonical operational state · Flow = path/dependency context · green = confirmed healthy · amber = real attention/degradation · red = failed or proven block · gray = unavailable/unconfirmed or API-dependent control disabled · pink = explicitly retired, not an outage.";
  legend.appendChild(semantics);
}

export function installPlatformLegend() {
  appendPlatformLegend();
  document.addEventListener("health-board-refreshed", appendPlatformLegend);
}
