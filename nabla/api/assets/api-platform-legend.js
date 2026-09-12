const PLATFORM_ITEMS = [
  ["🧱", "pfSense / PF path"],
  ["🛡️", "Snort"],
  ["🚫", "pfBlockerNG"],
  ["👥", "CrowdSec"],
  ["🌐", "Public / resolver DNS"],
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
    "Cards = canonical operational state · Flow = path/dependency context · green = confirmed healthy · amber = real attention/degradation · red = failed or proven block · gray = unavailable/unconfirmed or API-dependent control disabled.";
  legend.appendChild(semantics);
}

export function installPlatformLegend() {
  appendPlatformLegend();
  document.addEventListener("health-board-refreshed", appendPlatformLegend);
}
