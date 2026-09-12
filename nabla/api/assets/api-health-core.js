import { fetchHealthBoard } from "./api-health-board.js";
import {
  dependencyHealthClass,
  mergeHomelabEvidence,
} from "./api-health-dependency.js";
import {
  detailText,
  isExpectedSentryDebugFailure,
} from "./api-health-detail.js";
import {
  escapeText,
  httpStatusIsSuccess2xx,
  lockHtml,
  rowIcon,
  tunnelHref,
} from "./api-health-ui.js";
import { organizeHealthRows } from "./api-service-groups.js";

let lastHealthRowsSignature = null;

const LABELS = {
  redis: "Redis",
  postgres: "PostgreSQL",
  supabase: "Supabase",
  openstack_me: "OVH / OpenStack API",
  tavily: "Tavily Search",
  brave: "Brave Search",
  google: "Google Programmable Search",
  appwrite: "Appwrite",
  keycloak: "Keycloak (OpenID)",
  unleash: "Unleash",
  sentry: "Sentry",
  logfire: "Pydantic Logfire",
  datadog: "Datadog Agent",
  pyroscope: "Pyroscope",
  litellm: "LiteLLM proxy",
  cloudflare: "Cloudflare Tunnels",
  pfsense: "pfSense API",
  truenas_api: "TrueNAS API",
  albandrieu_twofactor: "twofactor-auth",
  albandrieu_nexus: "nexus",
  albandrieu_keycloak_ui: "keycloak",
  albandrieu_homarr: "homarr",
  albandrieu_plumber_api: "plumber-api",
  albandrieu_reactive_resume: "reactive-resume",
  albandrieu_vaultwarden: "vaultwarden-albandrieu",
  albandrieu_truenas: "TrueNAS HTTPS",
};

export const MANDATORY = new Set([
  "postgres",
  "redis",
  "supabase",
  "albandrieu_twofactor",
  "albandrieu_nexus",
  "albandrieu_keycloak_ui",
  "albandrieu_homarr",
  "albandrieu_plumber_api",
  "albandrieu_reactive_resume",
  "albandrieu_vaultwarden",
  "albandrieu_truenas",
]);

function healthRowTitleHtml(check, key) {
  let rowTitle = "";
  if (check.name != null && String(check.name).trim())
    rowTitle = String(check.name).trim();
  else if (check.display_label != null) rowTitle = String(check.display_label);
  else if (LABELS[key]) rowTitle = LABELS[key];
  else rowTitle = key;
  const hrefRaw = tunnelHref(check);
  const lock = lockHtml(check.tls_trusted, hrefRaw);
  const inner =
    hrefRaw.length > 0
      ? `<a class="sickz-target-link" target="_blank" rel="noopener noreferrer" href="${escapeText(hrefRaw)}">${escapeText(rowTitle)}</a>`
      : `<span>${escapeText(rowTitle)}</span>`;
  return `<div class="health-row-name health-row-name--sickz">${lock}${inner}</div>`;
}

function classify(key, check) {
  if (key === "cloudflare") {
    if (check.skipped === true) return "gray";
    if (check.api_reachable === true && check.status_confirmed === true) {
      return check.state === "warn" ? "yellow" : "green";
    }
    // Cloudflare control-plane uncertainty is not a provider outage. Keep the
    // Card neutral/unknown and disable API-derived policy controls elsewhere.
    return "gray";
  }
  if (check.skipped === true) return "yellow";
  if (
    key === "pfsense" &&
    check?.ingress_policy?.state === "possible_ingress_policy_block"
  )
    return "yellow";
  if (isExpectedSentryDebugFailure(key, check)) return "green";
  const dependencyClass = dependencyHealthClass(check);
  if (dependencyClass) return dependencyClass;
  if (check.reachable === true) {
    if (key === "truenas_api") return "green";
    if (!httpStatusIsSuccess2xx(check.http_status)) return "blue";
    return "green";
  }
  if (check.reachable === false) return "red";
  return "gray";
}

