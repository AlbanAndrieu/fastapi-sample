// Tiny entrypoint: do not statically import the advanced health UI.
// All rich modules (including their transitive imports) load only when the
// operator explicitly asks for full diagnostics.
import { installPublicServiceOverview } from "./api-public-services.js";

const params = new URLSearchParams(window.location.search);
const safeMode = params.get("ui_safe") === "1";
const operatorMode = params.get("operator") === "1";
// Viewing OWNER controls does not opt into the observer-heavy dashboard.
const richMode = params.get("ui_full") === "1";

function enterPublicDirectory({ allowAdvancedLink = false } = {}) {
  for (const id of [
    "health-board-private-meta", "owner-readonly-detail",
    "truenas-platform", "runtime-topology",
  ]) {
    const element = document.getElementById(id);
    if (element) element.hidden = true;
  }
  document.querySelectorAll(".health-cache-reset, .health-refresh")
    .forEach((button) => {
      button.hidden = true;
      button.disabled = true;
    });
  const heading = document.getElementById("health-summary-text");
  if (heading) {
    heading.textContent = allowAdvancedLink
      ? "Public service directory · detailed diagnostics available on request"
      : "Safe mode · public service directory only · probes not loaded";
  }

  if (allowAdvancedLink && heading && !document.getElementById("health-full-dashboard-link")) {
    const target = new URL(window.location.href);
    target.searchParams.delete("ui_safe");
    target.searchParams.set("ui_full", "1");
    const link = document.createElement("a");
    link.id = "health-full-dashboard-link";
    link.href = target.href;
    link.textContent = "Open detailed diagnostics";
    link.className = "health-full-dashboard-link";
    heading.parentElement?.appendChild(link);
  }

  // Make the operator entry discoverable without loading advanced observers.
  if (allowAdvancedLink && !operatorMode && heading && !document.getElementById("owner-access-link")) {
    const target = new URL(window.location.href);
    target.searchParams.set("operator", "1");
    const link = document.createElement("a");
    link.id = "owner-access-link";
    link.href = target.href;
    link.textContent = "Owner access";
    link.className = "health-full-dashboard-link";
    heading.parentElement?.appendChild(link);
  }

  // This bounded public endpoint does not require an owner session.
  // Its failure must leave a usable page with a visible error message.
  void installPublicServiceOverview({ ownerAuthenticated: false }).catch(() => {
    const summary = document.getElementById("public-services-summary");
    if (summary) summary.textContent = "Public service directory unavailable";
  });
}

// Keep the bounded directory available before importing any advanced modules.
// In particular, operator=1&ui_full=1 must never race the OWNER click handlers
// against observer-heavy imports: that previously left Unlock unclickable.
function showUnavailable(message) {
  const heading = document.getElementById("health-summary-text");
  if (heading) heading.textContent = message;
}

function startRichDashboard() {
  // Restore only the controls allowed for this verified session.
  document.querySelectorAll(".health-refresh").forEach((button) => {
    button.hidden = false;
    button.disabled = false;
  });
  if (operatorMode) {
    document.querySelectorAll(".health-cache-reset").forEach((button) => {
      button.hidden = false;
      button.disabled = false;
    });
  }
  // Keep the public directory visible until a complete health-board
  // refresh is observed. Import success alone is not an operational result.
  document.addEventListener("health-board-refreshed", () => {
    const fallback = document.getElementById("public-services-panel");
    if (fallback) fallback.hidden = true;
  }, { once: true });
  // Give the public directory and OWNER button a chance to paint first.
  // This is a scheduling guard, not proof that all advanced modules are safe.
  window.setTimeout(() => {
    void import("./api-health.js").catch(() => {
      showUnavailable("Detailed diagnostics could not start. The public directory remains available.");
    });
  }, 0);
}

// OWNER controls are a separate lightweight module. Their availability is
// not permission to see private diagnostics; the backend checks the key,
// signed cookie, origin and source IP independently.
let ownerSessionReady = Promise.resolve(false);
if (operatorMode && !safeMode) {
  const panel = document.getElementById("owner-session-panel");
  if (panel) {
    panel.hidden = false;
    ownerSessionReady = import("./api-owner-session.js")
      .then(({ installOwnerSessionControls, ownerSessionAvailable }) => {
        // Await installation BEFORE considering the advanced import.
        installOwnerSessionControls(() => window.location.reload());
        return ownerSessionAvailable();
      })
      .catch(() => {
        const state = document.getElementById("owner-session-state");
        const login = document.getElementById("owner-session-login");
        if (state) state.textContent = "Owner sign-in unavailable; check page assets.";
        if (login) login.disabled = true;
        return false;
      });
  }
}

if (safeMode || !richMode) {
  enterPublicDirectory({ allowAdvancedLink: !safeMode });
} else {
  // A usable catalogue is displayed even when the session or rich imports
  // fail. HTTP 200 on /api does not prove that the browser rendered cards.
  enterPublicDirectory({ allowAdvancedLink: true });
  if (operatorMode) {
    void ownerSessionReady.then((authenticated) => {
      if (!authenticated) {
        showUnavailable(
          "Owner locked. Unlock diagnostics to load the detailed dashboard; public services remain available.",
        );
        return;
      }
      startRichDashboard();
    });
  } else {
    // In read-only mode a 401/403 or timeout must not start the heavy board.
    // A query parameter never grants access to private probes.
    void import("./api-owner-session.js")
      .then(({ diagnosticsReadAvailable }) => diagnosticsReadAvailable())
      .then((readable) => {
        if (readable) startRichDashboard();
        else showUnavailable(
          "Detailed diagnostics not authorized from this session. Public services remain available.",
        );
      })
      .catch(() => showUnavailable(
        "Detailed diagnostics could not verify access. Public services remain available.",
      ));
  }
}
