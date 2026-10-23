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
import { installOwnerSessionControls, ownerSessionAvailable } from "./api-owner-session.js";
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

// Temporary public read-only mode is the default operator-approved landing.
// Never probe OWNER endpoints or show a Sign in dialog for an anonymous reader.
// Full diagnostics remain available only when a valid session already exists
// (or when the operator explicitly visits /api?operator=1 to unlock).
async function bootstrapHealthUi() {
  const operatorMode = new URLSearchParams(window.location.search).get("operator") === "1";
  const authenticated = await ownerSessionAvailable();
  const panel = document.getElementById("owner-session-panel");
  if (panel) panel.hidden = !operatorMode;

  installGlobalServiceFilter();
  installHealthUiPolish();
  installRuntimeVersionDriftWarning();

  if (!authenticated) {
    const heading = document.getElementById("health-summary-text");
    if (heading) heading.textContent =
      "Public read-only service inventory · no owner sign-in required.";
    document.querySelectorAll(".health-cache-reset, .health-refresh")
      .forEach((button) => { button.hidden = true; });
    if (operatorMode) installOwnerSessionControls(() => window.location.reload());
    await installPublicServiceOverview();
    return;
  }

  installPfsensePortLabels();
  installServiceDiagnostics();
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
  await installPublicServiceOverview({ ownerAuthenticated: true });
}

void bootstrapHealthUi();
