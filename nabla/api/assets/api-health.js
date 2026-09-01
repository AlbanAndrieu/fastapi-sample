import { loadHealth } from "./api-health-core.js";
import { resetHomelabHealthRequest } from "./api-homelab-health.js";
import { loadSickz } from "./api-sickz.js";
import { loadTrueNas } from "./api-truenas.js";
import { installServiceFilter } from "./api-service-groups.js";
import {
  decorateCloudflareTunnelStatuses,
  markHealthBoardsPending,
} from "./api-cloudflare-status.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";

function logRefreshClick() {
  fetch("/api/health-board/refresh-event", {
    method: "POST",
    cache: "no-store",
    keepalive: true,
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  }).catch(() => {
    // The health probes themselves remain authoritative even if telemetry logging fails.
  });
}

function loadHealthBoards() {
  resetHomelabHealthRequest();
  markHealthBoardsPending();
  const healthRequest = loadHealth();
  loadSickz();
  decorateCloudflareTunnelStatuses();
  Promise.resolve(healthRequest).finally(() => loadTrueNas());
}

document.querySelectorAll(".health-refresh").forEach((button) => {
  button.addEventListener("click", () => {
    logRefreshClick();
    loadHealthBoards();
  });
});

installPfsensePortLabels();
installServiceFilter();
loadHealthBoards();
