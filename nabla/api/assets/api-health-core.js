import {
  escapeText,
  httpStatusIsSuccess2xx,
  lockHtml,
  rowIcon,
  tunnelHref,
} from "./api-health-ui.js";
import { organizeHealthRows } from "./api-service-groups.js";

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

const HOMELAB_EVIDENCE_FIELDS = [
  "local_state",
  "dependency_state",
  "effective_state",
  "required_dependencies",
  "blocked_by",
  "dependency_evidence",
  "dependency_cycle",
  "observed_at",
  "observation_age_seconds",
  "observation_stale",
  "direct_state",
  "internal_state",
  "runtime_state",
  "runtime_app",
  "runtime_reachable",
  "tunnel_status",
  "tunnel_name",
];

function healthRowTitleHtml(check, key) {
  let rowTitle = "";
  if (check.name != null && String(check.name).trim()) rowTitle = String(check.name).trim();
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

function isExpectedSentryDebugFailure(key, check) {
  return (
    key === "sentry" &&
    check.reachable === true &&
    Number(check.http_status) === 500 &&
    (check.via === "/sentry-debug" || check.path === "/sentry-debug")
  );
}

function healthStateClass(state) {
  if (state === "ok") return "green";
  if (state === "warn") return "yellow";
  if (state === "fail") return "red";
  return "gray";
}

function classify(key, check) {
  if (check.skipped === true) return "yellow";
  if (isExpectedSentryDebugFailure(key, check)) return "green";
  if (check.effective_state) return healthStateClass(check.effective_state);
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

function baseDetailText(key, check) {
  if (check.skipped) return check.reason || "Not configured (intentionally disabled).";
  if (isExpectedSentryDebugFailure(key, check)) {
    return "HTTP 500 · Expected: the test error was intentionally triggered and captured by Sentry.";
  }
  if (key === "truenas_api" && check.reachable === true) {
    const parts = ["WebSocket API connected"];
    if (check.version) parts.push(String(check.version));
    if (check.app_count != null) parts.push(`${check.app_count} apps`);
    return parts.join(" · ");
  }
  if (check.reachable === true) {
    const parts = [];
    if (check.http_status != null) parts.push(`HTTP ${check.http_status}`);
    if (check.path) parts.push(check.path);
    if (check.host != null && check.port != null) parts.push(`${check.host}:${check.port}`);
    if (check.url) parts.push(String(check.url).replace(/^https?:\/\//i, ""));
    return parts.length ? parts.join(" · ") : "Connected.";
  }
  if (check.error) return check.error;
  return "Unreachable.";
}

function dependencyBlockedLabels(check) {
  const blocked = new Set(Array.isArray(check.blocked_by) ? check.blocked_by : []);
  if (blocked.size === 0) return [];
  const evidence = Array.isArray(check.dependency_evidence) ? check.dependency_evidence : [];
  return [...blocked].map((target) => {
    const item = evidence.find((entry) => entry?.target === target);
    return String(item?.target_name || target);
  });
}

function evidenceSources(check) {
  const sources = [];
  if (check.direct_state) sources.push("HTTP");
  if (check.internal_state) sources.push("internal probe");
  if (check.runtime_state) sources.push("TrueNAS runtime");
  if (check.tunnel_status) sources.push("Cloudflare tunnel");
  return sources;
}

function dependencyDetailText(check) {
  if (!check.effective_state) return "";
  const parts = [];
  const runtimeRunning = String(check.runtime_state || "").toUpperCase() === "RUNNING";
  if (runtimeRunning && check.effective_state !== "ok") parts.push("RUNNING but degraded");
  if (check.local_state && check.local_state !== check.effective_state) {
    parts.push(`local ${check.local_state} → effective ${check.effective_state}`);
  }
  const blocked = dependencyBlockedLabels(check);
  if (blocked.length > 0) parts.push(`blocked by ${blocked.join(", ")}`);
  const sources = evidenceSources(check);
  if (sources.length > 0) parts.push(`evidence: ${sources.join(" + ")}`);
  if (check.observation_stale === true) {
    const age = Number(check.observation_age_seconds);
    parts.push(Number.isFinite(age) ? `stale evidence (${Math.round(age)}s old)` : "stale evidence");
  } else if (check.observation_age_seconds != null) {
    const age = Number(check.observation_age_seconds);
    if (Number.isFinite(age)) parts.push(`observed ${Math.round(age)}s ago`);
  }
  const cycle = Array.isArray(check.dependency_cycle) ? check.dependency_cycle : [];
  if (cycle.length > 1) parts.push(`dependency cycle: ${cycle.join(" ↔ ")}`);
  return parts.join(" · ");
}

function detailText(key, check) {
  const details = [baseDetailText(key, check), dependencyDetailText(check)].filter(Boolean);
  return details.join(" · ");
}

function candidateServiceIds(key, check) {
  const ids = [check?.service_id, check?.id, key];
  if (String(key).startsWith("albandrieu_")) ids.push(String(key).slice("albandrieu_".length));
  return ids.filter(Boolean).map((value) => String(value).replaceAll("_", "-"));
}

function mergeHomelabEvidence(data, homelab) {
  const rows = Array.isArray(homelab?.services) ? homelab.services : [];
  const byId = new Map(rows.filter((row) => row?.id).map((row) => [String(row.id), row]));
  for (const [key, check] of Object.entries(data?.checks || {})) {
    const evidence = candidateServiceIds(key, check)
      .map((candidate) => byId.get(candidate))
      .find(Boolean);
    if (!evidence) continue;
    for (const field of HOMELAB_EVIDENCE_FIELDS) {
      if (Object.prototype.hasOwnProperty.call(evidence, field)) check[field] = evidence[field];
    }
  }
  return data;
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
        text: "A required check failed: PostgreSQL, Redis, Supabase (when configured), and required albandrieu.com infra HTTPS endpoints including TrueNAS must be reachable.",
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
      text: "Core dependencies OK. One or more optional integrations are failing.",
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
      text: "Core dependencies OK. Yellow = degraded dependency, env not set, or a minor health note.",
    };
  }
  return { cls: "green", text: "All probed services are reachable." };
}

function render(data) {
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
  const keys = sortKeys(Object.keys(checks)).filter((key) => key !== "truenas_api" && key !== "albandrieu_truenas");
  listEl.innerHTML = "";
  const groupedEl = document.getElementById("health-services-groups");
  if (groupedEl) groupedEl.innerHTML = "";
  keys.forEach((key) => {
    const check = checks[key];
    const tier = MANDATORY.has(key)
      ? key.indexOf("albandrieu_") === 0
        ? "Required infra (albandrieu.com)"
        : "Required for core stack"
      : "Optional integration";
    const cls = classify(key, check);
    const item = document.createElement("li");
    item.className = "health-row";
    item.dataset.serviceFilterTarget = "";
    item.dataset.serviceKey = key;
    item.dataset.serviceName = String(check.name || check.display_label || LABELS[key] || key);
    item.dataset.serviceUrl = tunnelHref(check);
    item.dataset.searchText = [
      key,
      item.dataset.serviceName,
      item.dataset.serviceUrl,
      detailText(key, check),
      tier,
    ].join(" ").toLowerCase();
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
  organizeHealthRows(data);
}

function showFetchError(message) {
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

function fetchJson(path, { required = true } = {}) {
  return fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .catch((error) => {
      if (required) throw error;
      return null;
    });
}

export function loadHealth() {
  Promise.all([
    fetchJson("/healthz"),
    fetchJson("/api/homelab/health", { required: false }),
  ])
    .then(([data, homelab]) => render(mergeHomelabEvidence(data, homelab)))
    .catch((error) => {
      showFetchError(String(error.message || error));
    });
}
