import {
  fetchHealthBoard,
  resetHealthBoardRequest,
} from "./api-health-board.js";

export function resetHomelabHealthRequest() {
  resetHealthBoardRequest();
}

export function fetchHomelabHealth() {
  return fetchHealthBoard().then((snapshot) => snapshot.homelab);
}

export function fetchHomelabProbeMatrix() {
  return fetch("/api/homelab/probes", {
    headers: { Accept: "application/json" },
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error(\n        `homelab probe matrix request failed: HTTP ${response.status}`,\n      );
    }
    return response.json();
  });
}
