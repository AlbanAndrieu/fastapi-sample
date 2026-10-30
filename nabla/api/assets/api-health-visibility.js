import { installPublicServiceOverview } from "./api-public-services.js";

// Page visibility per access mode. Hiding is presentation only: the server
// still enforces OWNER and diagnostics-read permissions on every endpoint.
const PRIVATE_SECTION_IDS = [
  "health-board-private-meta",
  "owner-readonly-detail",
  "truenas-platform",
  "runtime-topology",
];

export function enterPublicFirstDirectory(params) {
  for (const id of PRIVATE_SECTION_IDS) {
    const element = document.getElementById(id);
    if (element) element.hidden = true;
  }
  document
    .querySelectorAll(".health-cache-reset, .health-refresh")
    .forEach((button) => {
      button.hidden = true;
    });
  const heading = document.getElementById("health-summary-text");
  if (heading) {
    heading.textContent =
      params.get("ui_safe") === "1"
        ? "Safe mode · public service directory only · probes not loaded"
        : "Public service directory · detailed diagnostics available on request";
  }
  // Offer the previous rich dashboard without automatically installing its
  // competing observers on every anonymous browser session.
  if (params.get("ui_safe") !== "1") {
    const fullLink = document.createElement("a");
    const target = new URL(window.location.href);
    target.searchParams.set("ui_full", "1");
    fullLink.href = target.href;
    fullLink.textContent = "Open detailed diagnostics";
    fullLink.className = "health-full-dashboard-link";
    const parent =
      heading?.parentElement || document.getElementById("health-board");
    parent?.appendChild(fullLink);
  }
}

export function applyAccessVisibility({
  operatorMode,
  authenticated,
  readable,
}) {
  const panel = document.getElementById("owner-session-panel");
  if (panel) panel.hidden = !operatorMode;
  for (const id of PRIVATE_SECTION_IDS) {
    const element = document.getElementById(id);
    if (element) element.hidden = !readable;
  }

  // An anonymous read-only session may refresh GET probes, never purge caches.
  if (!authenticated) {
    document.querySelectorAll(".health-cache-reset").forEach((button) => {
      button.hidden = true;
      button.disabled = true;
    });
  }
}

export function enterReadOnlyInventory() {
  const heading = document.getElementById("health-summary-text");
  if (heading)
    heading.textContent =
      "Public read-only service inventory · no owner sign-in required.";
  document
    .querySelectorAll(".health-cache-reset, .health-refresh")
    .forEach((button) => {
      button.hidden = true;
    });
}

// The public projection is the independent fallback for a read-only
// dashboard when its private/aggregated health snapshots are stalled.
export async function installReadOnlyPublicFallback() {
  let detailedReady = false;
  document.addEventListener("health-board-refreshed", () => {
    detailedReady = true;
    const fallback = document.getElementById("public-services-panel");
    if (fallback) fallback.hidden = true;
  });
  await installPublicServiceOverview({ ownerAuthenticated: false });
  if (detailedReady) {
    const fallback = document.getElementById("public-services-panel");
    if (fallback) fallback.hidden = true;
  }
}