function mandatoryFailed(key, check) {
  if (!MANDATORY.has(key)) return false;
  if (check.skipped === true) return false;
  if (check.effective_state) return check.effective_state === "fail";
  return check.reachable === false;
}

function sortKeys(keys) {
  const first = [
    "postgres",
    "redis",
    "supabase",
    "albandrieu_twofactor",
    "albandrieu_nexus",
    "albandrieu_keycloak_ui",
    "albandrieu_homarr",
    "albandrieu_plumber_api",
    "albandrieu_reactive_resume",
    "albandrieu_vaultwarden",
    "albandrieu_truenas",
    "truenas_api",
    "cloudflare",
    "pfsense",
    "litellm",
    "sentry",
    "logfire",
  ];
  const rest = keys.filter((key) => first.indexOf(key) === -1).sort();
  return first.filter((key) => keys.indexOf(key) !== -1).concat(rest);
}

function computeOverall(data) {
  const checks = data.checks || {};
  let anyYellow = false;
  let anyOptionalRed = false;
  let anyBlue = false;
  for (const key of Object.keys(checks)) {
    const check = checks[key];
    if (mandatoryFailed(key, check)) {
      return {
        cls: "red",
        text: "A required health check failed. Review service outcomes and critical core components below to determine impact and likely cause.",
      };
    }
    const classification = classify(key, check);
    if (classification === "yellow") anyYellow = true;
    if (classification === "red" && !MANDATORY.has(key)) anyOptionalRed = true;
    if (classification === "blue") anyBlue = true;
  }
  const status = data.status;
  if (status && status !== "healthy") {
    anyYellow = true;
    const critical =
      status === "health_fetch_failed" ||
      status === "health_endpoint_non_200" ||
      status === "health_invalid_json" ||
      status === "health_unexpected_shape";
    if (critical) {
      return {
        cls: "red",
        text: `Base /health check failed (${status}).${data.error ? ` ${data.error}` : ""}`,
      };
    }
  }
  if (anyOptionalRed) {
    return {
      cls: "yellow",
      text: "One or more probed services or integrations need attention. Review the service and platform summaries below for impact.",
    };
  }
  if (anyBlue) {
    return {
      cls: "blue",
      text: "A service responded over HTTP but returned a status outside 2xx (e.g. 400, 502, 530); see rows for codes.",
    };
  }
  if (anyYellow) {
    return {
      cls: "yellow",
      text: "One or more checks are degraded, intentionally skipped, or waiting for complete evidence.",
    };
  }
  return {
    cls: "green",
    text: "All currently probed health checks are healthy.",
  };
}

function renderSnapshotFreshness(snapshot) {
  const element = document.getElementById("health-board-freshness");
  if (!element) return;

  const state = String(snapshot?.state || "unknown");
  const age = Number(snapshot?.age_seconds);
  const generatedAt = snapshot?.generated_at;
  const refreshing = snapshot?.refreshing === true;
  const parts = [];

  if (state === "fresh") parts.push("● fresh snapshot");
  else if (state === "stale") parts.push("◐ cached snapshot");
  else parts.push(`◌ ${state} snapshot`);

  if (Number.isFinite(age)) parts.push(`${Math.round(age)}s old`);
  if (generatedAt) parts.push(`generated ${String(generatedAt)}`);
  if (refreshing) parts.push("refresh in progress");
  if (snapshot?.error)
    parts.push(`last refresh error: ${String(snapshot.error)}`);

  element.textContent = parts.join(" · ");
}

