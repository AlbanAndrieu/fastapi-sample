import { diagnosticsReadAvailable, resetOwnerSessionStatus } from "./api-owner-session.js";

let healthBoardRequest = null;
let forceNextRefresh = false;

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function fetchUntilReady(attemptsRemaining = 30) {
  if (!(await diagnosticsReadAvailable())) {
    const error = new Error("Detailed diagnostics are unavailable.");
    error.code = "owner_session_required";
    throw error;
  }
  const force = forceNextRefresh;
  forceNextRefresh = false;
  const response = await fetch(
    `/api/health-board${force ? "?refresh=true" : ""}`,
    {
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
  const snapshot = await response.json();
  if (snapshot.state !== "pending") return snapshot;
  if (attemptsRemaining <= 0)
    throw new Error("health snapshot refresh timed out");
  await delay(Math.max(1, Number(snapshot.retry_after_seconds) || 2) * 1000);
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
