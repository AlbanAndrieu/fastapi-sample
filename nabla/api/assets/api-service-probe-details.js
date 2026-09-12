import { fetchHealthBoard } from "./api-health-board.js";

const ROW_SELECTOR = ".health-row[data-service-filter-target]";
const TICK_MS = 1000;

let latestSnapshot = null;
let scheduled = false;

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
    return new URL(String(value), window.location.href).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function checkMatchesRow(check, row) {
  if (!check || !row) return false;
  const key = normalize(row.dataset.serviceKey);
  const name = normalize(row.dataset.serviceName);
  const ids = [check.id, check.service_id, check.serviceId]
    .map(normalize)
    .filter(Boolean);
  if (key && ids.includes(key)) return true;
  const names = [check.name, check.display_label]
    .map(normalize)
    .filter(Boolean);
  if (name && names.includes(name)) return true;
  const rowHost = hostOf(row.dataset.serviceUrl);
  const aliases = Array.isArray(check.aliases_probed)
    ? check.aliases_probed
    : [];
  return [check.url, check.tunnel_url, check.tunnelUrl, ...aliases]
    .map(hostOf)
    .filter(Boolean)
    .includes(rowHost);
}

function findCheck(collection, row) {
  if (!collection) return null;
  const direct = collection[row.dataset.serviceKey];
  if (direct) return direct;
  const values = Array.isArray(collection)
    ? collection
    : Object.values(collection);
  return values.find((check) => checkMatchesRow(check, row)) || null;
}

function observedAt(check) {
  for (const value of [
    check?.probe_observed_at,
    check?.direct_probe_observed_at,
    check?.internal_probe_observed_at,
    check?.observed_at,
    check?.last_success_at,
  ]) {
    if (!value) continue;
    const timestamp = Date.parse(String(value));
    if (Number.isFinite(timestamp)) return timestamp;
  }
  return null;
}

function ageSeconds(check) {
  const timestamp = observedAt(check);
  if (timestamp != null) {
    return Math.max(0, (Date.now() - timestamp) / 1000);
  }
  for (const value of [
    check?.probe_age_seconds,
    check?.direct_probe_age_seconds,
    check?.internal_probe_age_seconds,
    check?.observation_age_seconds,
    check?.cache_age_seconds,
    check?.age_seconds,
  ]) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return Math.max(0, numeric);
  }
  return null;
}

function humanSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return null;
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${minutes.toFixed(minutes < 10 ? 1 : 0)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

function pendingState(check, snapshot) {
  if (check?.refreshing === true || check?.pending === true) return true;
  if (snapshot?.refreshing !== true) return false;
  const interval = Number(check?.probe_interval_seconds);
  const age = ageSeconds(check);
  if (!Number.isFinite(interval) || interval <= 0 || age == null) return true;
  return age >= Math.max(0, interval - 2);
}

function httpStatusMetric(check, key) {
  const value = Number(check?.[key]);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function metricDefinitions(check, snapshot) {
  const elapsed = Number(check?.elapsed_ms ?? check?.latency_ms);
  const dnsElapsed = Number(check?.dns_latency_ms);
  const interval = Number(check?.probe_interval_seconds);
  const age = ageSeconds(check);
  const next =
    Number.isFinite(interval) && interval > 0 && age != null
      ? Math.max(0, interval - age)
      : Number(check?.next_probe_in_seconds);
  const observed = observedAt(check);
  const status = pendingState(check, snapshot)
    ? "PENDING / probing…"
    : check?.stale === true
      ? "STALE"
      : "complete";
  const cache =
    check?.cache_layer ??
    (check?.cached === true
      ? "cached"
      : check?.cached === false
        ? "live"
        : null);

  return [
    ["probe-state", "Probe state", status],
    [
      "http-status",
      "HTTP status",
      Number.isFinite(Number(check?.http_status)) ? check.http_status : null,
    ],
    [
      "anonymous-initial-http",
      "Anonymous initial HTTP",
      httpStatusMetric(check, "anonymous_initial_http_status"),
    ],
    [
      "anonymous-final-http",
      "Anonymous final HTTP",
      httpStatusMetric(check, "anonymous_final_http_status"),
    ],
    [
      "authenticated-http",
      "Authenticated HTTP",
      httpStatusMetric(check, "authenticated_http_status"),
    ],
    [
      "origin-reached",
      "Origin reached",
      typeof check?.origin_reached === "boolean"
        ? String(check.origin_reached)
        : null,
    ],
    ["auth-mode", "Auth mode", check?.public_probe_auth_mode],
    [
      "reachable",
      "Reachable",
      typeof check?.reachable === "boolean" ? String(check.reachable) : null,
    ],
    [
      "tls-trusted",
      "TLS trusted",
      typeof check?.tls_trusted === "boolean"
        ? String(check.tls_trusted)
        : null,
    ],
    [
      "probe-latency",
      "Probe latency",
      Number.isFinite(elapsed) ? `${elapsed} ms` : null,
    ],
    [
      "dns-latency",
      "DNS latency",
      Number.isFinite(dnsElapsed) ? `${dnsElapsed} ms` : null,
    ],
    [
      "last-probe",
      "Last probe",
      observed != null ? new Date(observed).toISOString() : null,
    ],
    ["probe-age", "Probe age", age != null ? `${humanSeconds(age)} ago` : null],
    [
      "cadence",
      "Cadence",
      Number.isFinite(interval) && interval > 0 ? humanSeconds(interval) : null,
    ],
    [
      "next-due",
      "Next due",
      Number.isFinite(next) && next >= 0 ? humanSeconds(next) : null,
    ],
    ["cache", "Cache", cache],
    ["stale", "Stale", check?.stale === true ? "true" : null],
    ["vantage", "Vantage point", check?.vantage_point],
    ["probe", "Probe", check?.probe],
    ["failure-stage", "Failure stage", check?.failure_stage],
    [
      "refresh-error",
      "Refresh error",
      check?.probe_refresh_error ?? check?.refresh_error,
    ],
    ["error-kind", "Error kind", check?.error_kind],
  ];
}

function metricItem(key, label, value) {
  const item = document.createElement("div");
  item.className = "service-detail-metric";
  item.dataset.metricKey = key;
  const term = document.createElement("span");
  term.textContent = label;
  const content = document.createElement("strong");
  const rendered = value == null || value === "" ? "—" : String(value);
  content.textContent = rendered;
  item.classList.toggle("service-detail-metric--empty", rendered === "—");
  item.append(term, content);
  return item;
}

function appendLayer(section, layerKey, label, check, snapshot) {
  if (!check) return false;
  const block = document.createElement("div");
  block.className = "service-detail-relation-block";
  block.dataset.probeLayer = layerKey;
  const heading = document.createElement("strong");
  heading.textContent = label;
  block.appendChild(heading);
  const grid = document.createElement("div");
  grid.className = "service-detail-metrics";
  for (const [key, metricLabel, value] of metricDefinitions(check, snapshot)) {
    grid.appendChild(metricItem(key, metricLabel, value));
  }
  block.appendChild(grid);
  section.appendChild(block);
  return true;
}

function selectedRow() {
  return document.querySelector(`${ROW_SELECTOR}[data-detail-selected="true"]`);
}

function selectedBody() {
  return document
    .getElementById("service-detail-drawer")
    ?.querySelector(".service-detail-body");
}

function renderProbeTiming(snapshot, row, body) {
  body.querySelector("[data-probe-timing-section]")?.remove();
  const section = document.createElement("section");
  section.dataset.probeTimingSection = "true";
  section.dataset.serviceKey = row.dataset.serviceKey || "";
  const heading = document.createElement("h3");
  heading.textContent = "Probe timing & freshness";
  section.appendChild(heading);

  const layers = [
    ["health", "Health probe", findCheck(snapshot?.healthz?.checks, row)],
    ["homelab", "Homelab probe", findCheck(snapshot?.homelab?.services, row)],
    [
      "exposure",
      "Exposure / edge probe",
      findCheck(snapshot?.sickz?.checks, row),
    ],
  ];
  let rendered = false;
  for (const [layerKey, label, check] of layers) {
    rendered =
      appendLayer(section, layerKey, label, check, snapshot) || rendered;
  }

  if (!rendered) {
    const empty = document.createElement("p");
    empty.className = "service-detail-empty";
    empty.textContent =
      "No per-service probe timing evidence is available yet.";
    section.appendChild(empty);
  }
  body.appendChild(section);
}

function providerSummary(section, tone, text) {
  const summary = document.createElement("div");
  summary.className = `service-provider-summary service-provider-summary--${tone}`;
  summary.textContent = text;
  section.appendChild(summary);
}

function providerGroup(section, title) {
  const group = document.createElement("div");
  group.className = "service-provider-group";
  const heading = document.createElement("strong");
  heading.textContent = title;
  group.appendChild(heading);
  section.appendChild(group);
  return group;
}

function providerItem(group, icon, label, detail, tone = "neutral") {
  const item = document.createElement("div");
  item.className = `service-provider-item service-provider-item--${tone}`;
  const marker = document.createElement("span");
  marker.className = "service-provider-item-icon";
  marker.setAttribute("aria-hidden", "true");
  marker.textContent = icon;
  const body = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = label;
  const text = document.createElement("span");
  text.textContent = detail;
  body.append(title, text);
  item.append(marker, body);
  item.title = detail;
  group.appendChild(item);
}

function familyCount(family) {
  const value = Number(family?.total_count ?? family?.result_count);
  return Number.isFinite(value) ? value : null;
}

function tunnelTone(status) {
  const normalized = normalize(status);
  if (["healthy", "active", "up"].includes(normalized)) return ["🟢", "ok"];
  if (normalized === "inactive") return ["⚪", "neutral"];
  if (["degraded", "down"].includes(normalized)) return ["🔴", "fail"];
  return ["◌", "neutral"];
}

function renderCloudflareDiagnostics(section, snapshot) {
  const platform = snapshot?.healthz?.checks?.cloudflare || {};
  const exposure = snapshot?.homelab?.cloudflare || {};
  const confirmed =
    platform.api_reachable === true && platform.status_confirmed === true;
  const tunnelCount = Number(platform.tunnel_count);
  const healthy = Number(platform.healthy_tunnels);
  if (confirmed) {
    providerSummary(
      section,
      platform.state === "warn" ? "warn" : "ok",
      `☁️ Cloudflare API confirmed${Number.isFinite(healthy) && Number.isFinite(tunnelCount) ? ` · ${healthy}/${tunnelCount} tunnels healthy` : ""}`,
    );
  } else {
    const state =
      platform.api_reachable === false
        ? "Cloudflare API unavailable"
        : platform.api_reachable === true
          ? "Cloudflare API reachable · inventory unconfirmed"
          : "Cloudflare API not confirmed";
    providerSummary(section, "neutral", `◌ ${state}`);
  }

  const tunnels = Array.isArray(exposure?.tunnels) ? exposure.tunnels : [];
  if (tunnels.length > 0) {
    const group = providerGroup(section, "Tunnels");
    const managementKinds = new Set(
      tunnels.map((tunnel) => String(tunnel?.management || "unknown")),
    );
    const showManagement =
      managementKinds.size > 1 || !managementKinds.has("cloudflare");
    for (const tunnel of tunnels) {
      const [icon, tone] = tunnelTone(tunnel?.status);
      const ingress = Array.isArray(tunnel?.ingress) ? tunnel.ingress : [];
      const parts = [
        String(tunnel?.status || "unknown"),
        `${ingress.length} public hostname${ingress.length === 1 ? "" : "s"}`,
      ];
      if (showManagement) {
        const management = String(tunnel?.management || "unknown");
        parts.push(
          management === "cloudflare"
            ? "dashboard-managed"
            : `${management}-managed`,
        );
      }
      providerItem(
        group,
        icon,
        String(tunnel?.name || "Unnamed tunnel"),
        parts.join(" · "),
        tone,
      );
    }
  }

  const control = exposure?.control_plane || {};
  const accessGroup = providerGroup(section, "Access & Service Auth");
  const apps =
    familyCount(control.access_applications) ??
    (Array.isArray(exposure?.access_applications)
      ? exposure.access_applications.length
      : null);
  const reusable = familyCount(control.access_reusable_policies);
  const tokens = familyCount(control.access_service_tokens);
  providerItem(
    accessGroup,
    "🛡️",
    "Access applications",
    apps == null ? "inventory not confirmed" : `${apps} application(s) visible`,
    confirmed ? "ok" : "neutral",
  );
  providerItem(
    accessGroup,
    "📜",
    "Reusable policies",
    reusable == null
      ? "inventory not confirmed"
      : `${reusable} policy object(s) visible`,
    confirmed ? "ok" : "neutral",
  );
  const tokenPresent =
    control?.access_service_tokens?.configured_client_id_present;
  const tokenDetail = [
    tokens == null
      ? "inventory not confirmed"
      : `${tokens} Service Token(s) visible`,
    tokenPresent === true
      ? "configured Service Token found"
      : tokenPresent === false
        ? "configured Service Token not found"
        : null,
  ]
    .filter(Boolean)
    .join(" · ");
  providerItem(
    accessGroup,
    "🔑",
    "Service Tokens",
    tokenDetail,
    tokenPresent === false && confirmed
      ? "warn"
      : tokenPresent === true
        ? "ok"
        : "neutral",
  );

  const checks = Object.values(snapshot?.sickz?.checks || {});
  const unresolved = checks.filter(
    (check) =>
      check?.tunnel_secure === true &&
      check?.cloudflare_tunnel_observed !== true,
  ).length;
  if (unresolved > 0 && confirmed) {
    const group = providerGroup(section, "Reconciliation");
    providerItem(
      group,
      "⚠️",
      "Protected hostnames needing review",
      `${unresolved} hostname(s) are not confirmed by the current Tunnel route inventory. This is per-host configuration drift/uncertainty, not a Cloudflare outage.`,
      "warn",
    );
  }
}

function securityControlIcon(filter) {
  const id = normalize(`${filter?.id || ""} ${filter?.label || ""}`);
  if (id.includes("pfblocker")) return "🚫";
  if (id.includes("snort")) return "🛡️";
  if (id.includes("crowdsec")) return "👥";
  if (id.includes("pf") || id.includes("firewall")) return "🧱";
  return "🛡️";
}

function securityControlTone(filter) {
  const state = normalize(filter?.state);
  if (["running", "clear"].includes(state)) return "ok";
  if (state === "blocked") return "fail";
  if (state === "stopped") return "warn";
  return "neutral";
}

function renderPfSenseDiagnostics(section, snapshot) {
  const platform = snapshot?.healthz?.checks?.pfsense || {};
  const dns = snapshot?.homelab?.pfsense?.dns || {};
  const httpStatus = Number(platform.http_status);
  if (platform.reachable === true) {
    providerSummary(
      section,
      "ok",
      `🧱 pfSense REST API reachable${Number.isFinite(httpStatus) ? ` · HTTP ${httpStatus}` : ""}`,
    );
  } else if (platform.reachable === false) {
    providerSummary(
      section,
      "fail",
      `🔴 pfSense REST API failed${platform.error ? ` · ${platform.error}` : ""}`,
    );
  } else {
    providerSummary(
      section,
      "neutral",
      `◌ pfSense REST API not confirmed${platform.warning ? ` · ${platform.warning}` : ""}`,
    );
  }

  const filters = Array.isArray(dns?.security_filters)
    ? dns.security_filters
    : [];
  const controls = providerGroup(section, "Security controls");
  if (filters.length === 0) {
    providerItem(
      controls,
      "◌",
      "Security controls",
      "runtime status inventory is not available",
      "neutral",
    );
  } else {
    for (const filter of filters) {
      const label = String(filter?.label || filter?.id || "Security control");
      const state = String(filter?.state || "unknown");
      const detail = [state, filter?.detail, filter?.evidence]
        .filter(Boolean)
        .join(" · ");
      providerItem(
        controls,
        securityControlIcon(filter),
        label,
        detail || state,
        securityControlTone(filter),
      );
    }
  }

  const telemetry = dns?.ingress_block || {};
  const telemetryGroup = providerGroup(
    section,
    "Snort/PF attribution telemetry",
  );
  const state = String(telemetry?.state || "unknown");
  const timing = [
    telemetry?.error_kind,
    telemetry?.failure_stage ? `stage ${telemetry.failure_stage}` : null,
    telemetry?.attempts != null
      ? `${telemetry.attempts} attempt${telemetry.attempts === 1 ? "" : "s"}`
      : null,
    telemetry?.elapsed_ms != null ? `${telemetry.elapsed_ms} ms` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  if (state === "telemetry_unavailable") {
    providerItem(
      telemetryGroup,
      "◌",
      "snort2c evidence unavailable",
      `${telemetry?.evidence || "The snort2c table could not be queried."}${timing ? ` · ${timing}` : ""} · This does not mean Snort or pfBlockerNG is stopped; component runtime state is shown separately above.`,
      "neutral",
    );
  } else if (state === "telemetry_stale") {
    providerItem(
      telemetryGroup,
      "⚠️",
      "snort2c evidence stale",
      `${telemetry?.evidence || "Last-known-good attribution is retained."}${timing ? ` · ${timing}` : ""}`,
      "warn",
    );
  } else if (state === "blocked") {
    providerItem(
      telemetryGroup,
      "🛑",
      "Ingress block proven",
      telemetry?.evidence ||
        "Observed source matched the pfSense/Snort block table.",
      "fail",
    );
  } else {
    providerItem(
      telemetryGroup,
      "🟢",
      "Attribution telemetry",
      telemetry?.evidence || `state=${state}`,
      state === "clear" ? "ok" : "neutral",
    );
  }
}

function renderProviderDiagnostics(snapshot, row, body) {
  body.querySelector("[data-provider-diagnostics-section]")?.remove();
  const key = String(row.dataset.serviceKey || "");
  if (!["cloudflare", "pfsense"].includes(key)) return;

  const section = document.createElement("section");
  section.dataset.providerDiagnosticsSection = "true";
  const heading = document.createElement("h3");
  heading.textContent =
    key === "cloudflare" ? "Cloudflare diagnostics" : "pfSense diagnostics";
  section.appendChild(heading);
  if (key === "cloudflare") renderCloudflareDiagnostics(section, snapshot);
  else renderPfSenseDiagnostics(section, snapshot);
  body.appendChild(section);
}

function renderSelected(snapshot) {
  const row = selectedRow();
  const body = selectedBody();
  if (!row || !body) return;
  renderProbeTiming(snapshot, row, body);
  renderProviderDiagnostics(snapshot, row, body);
}

function dynamicCheckForLayer(snapshot, row, layerKey) {
  if (layerKey === "health") return findCheck(snapshot?.healthz?.checks, row);
  if (layerKey === "homelab")
    return findCheck(snapshot?.homelab?.services, row);
  if (layerKey === "exposure") return findCheck(snapshot?.sickz?.checks, row);
  return null;
}

function refreshDynamicTiming() {
  const row = selectedRow();
  const section = document.querySelector("[data-probe-timing-section]");
  if (!row || !section || !latestSnapshot) return;
  for (const block of section.querySelectorAll("[data-probe-layer]")) {
    const check = dynamicCheckForLayer(
      latestSnapshot,
      row,
      block.dataset.probeLayer,
    );
    if (!check) continue;
    const values = new Map(
      metricDefinitions(check, latestSnapshot).map(([key, , value]) => [
        key,
        value,
      ]),
    );
    for (const key of ["probe-state", "probe-age", "next-due"]) {
      const item = block.querySelector(`[data-metric-key="${key}"]`);
      const content = item?.querySelector("strong");
      if (!item || !content) continue;
      const value = values.get(key);
      const rendered = value == null || value === "" ? "—" : String(value);
      content.textContent = rendered;
      item.classList.toggle("service-detail-metric--empty", rendered === "—");
    }
  }
}

function scheduleRender() {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(() => {
    scheduled = false;
    if (latestSnapshot) renderSelected(latestSnapshot);
  });
}

async function refreshSnapshot() {
  latestSnapshot = await fetchHealthBoard().catch(() => latestSnapshot);
  scheduleRender();
}

export function installServiceProbeDetails() {
  document.addEventListener(
    "click",
    (event) => {
      const trigger =
        event.target instanceof Element
          ? event.target.closest(".service-detail-trigger")
          : null;
      if (!trigger) return;
      window.setTimeout(() => {
        if (latestSnapshot) scheduleRender();
        else refreshSnapshot();
      }, 0);
    },
    true,
  );
  document.addEventListener("health-board-refreshed", refreshSnapshot);
  refreshSnapshot();
  window.setInterval(refreshDynamicTiming, TICK_MS);
}
