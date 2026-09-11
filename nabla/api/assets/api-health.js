import { installHealthBoardController } from "./api-health-controller.js";
import { installProbeFanoutDashboard } from "./api-probe-fanout-dashboard.js";
import { startProbeAgeTicker } from "./api-probe-live.js";
import { installServiceFilter } from "./api-service-groups.js";
import { installPfsensePortLabels } from "./api-sickz-port-labels.js";
import { installRuntimeVersionDriftWarning } from "./api-version-drift.js";

installPfsensePortLabels();
installServiceFilter();
installProbeFanoutDashboard();
startProbeAgeTicker();
installHealthBoardController();
installRuntimeVersionDriftWarning();