function healthRowsSignature(checks) {
  return JSON.stringify(
    Object.keys(checks)
      .sort()
      .map((key) => {
        const check = checks[key] || {};
        return [
          key,
          check.name,
          check.display_label,
          check.service_id,
          check.reachable,
          check.api_reachable,
          check.status_confirmed,
          check.state,
          check.tunnel_count,
          check.healthy_tunnels,
          check.inactive_tunnels,
          check.degraded_or_down_tunnels,
          check.local_state,
          check.dependency_state,
          check.effective_state,
          check.http_status,
          check.skipped,
          check.warning,
          check.error_kind,
          check.stage,
          check.error,
          check.path,
          check.host,
          check.port,
          check.url,
          check.tls_trusted,
          check.dependency_detail,
        ];
      }),
  );
}

function render(data, platformMetrics = null) {
  const listEl = document.getElementById("health-checks");
  const summaryEl = document.getElementById("health-summary");
  const summaryText = document.getElementById("health-summary-text");
  const summaryLed = document.getElementById("health-summary-led");
  const errEl = document.getElementById("health-fetch-error");
  errEl.hidden = true;
  errEl.textContent = "";
  const overall = computeOverall(data);
  summaryEl.className = `health-summary health-summary--${overall.cls}`;
  summaryLed.className = `health-led health-led--${overall.cls}`;
  summaryText.textContent = overall.text;
  const checks = data.checks || {};
  const signature = healthRowsSignature(checks);
  if (signature === lastHealthRowsSignature) return;
  lastHealthRowsSignature = signature;
  const keys = sortKeys(Object.keys(checks)).filter(
    (key) => key !== "truenas_api",
  );
  listEl.innerHTML = "";
  const groupedEl = document.getElementById("health-services-groups");
  if (groupedEl) groupedEl.innerHTML = "";
  keys.forEach((key) => {
    const check = checks[key];
    const tier = MANDATORY.has(key)
      ? key.indexOf("albandrieu_") === 0
        ? "Required infra (albandrieu.com)"
        : "Required health check"
      : "Optional health check";
    const cls = classify(key, check);
    const item = document.createElement("li");
    item.className = "health-row";
    item.dataset.serviceFilterTarget = "";
    item.dataset.serviceKey = key;
    item.dataset.serviceName = String(
      check.name || check.display_label || LABELS[key] || key,
    );
    item.dataset.serviceUrl = tunnelHref(check);
    item.dataset.searchText = [
      key,
      item.dataset.serviceName,
      item.dataset.serviceUrl,
      detailText(key, check),
      tier,
    ]
      .join(" ")
      .toLowerCase();
    item.innerHTML =
      rowIcon(check, key, cls) +
      `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
      '<div class="health-row-main">' +
      `<div class="health-row-primary health-row-primary--${cls}">` +
      healthRowTitleHtml(check, key) +
      `<div class="health-row-detail">${escapeText(detailText(key, check))}</div></div>` +
      `<div class="health-row-tags">${tier}</div>` +
      "</div>";
    listEl.appendChild(item);
  });
  organizeHealthRows(data, platformMetrics);
}

function showFetchError(message) {
  lastHealthRowsSignature = null;
  const summaryEl = document.getElementById("health-summary");
  const summaryText = document.getElementById("health-summary-text");
  const summaryLed = document.getElementById("health-summary-led");
  const errEl = document.getElementById("health-fetch-error");
  document.getElementById("health-checks").innerHTML = "";
  const groupedEl = document.getElementById("health-services-groups");
  if (groupedEl) groupedEl.innerHTML = "";
  summaryEl.className = "health-summary health-summary--red";
  summaryLed.className = "health-led health-led--red";
  summaryText.textContent = "Could not load /healthz.";
  errEl.hidden = false;
  errEl.textContent = message;
}

export function loadHealth() {
  return fetchHealthBoard()
    .then((snapshot) => {
      renderSnapshotFreshness(snapshot);
      const data = snapshot.healthz;
      if (!data) throw new Error("health snapshot is missing /healthz data");
      const homelab = snapshot.homelab;
      const merged = homelab ? mergeHomelabEvidence(data, homelab) : data;
      render(merged, snapshot.platform_metrics);
    })
    .catch((error) => {
      showFetchError(String(error.message || error));
    });
}
