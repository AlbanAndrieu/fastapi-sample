import { fetchHealthBoard } from "./api-health-board.js";
import {
  installServiceFilter,
  refreshServiceFilter,
} from "./api-service-filter.js";

const PROBE_ICONS = {
  http: "🌐",
  tls: "🔒",
  tcp: "🔌",
  api: "⚙️",
  websocket: "↔️",
  cloudflare: "☁️",
  access: "🛡️",
  "service-token": "🔑",
  metrics: "📊",
  policy: "🛡️",
};

let latestSnapshot = null;
let refreshScheduled = false;
let decorating = false;

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value)).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function urlOf(check) {
  const aliases = Array.isArray(check?.aliases_probed)
    ? check.aliases_probed
    : [];
  const candidates = [
    check?.tunnel_url,
    check?.tunnelUrl,
    check?.href,
    check?.url,
    ...aliases,
  ];
  for (const value of candidates) {
    if (value && String(value).trim()) return String(value).trim();
  }
  return "";
}

function checkMatchesRow(check, row) {
  if (!check || !row) return false;

  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const rowHost = hostOf(row.dataset.serviceUrl);
  const ids = [check.service_id, check.serviceId, check.id]
    .map(normalize)
    .filter(Boolean);
  const names = [check.name, check.display_label]
    .map(normalize)
    .filter(Boolean);
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  const hosts = [check.url, check.tunnel_url, check.tunnelUrl, ...aliases]
    .map(hostOf)
    .filter(Boolean);

  return (
    ids.includes(key) ||
    names.includes(name) ||
    Boolean(rowHost && hosts.includes(rowHost))
  );
}

function findCheck(checks, row) {
  if (!checks || !row) return null;
  const key = row.dataset.serviceKey;
  if (key && checks[key]) return checks[key];
  for (const check of Object.values(checks)) {
    if (checkMatchesRow(check, row)) return check;
  }
  return null;
}

function normalizedPolicy(check) {
  const policy = normalize(check?.policy_status);
  if (["ok", "warn", "fail", "unknown"].includes(policy)) return policy;
  return "unknown";
}

function reachabilityTone(check) {
  if (!check) return "unknown";
  if (check.skipped === true) return "neutral";
  if (check.reachable === false) return "fail";
  if (check.reachable == null) return "unknown";

  const status = Number(check.http_status);
  if (!Number.isFinite(status)) {
    return check.reachable === true ? "ok" : "unknown";
  }
  if (status >= 200 && status < 400) return "ok";
  if (status >= 500) return "fail";
  return "warn";
}

function policyTone(policy) {
  if (policy === "ok") return "ok";
  if (policy === "warn") return "warn";
  if (policy === "fail") return "fail";
  return "unknown";
}

