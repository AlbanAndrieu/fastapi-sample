// Tiny entrypoint: do not statically import the advanced health UI.
// All rich modules (including their transitive imports) load only when the
// operator explicitly asks for full diagnostics.
import { installPublicServiceOverview } from "./api-public-services.js";

const params = new URLSearchParams(window.location.search);
const safeMode = params.get("ui_safe") === "1";
const richMode = params.get("ui_full") === "1" || params.get("operator") === "1";

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

  // This bounded public endpoint does not require an owner session.
  // Its failure must leave a usable page with a visible error message.
  void installPublicServiceOverview({ ownerAuthenticated: false }).catch(() => {
    const summary = document.getElementById("public-services-summary");
    if (summary) summary.textContent = "Public service directory unavailable";
  });
}

if (safeMode || !richMode) {
  enterPublicDirectory({ allowAdvancedLink: !safeMode });
} else {
  // Never install observer-heavy modules for the default public landing.
  // The imported module still performs normal OWNER/SERVICE permission checks.
  void import("./api-health.js").catch(() => {
    enterPublicDirectory();
  });
}
