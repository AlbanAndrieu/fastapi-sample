import { decorateCloudflareProbeStatuses } from "./api-cloudflare-probe.js";
import {
  decorateCloudflareTunnelStatuses,
  markHealthBoardsPending,
} from "./api-cloudflare-status.js";
import { decorateDnsStatuses } from "./api-dns-status.js";
import {
  fetchHealthBoard,
  resetHealthBoardRequest,
} from "./api-health-board.js";
import { loadHealth } from "./api-health-core.js";
import { decorateHttpProbeStatuses } from "./api-http-probe-status.js";
import { decorateProbeTelemetry } from "./api-probe-live.js";
import { loadRuntimeTopology } from "./api-runtime.js";
import { installSecurityControlIcons } from "./api-security-control-icons.js";
import { loadSickz } from "./api-sickz.js";
import { loadTrueNas } from "./api-truenas.js";

const HEALTH_BOARD_IDLE_POLL_MS = 10000;
const HEALTH_BOARD_REFRESHING_POLL_MS = 2000;
let automaticRefreshInFlight = false;
let automaticRefreshTimer = null;

function logRefreshClick() {
  fetch("/api/health-board/refresh-event", {
    method: "POST",
    cache: "no-store",
    keepalive: true,
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  }).catch(() => {
    // Probe results stay authoritative even when telemetry logging fails.
  });
}

function technicalDetailsOpen() {
  return (
    document.getElementById("runtime-topology")?.open === true ||
    document.getElementById("truenas-probe-dashboard")?.open === true
  );
}

function announceRefreshComplete(snapshot, { forceRefresh, includeTechnical }) {
  window.requestAnimationFrame(() => {
    document.dispatchEvent(
      new CustomEvent("health-board-refreshed", {
        detail: {
          forceRefresh,
          includeTechnical,
          refreshing: snapshot?.refreshing === true,
        },
      }),
    );
  });
}

function loadHealthBoards({
  forceRefresh = false,
  showPending = true,
  includeTechnical = false,
} = {}) {
  resetHealthBoardRequest({ forceRefresh });
  if (showPending) markHealthBoardsPending();
  loadHealth();
  loadSickz();
  if (includeTechnical) {
    loadRuntimeTopology();
    loadTrueNas();
  }
  return fetchHealthBoard()
    .then((snapshot) => {
      decorateCloudflareTunnelStatuses(
        snapshot.sickz,
        snapshot?.healthz?.checks?.cloudflare,
        snapshot?.homelab?.cloudflare,
      );
      decorateCloudflareProbeStatuses(snapshot.sickz);
      decorateProbeTelemetry(snapshot);
      decorateDnsStatuses(snapshot);
      decorateHttpProbeStatuses(snapshot);
      announceRefreshComplete(snapshot, { forceRefresh, includeTechnical });
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

function installTechnicalDetailRefresh() {
  const runtime = document.getElementById("runtime-topology");
  runtime?.addEventListener("toggle", () => {
    if (runtime.open) loadRuntimeTopology();
  });

  const fanout = document.getElementById("truenas-probe-dashboard");
  fanout?.addEventListener("toggle", () => {
    if (fanout.open) loadTrueNas();
  });
}

function installAutomaticRefresh() {
  scheduleAutomaticRefresh();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden || automaticRefreshInFlight) return;
    scheduleAutomaticRefresh(0);
  });
}

export function installHealthBoardController() {
  document.querySelectorAll(".health-refresh").forEach((button) => {
    button.addEventListener("click", () => {
      logRefreshClick();
      loadHealthBoards({
        forceRefresh: true,
        includeTechnical: technicalDetailsOpen(),
      });
    });
  });

  installSecurityControlIcons();
  installTechnicalDetailRefresh();
  loadHealthBoards({ includeTechnical: true });
  installAutomaticRefresh();
}
