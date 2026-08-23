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
  albandrieu_twofactor: "twofactor-auth",
  albandrieu_nexus: "nexus",
  albandrieu_keycloak_ui: "keycloak",
  albandrieu_homarr: "homarr",
  albandrieu_plumber_api: "plumber-api",
  albandrieu_reactive_resume: "reactive-resume",
  albandrieu_vaultwarden: "vaultwarden-albandrieu",
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
]);

const SELFHST_ICON_CDN = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/";
const HEALTHZ_ICON_IMG = {
  postgres: "postgresql.svg",
  redis: "redis.svg",
  supabase: "supabase.svg",
  openstack_me: "ovh.svg",
  tavily: "searxng.svg",
  brave: "brave.svg",
  google: "google.svg",
  appwrite: "appwrite.svg",
  keycloak: "keycloak.svg",
  sentry: "sentry.svg",
  datadog: "datadog.svg",
  pyroscope: "grafana.svg",
  litellm: "litellm.svg",
  cloudflare: "cloudflare.svg",
  albandrieu_twofactor: "2fauth.svg",
  albandrieu_nexus: "sonatype-nexus-repository.svg",
  albandrieu_keycloak_ui: "keycloak.svg",
  albandrieu_homarr: "homarr.svg",
  albandrieu_plumber_api: "docker.svg",
  albandrieu_reactive_resume: "reactive-resume.svg",
  albandrieu_vaultwarden: "vaultwarden.svg",
  sickz_url: "pfsense.svg",
};

const ICON_PATHS = {
  unleash:
    '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
  infra_host: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8M12 8v8"/>',
  _default:
    '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 12h6M12 9v6"/>',
};

function normalizeIconSrc(raw) {
  const value = raw == null ? "" : String(raw).trim();
  if (!value) return "";
  if (value.toLowerCase().slice(0, 2) === "//") return `https:${value}`;
  return value;
}

function iconSrcIsHttpUrl(value) {
  const lower = String(value).toLowerCase();
  return lower.slice(0, 8) === "https://" || lower.slice(0, 7) === "http://";
}

