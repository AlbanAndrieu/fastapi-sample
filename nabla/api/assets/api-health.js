import { installGlobalServiceFilter } from "./api-global-service-filter.js";
import { installHealthBoardController } from "./api-health-controller.js";
import { installHealthOperatorUx } from "./api-health-operator-ux.js";
import { installHealthUiConsistencyFollowup } from "./api-health-ui-consistency-followup.js";
import { installHealthUiFinalFollowup } from "./api-health-ui-final-followup.js";
import { installHealthUiOperatorFollowup } from "./api-health-ui-operator-followup.js";
import { installHealthUiPolish } from "./api-health-ui-polish.js";
import { installHealthUiProbeExplanations } from "./api-health-ui-probe-explanations.js";
import { installHealthUiProbeGrid } from "./api-health-ui-probe-grid.js";
import { installHealthUiResponsiveFollowup } from "./api-health-ui-responsive-followup.js";
import { installHttpProbeStatuses } from "./api-http-probe-status.js";
import {
  installOwnerSessionControls,
  ownerSessionAvailable,
  diagnosticsReadAvailable,
} from "./api-owner-session.js";
import { installPfsenseSecurityPosture } from "./api-pfsense-security-posture.js";
import { installPlatformFlowUi } from "./api-platform-flow-ui.js";
import { installPlatformLegend } from "./api-platform-legend.js";
import { installProbeFanoutDashboard } from "./api-probe-fanout-dashboard.js";
import { startProbeAgeTicker } from "./api-probe-live.js";
import { installPublicServiceOverview } from "./api-public-services.js";
import { installServiceDependencyPriority } from "./api-service-dependency-priority.js";
import { installServiceDetailDrawer } from "./api-service-detail-drawer.js";
import { installServiceDiagnostics } from "./api-service-diagnostics.js";
import { installServiceOperatorDiagnostics } from "./api-service-operator-diagnostics.js";
import { installServiceProbeDetails } from "./api-service-probe-details.js";
import { installServiceProbeHelp } from "./api-service-probe-help.js";
import { installServiceProbePlanes } from "./api-service-probe-planes.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";
import { installRuntimeVersionDriftWarning } from "./api-version-drift.js";

// Temporary read-only diagnostics restore the detailed probe dashboard without
// granting the browser an owner identity or access to mutation endpoints.
async function bootstrapHealthUi() {
  const operatorMode =
    new URLSearchParams(window.location.search).get("operator") === "1";
  const [authenticated, readable] = await Promise.all([
    ownerSessionAvailable(),
    diagnosticsReadAvailable(),
  ]);
  const panel = document.getElementById("owner-session-panel");
  if (panel) panel.hidden = !operatorMode;
  for (const id of [
    "health-board-private-meta",
    "owner-readonly-detail",
    "truenas-platform",
    "runtime-topology",
  ]) {
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

  if (!readable) {
    installGlobalServiceFilter();
    const heading = document.getElementById("health-summary-text");
    if (heading)
      heading.textContent =
        "Public read-only service inventory · no owner sign-in required.";
    document
      .querySelectorAll(".health-cache-reset, .health-refresh")
      .forEach((button) => {
        button.hidden = true;
      });
    if (operatorMode)
      installOwnerSessionControls(() => window.location.reload());
    await installPublicServiceOverview();
    return;
  }

  installHealthUiPolish();
  installRuntimeVersionDriftWarning();
  installPfsensePortLabels();
  installServiceDiagnostics();
  // The advanced controls must exist before the global disclosure wraps them.
  installGlobalServiceFilter();
  installPlatformLegend();
  installHealthOperatorUx();
  installServiceDetailDrawer();
  installProbeFanoutDashboard();
  startProbeAgeTicker();
  installHttpProbeStatuses();
  installHealthBoardController();
  if (operatorMode) installOwnerSessionControls(() => window.location.reload());
  installServiceOperatorDiagnostics();
  installServiceProbeDetails();
  installServiceProbeHelp();
  installServiceProbePlanes();
  installPfsenseSecurityPosture();
  installPlatformFlowUi();
  void installServiceDependencyPriority();
  installHealthUiResponsiveFollowup();
  installHealthUiProbeExplanations();
  installHealthUiOperatorFollowup();
  installHealthUiConsistencyFollowup();
  installHealthUiProbeGrid();
  installHealthUiFinalFollowup();
  // The public projection is the independent fallback for a read-only
  // dashboard when its private/aggregated health snapshots are stalled.
  // OWNER mode still uses the richer service rows directly.
  if (!authenticated) {
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
}

void bootstrapHealthUi();
