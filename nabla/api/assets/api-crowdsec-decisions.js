import { escapeText } from "./api-health-ui.js";

const PATH = "/api/homelab/crowdsec/decisions";
const TONES = { ok: "ok", empty: "ok", not_observed: "expected" };

function summaryText(data) {
  if (data.state === "ok" || data.state === "empty") {
    const more = data.truncated ? " (first 200 shown)" : "";
    return `🛡 CrowdSec · ${data.count} blocked IP(s) from local decisions${more} · 🍯 ${data.honeypot_count} honeypot`;
  }
  if (data.state === "not_observed") {
    return "◆ CrowdSec blocked IPs · LAN-only: open this panel on the TrueNAS runtime";
  }
  return `⚠ CrowdSec blocked IPs · ${data.state} · ${data.reason || "unknown"}`;
}

function rowsHtml(decisions) {
  return decisions
    .map(
      (row) =>
        `<tr class="${row.honeypot ? "crowdsec-decision--honeypot" : ""}">` +
        `<td>${row.honeypot ? "🍯 " : ""}${escapeText(row.value)}</td>` +
        `<td>${escapeText(row.type)}${row.simulated ? " (simulated)" : ""}</td>` +
        `<td>${escapeText(row.scenario)}</td>` +
        `<td>${escapeText(row.duration)}</td>` +
        `<td>${escapeText(row.origin)}</td></tr>`,
    )
    .join("");
}

function render(panel, data) {
  const summary = panel.querySelector("summary");
  const body = panel.querySelector(".crowdsec-decisions-body");
  summary.className = `crowdsec-decisions-summary crowdsec-decisions-summary--${TONES[data.state] || "warn"}`;
  summary.textContent = summaryText(data);
  const decisions = Array.isArray(data.decisions) ? data.decisions : [];
  const honeypotNote =
    data.state === "ok" || data.state === "empty"
      ? data.honeypot_count
        ? ""
        : "<p>No honeypot ban: login.albandrieu.com visits are only logged until the nabla/honeypot-login-burst scenario is mounted in nabla-compose.</p>"
      : "";
  body.innerHTML =
    honeypotNote +
    (decisions.length
      ? `<table><thead><tr><th>IP / range</th><th>Action</th><th>Scenario</th><th>Remaining</th><th>Origin</th></tr></thead><tbody>${rowsHtml(decisions)}</tbody></table>`
      : "");
}

async function load(panel) {
  try {
    const response = await fetch(PATH, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (response.status === 403) {
      render(panel, { state: "locked", reason: "owner session required" });
      return;
    }
    render(panel, await response.json());
  } catch (error) {
    render(panel, {
      state: "unavailable",
      reason: String(error?.message || error),
    });
  }
}

export function installCrowdsecDecisions() {
  const target = document.getElementById("truenas-platform-target");
  if (!target || document.getElementById("crowdsec-decisions")) return;
  const panel = document.createElement("details");
  panel.id = "crowdsec-decisions";
  panel.className = "crowdsec-decisions";
  panel.innerHTML =
    '<summary class="crowdsec-decisions-summary">🛡 CrowdSec blocked IPs · open to load (owner)</summary><div class="crowdsec-decisions-body"></div>';
  // Raw IPs are fetched on demand only, never on the periodic health refresh.
  panel.addEventListener("toggle", () => {
    if (panel.open) void load(panel);
  });
  target.insertAdjacentElement("afterend", panel);
}
