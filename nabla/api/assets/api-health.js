import { installHealthBoardController } from "./api-health-controller.js";
import { installProbeFanoutDashboard } from "./api-probe-fanout-dashboard.js";
import { startProbeAgeTicker } from "./api-probe-live.js";
import { installServiceDiagnostics } from "./api-service-diagnostics.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";
import { installRuntimeVersionDriftWarning } from "./api-version-drift.js";

installPfsensePortLabels();
installServiceDiagnostics();
installProbeFanoutDashboard();
startProbeAgeTicker();
installHealthBoardController();
installRuntimeVersionDriftWarning();
