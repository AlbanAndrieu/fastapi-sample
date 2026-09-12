const ROW_SELECTOR = ".health-row[data-service-filter-target]";

function decorateRow(row) {
  const popover = row.querySelector(".service-help-popover");
  if (!popover) return;
  popover.querySelector("[data-service-probe-help-timing]")?.remove();

  const httpProbe = row.querySelector('[data-probe-kind="http"]');
  if (!httpProbe) return;
  const detail = String(httpProbe.getAttribute("aria-label") || httpProbe.title || "").trim();
  if (!detail) return;

  const timing = document.createElement("span");
  timing.dataset.serviceProbeHelpTiming = "true";
  timing.textContent = `HTTP probe: ${detail}`;
  popover.appendChild(timing);
}

function decorate() {
  document.querySelectorAll(ROW_SELECTOR).forEach(decorateRow);
}

function schedule() {
  window.requestAnimationFrame(decorate);
  window.setTimeout(decorate, 150);
}

export function installServiceProbeHelp() {
  schedule();
  document.addEventListener("health-board-refreshed", schedule);
}
