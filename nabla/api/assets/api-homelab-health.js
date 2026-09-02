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