function evidenceMetadata(check) {
  if (!check) return "";
  const parts = [];
  if (check.elapsed_ms != null) parts.push(`latency=${check.elapsed_ms}ms`);
  const age = check.cache_age_seconds ?? check.age_seconds;
  if (age != null) parts.push(`age=${age}s`);
  const cache = check.cache_layer ?? (check.cached === true ? "yes" : null);
  if (cache) parts.push(`cache=${cache}`);
  if (check.stale === true) parts.push("stale");
  if (check.refreshing === true) parts.push("refreshing");
  if (check.confirmed === false || check.unconfirmed === true) {
    parts.push("status=unconfirmed");
  }
  if (check.vantage_point) parts.push(`vantage=${check.vantage_point}`);
  if (check.failure_stage) parts.push(`stage=${check.failure_stage}`);
  if (check.error_kind) parts.push(`error=${check.error_kind}`);
  if (check.credential_mode) parts.push(`credential=${check.credential_mode}`);
  if (check.last_success_at)
    parts.push(`last-success=${check.last_success_at}`);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

function probeBadge(kind, tone, label, detail, evidence = null) {
  const metricsHref =
    kind === "metrics" ? String(evidence?.metrics_url || "").trim() : "";
  const linkedMetrics = /^https?:\/\//i.test(metricsHref);
  const badge = document.createElement(linkedMetrics ? "a" : "span");
  badge.className = `service-probe service-probe--${tone}`;
  badge.dataset.probeKind = kind;
  const description = `${detail || label}${evidenceMetadata(evidence)}`;
  badge.title = description;
  badge.setAttribute("aria-label", description);
  if (linkedMetrics) {
    badge.href = metricsHref;
    badge.target = "_blank";
    badge.rel = "noopener noreferrer";
    badge.style.cursor = "pointer";
    badge.style.textDecoration = "none";
  }

  const icon = document.createElement("span");
  icon.className = "service-probe-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = PROBE_ICONS[kind] || "•";

  const text = document.createElement("span");
  text.className = "service-probe-label";
  text.textContent = label;
  badge.append(icon, text);
  return badge;
}

function httpDetail(check, suffix) {
  if (check.reachable === true) {
    return `HTTP probe reached the target${suffix}`;
  }
  if (check.reachable === false) {
    const error = check.error ? `: ${check.error}` : "";
    return `HTTP probe could not reach the target${error}`;
  }
  const warning = check.warning ? `: ${check.warning}` : "";
  return `HTTP probe result is not confirmed${warning}`;
}

function addHttpEvidence(target, check, kinds) {
  if (!check) return;
  const url = urlOf(check);
  const probe = normalize(check.probe);
  const hasHttp =
    /^https?:\/\//i.test(url) ||
    check.http_status != null ||
    probe.includes("http");
  if (!hasHttp) return;

  const status = Number(check.http_status);
  const label = Number.isFinite(status) ? `HTTP ${status}` : "HTTP";
  const suffix = Number.isFinite(status) ? ` with status ${status}` : "";
  target.appendChild(
    probeBadge(
      "http",
      reachabilityTone(check),
      label,
      httpDetail(check, suffix),
      check,
    ),
  );
  kinds.add("http");
}

function addTlsEvidence(target, check, kinds) {
  if (!check) return;
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  const hasHttps =
    /^https:\/\//i.test(urlOf(check)) ||
    aliases.some((value) => /^https:\/\//i.test(String(value)));
  if (!hasHttps) return;

  let tone = "unknown";
  let detail = "HTTPS target exists but TLS trust was not confirmed";
  if (check.skipped === true) {
    tone = "neutral";
    detail = "TLS validation was intentionally skipped from this vantage point";
  } else if (check.tls_trusted === true) {
    tone = "ok";
    detail = "HTTPS certificate chain and hostname were validated";
  } else if (check.tls_trusted === false) {
    tone = "fail";
    detail = "HTTPS certificate validation failed";
  }

  target.appendChild(probeBadge("tls", tone, "TLS", detail, check));
  kinds.add("tls");
}

function addTcpEvidence(target, check, kinds) {
  if (!check) return;
  const probe = normalize(check.probe);
  const protocol = normalize(check.protocol);
  const url = urlOf(check);
  const hasTcp =
    probe.includes("tcp") ||
    protocol === "tcp" ||
    Boolean(check.host && check.port != null && !/^https?:\/\//i.test(url));
  if (!hasTcp) return;

  const endpoint =
    check.host && check.port != null ? ` ${check.host}:${check.port}` : "";
  const error = check.error ? `: ${check.error}` : "";
  target.appendChild(
    probeBadge(
      "tcp",
      reachabilityTone(check),
      "TCP",
      `TCP connectivity probe${endpoint}${error}`,
      check,
    ),
  );
  kinds.add("tcp");
}

function addApiEvidence(target, key, check, kinds) {
  if (!check) return;
  const probe = normalize(check.probe);
  const path = String(check.path || "");
  const hasApi =
    probe.includes("api") ||
    path.startsWith("/api/") ||
    ["pfsense", "truenas_api"].includes(String(key || ""));
  if (!hasApi) return;

  const detail = `Authenticated/read-only API evidence${path ? ` via ${path}` : ""}`;
  target.appendChild(
    probeBadge("api", reachabilityTone(check), "API", detail, check),
  );
  kinds.add("api");

  const hasWebsocket =
    probe.includes("websocket") || String(key || "") === "truenas_api";
  if (!hasWebsocket) return;
  target.appendChild(
    probeBadge(
      "websocket",
      reachabilityTone(check),
      "WS",
      "WebSocket API connectivity evidence",
      check,
    ),
  );
  kinds.add("websocket");
}

function tunnelEvidence(exposure) {
  const expected = exposure.tunnel_secure === true;
  const observed = exposure.cloudflare_tunnel_observed;
  if (expected && observed === true) {
    return ["ok", "Cloudflare Tunnel is expected and observed"];
  }
  if (expected && observed === false) {
    return ["fail", "Cloudflare Tunnel is expected but was not observed"];
  }
  if (!expected && observed === true) {
    return [
      "warn",
      "Cloudflare Tunnel was observed although direct exposure is declared",
    ];
  }
  if (exposure.tunnel_secure === false) {
    return [
      "neutral",
      "Cloudflare Tunnel is not required by the declared exposure policy",
    ];
  }
  return ["unknown", "Cloudflare Tunnel evidence is not confirmed"];
}

function accessEvidence(exposure) {
  const policyCount = Number(exposure.cloudflare_access_policy_count);
  const hasCount = Number.isFinite(policyCount);
  let tone = "unknown";
  if (exposure.cloudflare_default_deny === true && policyCount > 0) {
    tone = "ok";
  } else if (exposure.cloudflare_default_deny === true && policyCount === 0) {
    tone = "fail";
  } else if (hasCount) {
    tone = policyCount > 0 ? "ok" : "warn";
  }

  const countDetail = hasCount
    ? ` · ${policyCount} ${policyCount === 1 ? "policy" : "policies"}`
    : "";
  return [
    tone,
    `Cloudflare Access Default-Deny=${String(exposure.cloudflare_default_deny)}${countDetail}`,
  ];
}

function addCloudflareEvidence(target, exposure, kinds) {
  if (!exposure) return;
  const hasTunnel =
    exposure.tunnel_secure != null ||
    exposure.cloudflare_tunnel_observed != null ||
    exposure.cloudflare_default_deny != null ||
    exposure.cloudflare_access_policy_count != null;
  if (!hasTunnel) return;

  const [tunnelTone, tunnelDetail] = tunnelEvidence(exposure);
  target.appendChild(
    probeBadge("cloudflare", tunnelTone, "Tunnel", tunnelDetail, exposure),
  );
  kinds.add("cloudflare");

  const hasAccess =
    exposure.cloudflare_default_deny != null ||
    Number.isFinite(Number(exposure.cloudflare_access_policy_count));
  if (hasAccess) {
    const [accessTone, accessDetail] = accessEvidence(exposure);
    target.appendChild(
      probeBadge("access", accessTone, "Access", accessDetail, exposure),
    );
    kinds.add("access");
  }

  if (exposure.cloudflare_service_auth_attempted !== true) return;
  const passed = exposure.cloudflare_service_token_access_passed;
  const httpStatus = Number(exposure.cloudflare_service_token_http_status);
  const statusLabel = Number.isFinite(httpStatus) ? ` ${httpStatus}` : "";
  let tone = "unknown";
  if (passed === true) tone = "ok";
  else if (passed === false) tone = "fail";

  const result =
    passed === true
      ? "authenticated successfully"
      : passed === false
        ? "authentication failed"
        : "result is unknown";
  target.appendChild(
    probeBadge(
      "service-token",
      tone,
      `Token${statusLabel}`,
      `Cloudflare Access Service Token ${result}${statusLabel ? ` · HTTP${statusLabel}` : ""}`,
      exposure,
    ),
  );
  kinds.add("service-token");
}

function metricTone(check) {
  if (!check) return null;
  const values = [
    check.prometheus_up,
    check.metrics_up,
    check.telemetry_available,
    check.metrics_available,
  ];
  if (values.some((value) => value === true)) return "ok";
  if (values.some((value) => value === false)) return "fail";
  const source = normalize(
    [check.source, check.metric_source, check.telemetry_source]
      .filter(Boolean)
      .join(" "),
  );
  return source.includes("prometheus") ? "unknown" : null;
}

function addMetricEvidence(target, check, kinds) {
  const tone = metricTone(check);
  if (!tone) return;

  let detail =
    "Prometheus metrics source is declared but current evidence is unknown";
  if (tone === "ok") detail = "Prometheus metrics endpoint is available";
  else if (tone === "fail") {
    detail = "Prometheus metrics endpoint reports unavailable";
  }
  const metricsStatus = Number(check?.metrics_http_status);
  if (Number.isFinite(metricsStatus)) detail += ` · HTTP ${metricsStatus}`;
  target.appendChild(
    probeBadge("metrics", tone, "Prometheus", detail, check),
  );
  kinds.add("metrics");
}

function setExposureMetadata(row, exposure) {
  if (!exposure) {
    row.dataset.exposurePolicy = "unobserved";
    row.dataset.exposureScope = "unobserved";
    row.dataset.exposureMode = "unobserved";
    return;
  }

  row.dataset.exposurePolicy = normalizedPolicy(exposure);
  if (exposure.external === true) row.dataset.exposureScope = "external";
  else if (exposure.external === false) row.dataset.exposureScope = "internal";
  else row.dataset.exposureScope = "unknown";

  if (exposure.tunnel_secure === true) {
    row.dataset.exposureMode = "cloudflare";
  } else if (exposure.tunnel_secure === false) {
    row.dataset.exposureMode = "direct";
  } else {
    row.dataset.exposureMode = "unknown";
  }
}

function decorateRow(row, snapshot) {
  const healthChecks = snapshot?.healthz?.checks || {};
  const homelabChecks = snapshot?.homelab?.checks || {};
  const sickzChecks = snapshot?.sickz?.checks || {};
  const key = row.dataset.serviceKey || "";
  const health =
    findCheck(healthChecks, row) || findCheck(homelabChecks, row) || null;
  const exposure = findCheck(sickzChecks, row);
  const primary = row.querySelector(".health-row-primary");
  if (!primary) return;

  setExposureMetadata(row, exposure);
  const kinds = new Set();
  const strip = document.createElement("div");
  strip.className = "service-probe-strip";
  strip.setAttribute("aria-label", "Probe evidence");

  const mainEvidence = health || exposure;
  addHttpEvidence(strip, mainEvidence, kinds);
  addTlsEvidence(strip, exposure || mainEvidence, kinds);
  addTcpEvidence(strip, mainEvidence, kinds);
  addApiEvidence(strip, key, mainEvidence, kinds);
  addCloudflareEvidence(strip, exposure, kinds);
  addMetricEvidence(strip, health, kinds);

  if (exposure?.policy_status) {
    const policy = normalizedPolicy(exposure);
    const detail =
      exposure.policy_detail || `Exposure security policy: ${policy}`;
    strip.appendChild(
      probeBadge("policy", policyTone(policy), "Policy", detail, exposure),
    );
  }

  row.dataset.probeKinds = [...kinds].join(" ");
  const signature = strip.textContent + strip.innerHTML;
  const existing = primary.querySelector(":scope > .service-probe-strip");
  if (existing?.dataset.signature === signature) return;
  if (existing) existing.remove();
  strip.dataset.signature = signature;
  if (strip.children.length > 0) primary.appendChild(strip);
}

async function decorateRows() {
  if (decorating) return;
  decorating = true;
  try {
    latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
    if (latestSnapshot) {
      const rows = document.querySelectorAll(
        ".health-row[data-service-filter-target]",
      );
      for (const row of rows) decorateRow(row, latestSnapshot);
    }
    refreshServiceFilter();
  } finally {
    decorating = false;
  }
}

function scheduleRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.requestAnimationFrame(() => {
    refreshScheduled = false;
    decorateRows();
  });
}

export function installServiceDiagnostics() {
  installServiceFilter();
  const board = document.getElementById("health-board");
  if (board) {
    const observer = new MutationObserver(scheduleRefresh);
    observer.observe(board, { childList: true, subtree: true });
  }
  scheduleRefresh();
}
