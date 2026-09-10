import {
  decorateCloudflareTunnelStatuses,
  markHealthBoardsPending,
} from "./api-cloudflare-status.js";
import {
  fetchHealthBoard,
  resetHealthBoardRequest,
} from "./api-health-board.js";
import { loadHealth } from "./api-health-core.js";
import { installProbeFanoutDashboard } from "./api-probe-fanout-dashboard.js";
import {
  decorateProbeTelemetry,
  startProbeAgeTicker,
} from "./api-probe-live.js";
import { loadRuntimeTopology } from "./api-runtime.js";
import { installServiceFilter } from "./api-service-groups.js";
import { loadSickz } from "./api-sickz.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";
import { loadTrueNas } from "./api-truenas.js";

const HEALTH_BOARD_IDLE_POLL_MS = 5000;
const HEALTH_BOARD_REFRESHING_POLL_MS = 1000;
let automaticRefreshInFlight = false;
let automaticRefreshTimer = null;

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
  if (showPending) markHealthBoardsPending();
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

function scheduleAutomaticRefresh(delayMs = HEALTH_BOARD_IDLE_POLL_MS) {
  if (automaticRefreshTimer) window.clearTimeout(automaticRefreshTimer);
  automaticRefreshTimer = window.setTimeout(async () => {
    if (document.hidden || automaticRefreshInFlight) {
      scheduleAutomaticRefresh();
      return;
    }
    automaticRefreshInFlight = true;
    const snapshot = await loadHealthBoards({ showPending: false });
    automaticRefreshInFlight = false;
    scheduleAutomaticRefresh(
      snapshot?.refreshing === true
        ? HEALTH_BOARD_REFRESHING_POLL_MS
        : HEALTH_BOARD_IDLE_POLL_MS,
    );
  }, delayMs);
}

function installAutomaticRefresh() {
  scheduleAutomaticRefresh();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden || automaticRefreshInFlight) return;
    scheduleAutomaticRefresh(0);
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
installProbeFanoutDashboard();
startProbeAgeTicker();
loadHealthBoards();
installAutomaticRefresh();
