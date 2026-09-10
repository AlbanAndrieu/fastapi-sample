import {
  decorateCloudflareTunnelStatuses,
  markHealthBoardsPending,
} from "./api-cloudflare-status.js";
import {
  fetchHealthBoard,
  resetHealthBoardRequest,
} from "./api-health-board.js";
import { loadHealth } from "./api-health-core.js";
import {
  decorateProbeTelemetry,
  markVisibleProbeRowsPending,
  startProbeAgeTicker,
} from "./api-probe-live.js";
import { loadRuntimeTopology } from "./api-runtime.js";
import { installServiceFilter } from "./api-service-groups.js";
import { loadSickz } from "./api-sickz.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";
import { loadTrueNas } from "./api-truenas.js";

const HEALTH_BOARD_POLL_MS = 5000;
let automaticRefreshInFlight = false;

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

function loadHealthBoards({ forceRefresh = false, showPending = true } = {}) {
  resetHealthBoardRequest({ forceRefresh });
  if (showPending) {
    markHealthBoardsPending();
    if (forceRefresh) markVisibleProbeRowsPending();
  }
  loadRuntimeTopology();
  loadTrueNas();
  loadHealth();
  loadSickz();
  return fetchHealthBoard()
    .then((snapshot) => {
      decorateCloudflareTunnelStatuses(snapshot.sickz);
      decorateProbeTelemetry(snapshot);
      return snapshot;
    })
    .catch(() => null);
}

function installAutomaticRefresh() {
  window.setInterval(() => {
    if (document.hidden || automaticRefreshInFlight) return;
    automaticRefreshInFlight = true;
    loadHealthBoards({ showPending: false }).finally(() => {
      automaticRefreshInFlight = false;
    });
  }, HEALTH_BOARD_POLL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden || automaticRefreshInFlight) return;
    automaticRefreshInFlight = true;
    loadHealthBoards({ showPending: false }).finally(() => {
      automaticRefreshInFlight = false;
    });
  });
}

document.querySelectorAll(".health-refresh").forEach((button) => {
  button.addEventListener("click", () => {
    logRefreshClick();
    loadHealthBoards({ forceRefresh: true });
  });
});

installPfsensePortLabels();
installServiceFilter();
startProbeAgeTicker();
loadHealthBoards();
installAutomaticRefresh();