function serviceIconSvg(key, statusCls) {
  const imgFile = HEALTHZ_ICON_IMG[key];
  if (imgFile) {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${SELFHST_ICON_CDN}${imgFile}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  const path =
    ICON_PATHS[key] ||
    (key.indexOf("albandrieu_") === 0 ? ICON_PATHS.infra_host : ICON_PATHS._default);
  return (
    `<span class="health-row-icon health-row-icon--${statusCls}" aria-hidden="true">` +
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
    path +
    "</svg></span>"
  );
}

export function escapeText(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function healthRowIcon(check, key, statusCls) {
  let rawPick = "";
  if (check.icon_src && typeof check.icon_src === "string") rawPick = check.icon_src;
  else if (check.iconSrc && typeof check.iconSrc === "string") rawPick = check.iconSrc;
  const absRaw = normalizeIconSrc(rawPick);
  if (iconSrcIsHttpUrl(absRaw)) {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${escapeText(absRaw)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  const filename = check.icon_filename;
  if (filename && typeof filename === "string") {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${SELFHST_ICON_CDN}${escapeText(filename)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  return serviceIconSvg(key, statusCls);
}

export function shortHostForDetail(url) {
  let value = String(url).replace(/^https?:\/\//i, "");
  const slash = value.indexOf("/");
  if (slash !== -1) value = value.slice(0, slash);
  const suffix = ".albandrieu.com";
  if (value.toLowerCase().endsWith(suffix)) {
    return value.slice(0, -suffix.length) || value;
  }
  return value;
}

export function lockHtml(tlsTrusted, hrefRaw) {
  const href = (hrefRaw || "").trim().toLowerCase();
  const isHttps = href.indexOf("https:") === 0;
  let wrapCls;
  let label;
  if (!isHttps) {
    wrapCls = "sickz-lock--unknown";
    label = "TLS: not applicable (non-HTTPS or no link)";
  } else if (tlsTrusted === true) {
    wrapCls = "sickz-lock--trusted";
    label = "TLS: certificate validated";
  } else {
    wrapCls = "sickz-lock--untrusted";
    label =
      tlsTrusted === false
        ? "TLS: certificate not trusted"
        : "TLS: not validated (unreachable or check incomplete)";
  }
  const lockPaths =
    '<rect x="5" y="11" width="14" height="10" rx="2" ry="2"/>' +
    '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>';
  return (
    `<span class="sickz-lock-wrap ${wrapCls}" role="img" aria-label="${escapeText(label)}">` +
    '<svg class="sickz-lock-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
    lockPaths +
    "</svg></span>"
  );
}

export function sickzRowIcon(check, statusCls) {
  let rawPick = "";
  if (check.icon_src && typeof check.icon_src === "string") rawPick = check.icon_src;
  else if (check.iconSrc && typeof check.iconSrc === "string") rawPick = check.iconSrc;
  const absRaw = normalizeIconSrc(rawPick);
  if (iconSrcIsHttpUrl(absRaw)) {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${escapeText(absRaw)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  const filename = check.icon_filename;
  if (filename && typeof filename === "string") {
    return (
      `<span class="health-row-icon health-row-icon--img health-row-icon--${statusCls}" aria-hidden="true">` +
      `<img src="${SELFHST_ICON_CDN}${escapeText(filename)}" alt="" width="26" height="26" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" />` +
      "</span>"
    );
  }
  return serviceIconSvg("sickz_url", statusCls);
}

export function tunnelHref(check) {
  const url =
    (check.tunnel_url && String(check.tunnel_url).trim()) ||
    (check.tunnelUrl && String(check.tunnelUrl).trim()) ||
    (check.href && String(check.href).trim()) ||
    "";
  return url.trim();
}

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

export function httpStatusIsSuccess2xx(code) {
  if (code == null) return true;
  const status = Number(code);
  if (Number.isNaN(status)) return true;
  return status >= 200 && status < 300;
}

function isExpectedSentryDebugFailure(key, check) {
  return (
    key === "sentry" &&
    check.reachable === true &&
    Number(check.http_status) === 500 &&
    (check.via === "/sentry-debug" || check.path === "/sentry-debug")
  );
}

function classify(key, check) {
  if (check.skipped === true) return "yellow";
  if (isExpectedSentryDebugFailure(key, check)) return "green";
  if (check.reachable === true) {
    if (!httpStatusIsSuccess2xx(check.http_status)) return "blue";
    return "green";
  }
  if (check.reachable === false) return "red";
  return "gray";
}

function mandatoryFailed(key, check) {
  if (!MANDATORY.has(key)) return false;
  if (check.skipped === true) return false;
  return check.reachable === false;
}

function detailText(key, check) {
  if (check.skipped) return check.reason || "Not configured (intentionally disabled).";
  if (isExpectedSentryDebugFailure(key, check)) {
    return "HTTP 500 · Expected: the test error was intentionally triggered and captured by Sentry.";
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
        text: "A required check failed: PostgreSQL, Redis, Supabase (when configured), and required albandrieu.com infra HTTPS endpoints must be reachable.",
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
    return { cls: "yellow", text: "Core dependencies OK. One or more optional integrations are failing." };
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
      text: "Core dependencies OK. Yellow = env not set (disabled on purpose) or minor /health note.",
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
  const keys = sortKeys(Object.keys(checks));
  listEl.innerHTML = "";
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
    item.innerHTML =
      healthRowIcon(check, key, cls) +
      `<span class="health-row-led-wrap"><span class="health-led health-led--${cls}" title="${cls}"></span></span>` +
      '<div class="health-row-main">' +
      `<div class="health-row-primary health-row-primary--${cls}">` +
      healthRowTitleHtml(check, key) +
      `<div class="health-row-detail">${detailText(key, check)}</div></div>` +
      `<div class="health-row-tags">${tier}</div>` +
      "</div>";
    listEl.appendChild(item);
  });
}

function showFetchError(message) {
  const summaryEl = document.getElementById("health-summary");
  const summaryText = document.getElementById("health-summary-text");
  const summaryLed = document.getElementById("health-summary-led");
  const errEl = document.getElementById("health-fetch-error");
  document.getElementById("health-checks").innerHTML = "";
  summaryEl.className = "health-summary health-summary--red";
  summaryLed.className = "health-led health-led--red";
  summaryText.textContent = "Could not load /healthz.";
  errEl.hidden = false;
  errEl.textContent = message;
}

export function loadHealth() {
  fetch("/healthz", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch((error) => {
      showFetchError(String(error.message || error));
    });
}
