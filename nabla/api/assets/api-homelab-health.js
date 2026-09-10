import {
  fetchHealthBoard,
  resetHealthBoardRequest,
} from "./api-health-board.js";

const PROBE_UPDATE_EVENT = "homelab-probes:update";
const PROBE_LOADING_EVENT = "homelab-probes:loading";
const PROBE_ERROR_EVENT = "homelab-probes:error";

function dispatchProbeEvent(name, detail) {
  if (typeof window === "undefined" || typeof CustomEvent === "undefined") return;
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

export function resetHomelabHealthRequest() {
  resetHealthBoardRequest();
}

export function fetchHomelabHealth() {
  return fetchHealthBoard().then((snapshot) => snapshot.homelab);
}

export function fetchHomelabProbeMatrix({ reason = "auto" } = {}) {
  dispatchProbeEvent(PROBE_LOADING_EVENT, { reason });
  return fetch("/api/homelab/probes", {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(
          `homelab probe matrix request failed: HTTP ${response.status}`,
        );
      }
      const payload = await response.json();
      dispatchProbeEvent(PROBE_UPDATE_EVENT, payload);
      return payload;
    })
    .catch((error) => {
      dispatchProbeEvent(PROBE_ERROR_EVENT, {
        reason,
        message: String(error?.message || error),
      });
      throw error;
    });
}
