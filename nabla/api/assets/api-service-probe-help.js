const ROW_SELECTOR = ".health-row[data-service-filter-target]";

function decorateRow(row) {
  const popover = row.querySelector(".service-help-popover");
  if (!popover) return;
  const current = popover.querySelector("[data-service-probe-help-timing]");

  const httpProbe = row.querySelector('[data-probe-kind="http"]');
  const detail = String(
    httpProbe?.getAttribute("aria-label") || httpProbe?.title || "",
  ).trim();
  if (!detail) {
    current?.remove();
    return;
  }
  const text = `HTTP probe: ${detail}`;
  // Update in place: an open popover must not lose and regain this line.
  if (current) {
    if (current.textContent !== text) current.textContent = text;
    return;
  }
  const timing = document.createElement("span");
  timing.dataset.serviceProbeHelpTiming = "true";
  timing.textContent = text;
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
