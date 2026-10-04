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

export function fetchHomelabProbeMatrix({
  reason = "auto",
  diagnosticsKey = "",
} = {}) {
  dispatchProbeEvent(PROBE_LOADING_EVENT, { reason });
  const headers = { Accept: "application/json", "Cache-Control": "no-cache" };
  if (diagnosticsKey) headers["X-Diagnostics-Key"] = diagnosticsKey;
  return fetch("/api/homelab/probes", {
    cache: "no-store",
    headers,
  })
    .then(async (response) => {
      if (!response.ok) {
        const error = new Error(
          response.status === 401
            ? "Probe matrix is protected by DIAGNOSTICS_ACCESS_KEY"
            : `homelab probe matrix request failed: HTTP ${response.status}`,
        );
        if (response.status === 401) {
          error.code = "diagnostics_auth_required";
          error.httpStatus = 401;
        }
        throw error;
      }
      const payload = await response.json();
      dispatchProbeEvent(PROBE_UPDATE_EVENT, payload);
      return payload;
    })
    .catch((error) => {
      dispatchProbeEvent(PROBE_ERROR_EVENT, {
        reason,
        message: String(error?.message || error),
        code: error?.code || null,
        httpStatus: error?.httpStatus || null,
      });
      throw error;
    });
}
