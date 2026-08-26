import { loadHealth } from "./api-health-core.js";
import { loadSickz } from "./api-sickz.js";
import {
  decorateCloudflareTunnelStatuses,
  markHealthBoardsPending,
} from "./api-cloudflare-status.js";

function loadHealthBoards() {
  markHealthBoardsPending();
  loadHealth();
  loadSickz();
  decorateCloudflareTunnelStatuses();
}

document.querySelectorAll(".health-refresh").forEach((button) => {
  button.addEventListener("click", loadHealthBoards);
});

loadHealthBoards();
