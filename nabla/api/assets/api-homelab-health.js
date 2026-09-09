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
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Cache-Control": "no-cache",
    },
  }).then((response) => {
    if (!response.ok) {
      throw new Error(`homelab probe matrix HTTP ${response.status}`);
    }
    return response.json();
  });
}
