import { withRequestDeadline } from "./api-request-deadline.js";
import {
  diagnosticsReadAvailable,
  ownerSessionAvailable,
  resetOwnerSessionStatus,
} from "./api-owner-session.js";

let healthBoardRequest = null;
let forceNextRefresh = false;

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

// The server already refreshes probes in the background (up to 40 seconds).
// The browser must not wait for that refresh to finish to remain usable.
async function fetchUntilReady(attemptsRemaining = 1) {
  if (!(await diagnosticsReadAvailable())) {
    const error = new Error("Detailed diagnostics are unavailable.");
    error.code = "owner_session_required";
    throw error;
  }
  // A read-only page may reload an existing snapshot, not force probes.
  const force = forceNextRefresh && (await ownerSessionAvailable());
  forceNextRefresh = false;
  const snapshot = await withRequestDeadline(async (signal) => {
    const response = await fetch(
      `/api/health-board${force ? "?refresh=true" : ""}`,
      {
        signal,
        cache: "no-store",
        headers: { Accept: "application/json", "Cache-Control": "no-cache" },
      },
    );
    if (response.status === 401 || response.status === 403) {
      resetOwnerSessionStatus();
      const error = new Error("Detailed diagnostics access unavailable.");
      error.code = "owner_session_required";
      throw error;
    }
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }, 6000);
  if (snapshot.state !== "pending") return snapshot;
  if (attemptsRemaining <= 0)
    throw new Error("health snapshot refresh timed out");
  // Never accept unbounded retry_after_seconds supplied by the server.
  await delay(Math.min(2, Math.max(1, Number(snapshot.retry_after_seconds) || 2)) * 1000);
  return fetchUntilReady(attemptsRemaining - 1);
}

export function resetHealthBoardRequest({ forceRefresh = false } = {}) {
  healthBoardRequest = null;
  forceNextRefresh = forceRefresh;
}

export function fetchHealthBoard() {
  if (!healthBoardRequest) {
    healthBoardRequest = fetchUntilReady().catch((error) => {
      healthBoardRequest = null;
      throw error;
    });
  }
  return healthBoardRequest;
}
