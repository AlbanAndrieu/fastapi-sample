function normalized(value) {
  return String(value || "").trim().toLowerCase();
}

function nonEmpty(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function probeTone({ errorKind, refreshError, stale = false, enabled = true }) {
  if (!enabled) return "disabled";
  if (nonEmpty(errorKind) || nonEmpty(refreshError)) return "error";
  if (stale) return "stale";
  return "ok";
}

function chip(icon, label, tone, title) {
  const element = document.createElement("span");
  element.className = `service-probe-chip service-probe-chip--${tone}`;
  element.title = title;
  element.setAttribute("aria-label", `${label}. ${title}`);
  const iconElement = document.createElement("span");
  iconElement.className = "service-probe-chip-icon";
  iconElement.setAttribute("aria-hidden", "true");
  iconElement.textContent = icon;
  const labelElement = document.createElement("span");
  labelElement.textContent = label;
  element.append(iconElement, labelElement);
  return element;
}

function containerEvidence(check) {
  const containers = Array.isArray(check?.runtime_containers)
    ? check.runtime_containers
    : [];
  if (containers.length === 0) return null;
  const preferred = containers.find((container) => container?.state || container?.health);
  return preferred || containers[0];
}

function runtimeTone(state, health) {
  const combined = `${normalized(state)} ${normalized(health)}`;
  if (/(failed|stopped|exited|dead|unhealthy|crashed)/.test(combined)) return "error";
  if (/(starting|restarting|created|deploying|initializing)/.test(combined)) return "starting";
  if (/(running|healthy)/.test(combined)) return "ok";
  return "unknown";
}

function decorateRuntime(name, check) {
  name.querySelector(".service-runtime-badge")?.remove();
  const container = containerEvidence(check);
  const state = nonEmpty(container?.state) || nonEmpty(check?.runtime_state);
  const health = nonEmpty(container?.health);
  if (!state && !health) return;

  const badge = document.createElement("span");
  const tone = runtimeTone(state, health);
  badge.className = `service-runtime-badge service-runtime-badge--${tone}`;
  const values = [state, health].filter(Boolean);
  badge.textContent = `▣ ${values.join(" · ")}`;
  badge.title = [
    "TrueNAS app.query runtime evidence",
    check?.runtime_app ? `app ${check.runtime_app}` : "",
    container?.service_name ? `container ${container.service_name}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  badge.setAttribute("aria-label", badge.title || badge.textContent);
  name.appendChild(badge);
}

function publicProbeChip(check) {
  if (!check?.direct_probe_source && !check?.direct_probe_kind && !check?.direct_probe_url)
    return null;
  const stale = check.direct_probe_source === "memory" || check.observation_stale === true;
  const tone = probeTone({
    errorKind: check.direct_probe_error_kind || check.error_kind,
    refreshError: check.direct_probe_refresh_error,
    stale,
  });
  const kind = normalized(check.direct_probe_kind || check.probe_kind);
  const isPublic = kind === "public_https" || Boolean(check.direct_probe_url);
  const label = isPublic ? "Public HTTPS" : kind === "http" ? "HTTP" : "HTTPS";
  const icon = isPublic ? "🌍" : kind === "http" ? "↔️" : "🔗";
  const status = Number(check.http_status);
  const details = [
    isPublic ? "Public URL/tunnel reachability probe" : "HTTP reachability probe",
    Number.isFinite(status) && status > 0 ? `HTTP ${status}` : "",
    check.direct_probe_url || "",
    check.direct_probe_refresh_error || check.direct_probe_error_kind || "",
  ]
    .filter(Boolean)
    .join(" · ");
  return chip(icon, label, tone, details || `${label} probe enabled`);
}

function internalProbeChip(check) {
  if (!check?.internal_probe_source && !check?.internal_probe_kind && !check?.internal_state)
    return null;
  const kind = normalized(check.internal_probe_kind);
  const label = kind === "tcp" || !kind ? "TCP" : kind.toUpperCase();
  const icon = kind === "tcp" || !kind ? "🔌" : "↔️";
  const tone = probeTone({
    errorKind: check.internal_probe_error_kind,
    refreshError: check.internal_probe_refresh_error,
    stale: check.internal_probe_source === "memory" || check.observation_stale === true,
  });
  const details = [
    "LAN/internal probe",
    check.internal_probe_error_kind || check.internal_probe_refresh_error || "",
  ]
    .filter(Boolean)
    .join(" · ");
  return chip(icon, label, tone, details || `${label} probe enabled`);
}

function truenasProbeChip(check) {
  if (check?.runtime_reachable == null && !check?.runtime_state && !check?.runtime_app)
    return null;
  const tone =
    check.runtime_reachable === false
      ? "error"
      : check.runtime_stale === true
        ? "stale"
        : "ok";
  const details = [
    "TrueNAS app.query runtime probe",
    check.runtime_reachable === false ? "API unreachable or runtime query failed" : "API evidence available",
    check.runtime_state ? `app ${check.runtime_state}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return chip("🗄️", "TrueNAS", tone, details);
}

function cloudflareTunnelChip(check) {
  if (!check?.tunnel_status && !check?.tunnel_name) return null;
  const tone = check.tunnel_stale === true ? "stale" : "ok";
  const details = [
    "Cloudflare tunnel control-plane observation",
    check.tunnel_name || "",
    check.tunnel_status ? `reported ${check.tunnel_status}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return chip("☁️", "Tunnel", tone, details);
}

function cloudflareAuthChip(check) {
  if (check?.cloudflare_service_auth_attempted !== true && check?.public_probe_auth_mode !== "cloudflare_service_token")
    return null;
  const authError = nonEmpty(check.cloudflare_service_token_error_kind);
  const passed = check.cloudflare_service_token_access_passed;
  const tone = authError || passed === false ? "error" : "ok";
  const status = Number(check.cloudflare_service_token_http_status);
  const details = [
    "Authenticated Cloudflare Access probe using service-token credentials",
    authError ? `technical error ${authError}` : "",
    passed === false ? "service token did not pass Access" : "",
    Number.isFinite(status) && status > 0 ? `HTTP ${status}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return chip("🔑", "CF token", tone, details);
}

function tlsChip(check) {
  if (typeof check?.tls_trusted !== "boolean") return null;
  return chip(
    "🔒",
    "TLS",
    check.tls_trusted ? "ok" : "error",
    check.tls_trusted
      ? "TLS certificate validation succeeded"
      : "TLS certificate validation failed or could not be trusted",
  );
}

function baseHttpChip(check) {
  if (check?.direct_probe_source || check?.direct_probe_kind || check?.direct_probe_url)
    return null;
  const url = nonEmpty(check?.url);
  const hasHttpEvidence = check?.http_status != null || url?.startsWith("http");
  if (!hasHttpEvidence) return null;
  const https = url?.startsWith("https://") === true;
  const tone = probeTone({ errorKind: check.error_kind, refreshError: check.refresh_error });
  return chip(
    https ? "🔗" : "↔️",
    https ? "HTTPS" : "HTTP",
    tone,
    ["Basic HTTP health probe", check.error_kind || check.refresh_error || ""].filter(Boolean).join(" · "),
  );
}

function pfsenseChip(serviceId, check) {
  if (serviceId !== "pfsense" && serviceId !== "pfsense-api") return null;
  const tone = probeTone({
    errorKind: check?.error_kind,
    refreshError: check?.refresh_error,
    enabled: check?.skipped !== true,
  });
  return chip(
    "🧱",
    "pfSense",
    tone,
    check?.error_kind
      ? `pfSense API probe technical error: ${check.error_kind}`
      : "pfSense API probe channel",
  );
}

const PROMETHEUS_SIGNAL_BY_SERVICE = {
  truenas: ["truenas_node_up", "truenas_cadvisor_up"],
  "truenas-api": ["truenas_node_up", "truenas_cadvisor_up"],
  pfsense: ["pfsense_metrics_up"],
  "pfsense-api": ["pfsense_metrics_up"],
  prometheus: ["prometheus_up"],
};

function prometheusChip(serviceId, platformMetrics) {
  const signalNames = PROMETHEUS_SIGNAL_BY_SERVICE[serviceId];
  if (!signalNames || !platformMetrics) return null;
  const metrics = platformMetrics.metrics || {};
  const configured = platformMetrics.configured !== false;
  const available = platformMetrics.state === "ok" || signalNames.some((name) => metrics[name] != null);
  const tone = !configured ? "disabled" : available ? "ok" : "error";
  const observed = signalNames
    .filter((name) => metrics[name] != null)
    .map((name) => `${name}=${metrics[name]}`)
    .join(", ");
  const details = [
    "Prometheus query channel",
    observed,
    platformMetrics.error || "",
  ]
    .filter(Boolean)
    .join(" · ");
  return chip("📈", "Prom", tone, details || "Prometheus query channel");
}

export function decorateServiceProbeEvidence(
  row,
  check,
  { serviceId = "", platformMetrics = null } = {},
) {
  if (!row || !check) return;
  const name = row.querySelector(".health-row-name");
  if (name) decorateRuntime(name, check);

  const tags = row.querySelector(".health-row-tags");
  if (!tags) return;
  tags.querySelector(".service-probe-strip")?.remove();
  const strip = document.createElement("span");
  strip.className = "service-probe-strip";

  const probes = [
    truenasProbeChip(check),
    pfsenseChip(serviceId, check),
    prometheusChip(serviceId, platformMetrics),
    internalProbeChip(check),
    publicProbeChip(check),
    baseHttpChip(check),
    cloudflareTunnelChip(check),
    cloudflareAuthChip(check),
    tlsChip(check),
  ].filter(Boolean);
  if (probes.length === 0) return;
  strip.append(...probes);
  tags.appendChild(strip);
}
