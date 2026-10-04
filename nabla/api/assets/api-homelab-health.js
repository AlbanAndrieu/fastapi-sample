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

function publishAggregateProbeSnapshot(snapshot) {
  const homelab = snapshot?.homelab;
  if (
    homelab &&
    (homelab.probe_summary ||
      Array.isArray(homelab.internal_services) ||
      Array.isArray(homelab.public_probe_results))
  ) {
    dispatchProbeEvent(PROBE_UPDATE_EVENT, {
      ...homelab,
      probe_snapshot_source: "health-board",
    });
  }
  return homelab;
}

export function fetchHomelabHealth() {
  return fetchHealthBoard().then(publishAggregateProbeSnapshot);
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
        const protectedResponse =
          response.status === 401 || response.status === 403;
        const unavailableResponse = response.status === 404;
        const error = new Error(
          protectedResponse
            ? "Raw probe matrix is protected by DIAGNOSTICS_ACCESS_KEY"
            : unavailableResponse
              ? "Raw probe matrix is unavailable on this deployment; aggregate probe health remains available"
              : `homelab probe matrix request failed: HTTP ${response.status}`,
        );
        if (protectedResponse) {
          error.code = "diagnostics_auth_required";
          error.httpStatus = response.status;
        } else if (unavailableResponse) {
          error.code = "probe_matrix_unavailable";
          error.httpStatus = 404;
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
