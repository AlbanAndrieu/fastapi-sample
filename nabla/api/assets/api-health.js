import { loadHealth } from "./api-health-core.js";
import { loadSickz } from "./api-sickz.js";

function loadHealthBoards() {
  loadHealth();
  loadSickz();
}

document.querySelectorAll(".health-refresh").forEach((button) => {
  button.addEventListener("click", loadHealthBoards);
});

loadHealthBoards();
