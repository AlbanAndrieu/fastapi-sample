import {
  decorateCloudflareTunnelStatuses,
  markHealthBoardsPending,
} from "./api-cloudflare-status.js";
import {
  fetchHealthBoard,
  resetHealthBoardRequest,
} from "./api-health-board.js";
import { loadHealth } from "./api-health-core.js";
import { installServiceFilter } from "./api-service-groups.js";
import { loadSickz } from "./api-sickz.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";
import { loadTrueNas } from "./api-truenas.js";

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

function loadHealthBoards({ forceRefresh = false } = {}) {
  resetHealthBoardRequest({ forceRefresh });
  markHealthBoardsPending();
  const healthRequest = loadHealth();
  loadSickz();
  fetchHealthBoard()
    .then((snapshot) => decorateCloudflareTunnelStatuses(snapshot.sickz))
    .catch(() => {});
  Promise.resolve(healthRequest).finally(() => loadTrueNas());
}

document.querySelectorAll(".health-refresh").forEach((button) => {
  button.addEventListener("click", () => {
    logRefreshClick();
    loadHealthBoards({ forceRefresh: true });
  });
});

installPfsensePortLabels();
installServiceFilter();
loadHealthBoards();
