import { escapeText } from "./api-health-ui.js";

function statusClass(status) {
  if (status === "ok") return "green";
  if (status === "fail" || status === "error") return "red";
  if (status === "warn") return "yellow";
  return "gray";
}

function findingClass(state) {
  if (state === "MATCH") return "green";
  if (state === "UNEXPECTEDLY_EXPOSED") return "red";
  if (state === "MISSING_EXPOSURE") return "yellow";
  return "gray";
}

function summaryText(data) {
  if (data.status === "disabled") {
    return "Cloudflare exposure audit disabled: read-only credentials are not configured.";
  }
  if (data.status === "error") {
    return `Cloudflare exposure audit failed: ${data.observer_error || "observer error"}.`;
  }
  const summary = data.summary || {};
  return [
    `${summary.match || 0} match`,
    `${summary.unexpectedly_exposed || 0} unexpected exposure`,
    `${summary.missing_exposure || 0} missing exposure`,
    `${summary.unknown || 0} unknown`,
  ].join(" · ");
}

function findingDetail(finding) {
  const desired =
    finding.desired_external === true
      ? "external=true"
      : finding.desired_external === false
        ? "external=false"
        : "not in catalog";
  const observed = finding.observed_exposed ? "observed exposed" : "not observed";
  return `${desired} · ${observed}`;
}

function render(data) {
  const summaryEl = document.getElementById("exposure-summary");
  const summaryLed = document.getElementById("exposure-summary-led");
  const summaryLabel = document.getElementById("exposure-summary-text");
  const listEl = document.getElementById("exposure-checks");
  const errorEl = document.getElementById("exposure-fetch-error");
  if (!summaryEl || !summaryLed || !summaryLabel || !listEl || !errorEl) return;

  errorEl.hidden = true;
  errorEl.textContent = "";
  const cls = statusClass(data.status);
  summaryEl.className = `health-summary health-summary--${cls}`;
  summaryLed.className = `health-led health-led--${cls}`;
  summaryLabel.textContent = summaryText(data);
  listEl.innerHTML = "";

  (data.findings || []).forEach((finding) => {
    const rowCls = findingClass(finding.state);
    const item = document.createElement("li");
    item.className = "health-row";
    item.innerHTML =
      `<span class="health-row-led-wrap"><span class="health-led health-led--${rowCls}" title="${rowCls}"></span></span>` +
      '<div class="health-row-main">' +
      `<div class="health-row-primary health-row-primary--${rowCls}">` +
      `<div class="health-row-name">${escapeText(finding.name || finding.hostname)}</div>` +
      `<div class="health-row-detail">${escapeText(finding.hostname)} · ${escapeText(findingDetail(finding))}</div>` +
      "</div>" +
      `<div class="health-row-tags">${escapeText(finding.state)}</div>` +
      "</div>";
    listEl.appendChild(item);
  });
}

function showError(message) {
  const summaryEl = document.getElementById("exposure-summary");
  const summaryLed = document.getElementById("exposure-summary-led");
  const summaryLabel = document.getElementById("exposure-summary-text");
  const errorEl = document.getElementById("exposure-fetch-error");
  if (!summaryEl || !summaryLed || !summaryLabel || !errorEl) return;
  summaryEl.className = "health-summary health-summary--red";
  summaryLed.className = "health-led health-led--red";
  summaryLabel.textContent = "Could not load Cloudflare exposure audit.";
  errorEl.hidden = false;
  errorEl.textContent = message;
}

export function loadExposureAudit() {
  fetch("/api/homelab/exposure-audit", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch((error) => showError(String(error.message || error)));
}
