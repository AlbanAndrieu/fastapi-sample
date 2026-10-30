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
import * as visibility from "./api-health-visibility.js";
import { installHttpProbeStatuses } from "./api-http-probe-status.js";
import {
  diagnosticsReadAvailable,
  installOwnerSessionControls,
  ownerSessionAvailable,
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
  const params = new URLSearchParams(window.location.search);
  // The public directory is the resilient default: even healthy /api and
  // /api/ui/* HTTP responses cannot prevent a browser MutationObserver loop.
  // Rich diagnostics remain opt-in; this query parameter grants NO owner access.
  const fullDashboardRequested =
    params.get("ui_full") === "1" || params.get("operator") === "1";
  const publicFirst = params.get("ui_safe") === "1" || !fullDashboardRequested;
  if (publicFirst) {
    visibility.enterPublicFirstDirectory(params);
    await installPublicServiceOverview({ ownerAuthenticated: false });
    return;
  }
  const operatorMode =
    new URLSearchParams(window.location.search).get("operator") === "1";
  const [authenticated, readable] = await Promise.all([
    ownerSessionAvailable(),
    diagnosticsReadAvailable(),
  ]);
  visibility.applyAccessVisibility({ operatorMode, authenticated, readable });

  if (!readable) {
    installGlobalServiceFilter();
    visibility.enterReadOnlyInventory();
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
  // OWNER mode uses richer service rows; read-only keeps a public fallback.
  if (!authenticated) await visibility.installReadOnlyPublicFallback();
}

// An import() resolves when the ESM module evaluates, even if the
// asynchronous bootstrap rejects afterwards. Notify the lightweight entry
// without leaking stack traces, credentials or internal diagnostic data.
void bootstrapHealthUi().catch(() => {
  document.dispatchEvent(new Event("health-board-bootstrap-failed"));
});
