import { escapeText } from "./api-health-ui.js";
import {
  fetchHomelabHealth,
  fetchHomelabProbeMatrix,
} from "./api-homelab-health.js";

function stageClass(stage) {
  if (stage?.state === "ok") return "ok";
  if (stage?.state === "fail") return "fail";
  if (stage?.state === "warn") return "warn";
  return "blocked";
}

function stageIcon(stage) {
  if (stage?.state === "ok") return "●";
  if (stage?.state === "fail") return "💀";
  if (stage?.state === "warn") return "⚠";
  return "⊘";
}

function stageTime(stage) {
  return stage?.elapsed_ms != null ? `${stage.elapsed_ms} ms` : "—";
}

function renderStage(stage) {
  const cls = stageClass(stage);
  return (
    `<div class="truenas-stage truenas-stage--${cls}" title="${escapeText(stage?.detail || "")}">` +
    `<span class="truenas-stage-icon" aria-hidden="true">${stageIcon(stage)}</span>` +
    `<span class="truenas-stage-label">${escapeText(stage?.label || stage?.id || "stage")}</span>` +
    `<span class="truenas-stage-time">${escapeText(stageTime(stage))}</span>` +
    `<span class="truenas-stage-detail">${escapeText(stage?.detail || "")}</span>` +
    `</div>`
  );
}

function renderConnector(left, right) {
  const broken = [left?.state, right?.state].some((state) => state === "fail" || state === "blocked");
  return `<div class="truenas-connector${broken ? " truenas-connector--broken" : ""}" aria-hidden="true"></div>`;
}

function normalizedTarget(value) {
  const target = String(value || "").trim();
  if (!target) return "";
  return /^https?:\/\//i.test(target) ? target : `https://${target}`;
}

function dnsResolved(diagnostics) {
  const dns = Array.isArray(diagnostics?.stages)
    ? diagnostics.stages.find((stage) => stage?.id === "dns")
    : null;
  return Array.isArray(dns?.resolved) ? dns.resolved.filter(Boolean) : [];
}

function targetText(truenas) {
  const diagnostics = truenas?.diagnostics;
  const configuredTarget = normalizedTarget(
    diagnostics?.target || truenas?.public?.url || "TrueNAS",
  );
  const resolved = dnsResolved(diagnostics);
  const resolution = resolved.length ? ` → ${resolved.join(", ")}` : "";
  if (diagnostics?.path_mode === "direct_lan") {
    return `${configuredTarget}${resolution} · direct LAN / runtime host resolution · hostname retained for TLS/SNI`;
  }
  const wan = diagnostics?.wan;
  if (!wan?.ipv4)
    return `${configuredTarget}${resolution} · TrueNAS HTTPS listener + TrueNAS API (WebSocket /api/current)`;
  const provider = wan?.provider ? ` · ${wan.provider}` : "";
  const addressKind = wan?.static ? " static IPv4" : " IPv4";
  return `${configuredTarget}${resolution} · public API path via pfSense/HAProxy · ${wan.ipv4}${provider}${addressKind}`;
}

function targetStage(data, measuredStages) {
  const diagnostics = data?.truenas?.diagnostics || {};
  const configuredTarget = normalizedTarget(
    diagnostics?.target || data?.truenas?.public?.url || "",
  );
  const dns = measuredStages.find((stage) => stage?.id === "dns");
  const resolved = Array.isArray(dns?.resolved) ? dns.resolved.filter(Boolean) : [];
  const direct = diagnostics?.path_mode === "direct_lan";
  return {
    id: "target_url",
    label: "TrueNAS target URL",
    state: configuredTarget ? (dns?.state === "fail" ? "fail" : "ok") : "warn",
    detail: [
      configuredTarget || "target not configured",
      resolved.length ? `resolved ${resolved.join(", ")}` : "resolution not confirmed",
      direct
        ? "direct LAN/runtime host resolution; no Cloudflare DNS or pfSense WAN hop"
        : "public WAN path",
    ].join(" · "),
  };
}

function pfsenseControlStage(data) {
  const posture = data?.pfsense?.dns || {};
  const services = Array.isArray(posture?.services) ? posture.services : [];
  const resolver = posture?.resolver || {};
  const serviceSummary = services
    .slice(0, 8)
    .map((row) => `${row?.identity || "service"} ${row?.runtime_state || "unknown"}`)
    .join(", ");
  const hasPolicyEvidence =
    posture?.policy_state && posture.policy_state !== "unknown";
  const state =
    posture?.reachable === true
      ? "ok"
      : hasPolicyEvidence || services.length > 0 || resolver?.running != null
        ? "warn"
        : "warn";
  const liveness =
    posture?.reachable === true
      ? "API liveness reachable"
      : posture?.reachable === false
        ? `API liveness failed${posture?.error ? `: ${posture.error}` : ""}`
        : "API liveness not confirmed";
  const unbound =
    resolver?.running === true
      ? "Unbound running"
      : resolver?.running === false
        ? "Unbound stopped"
        : "Unbound unknown";
  return {
    id: "pfsense_lan_control",
    label: "pfSense LAN control + DNS",
    state,
    detail: [
      posture?.target || "pfSense target unavailable",
      liveness,
      unbound,
      serviceSummary,
      "out of path for direct TrueNAS LAN traffic",
    ]
      .filter(Boolean)
      .join(" · "),
  };
}

function cloudflareTunnelStage(data) {
  const rows = Array.isArray(data?.services) ? data.services : [];
  const truenas = rows.find((row) => {
    const id = String(row?.id || "").toLowerCase();
    const name = String(row?.name || "").toLowerCase();
    return id === "truenas" || name === "truenas";
  });
  const status = String(truenas?.tunnel_status || "").trim();
  const normalized = status.toUpperCase();
  const healthy = ["HEALTHY", "ACTIVE", "UP", "CONNECTED", "RUNNING"].includes(normalized);
  const down = ["DOWN", "INACTIVE", "STOPPED", "FAILED", "UNHEALTHY"].includes(normalized);
  const stale = truenas?.tunnel_stale === true;
  return {
    id: "cloudflare_tunnel",
    label: "Cloudflare Tunnel",
    state: stale || !status ? "warn" : healthy ? "ok" : down ? "fail" : "warn",
    detail: !status
      ? "Cloudflare tunnel status not confirmed; optional observation, no TrueNAS downgrade"
      : `${truenas?.tunnel_name || "tunnel"} · ${status}${stale ? " · stale" : ""}${data?.truenas?.diagnostics?.path_mode === "direct_lan" ? " · out of path for direct LAN" : ""}`,
  };
}


function filterIcon(filter) {
  if (filter?.state === "blocked") return "💀";
  if (filter?.state === "running" || filter?.state === "clear") return "●";
  if (filter?.state === "in_path" || filter?.state === "observed") return "◐";
  if (filter?.state === "stopped") return "○";
  return "?";
}

function ingressPolicyStage(data, measuredStages) {
  const block = data?.pfsense?.dns?.ingress_block;
  const filters = data?.pfsense?.dns?.security_filters;
  const tcp = measuredStages.find((stage) => stage?.id === "socket");
  const filterRows = Array.isArray(filters) ? filters : [];
  const details = filterRows.map((filter) => {
    const label = filter?.label || filter?.id || "filter";
    const state = filter?.state || "unknown";
    return `${filterIcon(filter)} ${label} ${state}`;
  });

  let state = "blocked";
  if (block?.state === "blocked") state = "fail";
  else if (tcp?.state === "ok") state = "ok";

  return {
    id: "pfsense_wan_ingress",
    label: "pfSense WAN ingress",
    state,
    detail: details.length
      ? details.join(" · ")
      : "PF policy path · security-engine telemetry unavailable",
  };
}

function trafficStages(data, stages) {
  const pathMode = data?.truenas?.diagnostics?.path_mode;
  const output = [targetStage(data, stages)];
  if (pathMode === "direct_lan") {
    output.push(...stages);
    output.push(pfsenseControlStage(data));
    output.push(cloudflareTunnelStage(data));
    return output;
  }

  let inserted = false;
  for (const stage of stages) {
    output.push(stage);
    if (!inserted && stage?.id === "dns") {
      output.push(ingressPolicyStage(data, stages));
      inserted = true;
    }
  }
  if (!inserted) output.splice(1, 0, ingressPolicyStage(data, stages));
  output.push(cloudflareTunnelStage(data));
  return output;
}


function ensureIngressBlock(target) {
  let container = document.getElementById("truenas-ingress-block");
  if (container || !target) return container;
  container = document.createElement("div");
  container.id = "truenas-ingress-block";
  container.className = "truenas-ingress-block";
  target.insertAdjacentElement("afterend", container);
  return container;
}

function endpointText(endpoint) {
  if (!endpoint?.ip) return endpoint?.role || "unknown endpoint";
  const port = endpoint?.port != null ? `:${endpoint.port}` : "";
  const role = endpoint?.role ? ` (${endpoint.role})` : "";
  return `${endpoint.ip}${port}${role}`;
}

function telemetryTiming(block) {
  const values = [];
  if (block?.error_kind) values.push(block.error_kind);
  if (block?.failure_stage) values.push(`stage ${block.failure_stage}`);
  if (block?.attempts != null)
    values.push(`${block.attempts} attempt${block.attempts === 1 ? "" : "s"}`);
  if (block?.elapsed_ms != null) values.push(`${block.elapsed_ms} ms`);
  if (block?.last_success_at)
    values.push(`last success ${block.last_success_at}`);
  return values.join(" · ");
}

function renderIngressBlock(data, target) {
  const container = ensureIngressBlock(target);
  if (!container) return;
  const block = data?.pfsense?.dns?.ingress_block;
  const controlPath = block?.control_path;
  if (data?.truenas?.diagnostics?.path_mode === "direct_lan") {
    container.hidden = true;
    container.innerHTML = "";
    container.className = "truenas-ingress-block";
    return;
  }

  if (block?.state === "telemetry_unavailable") {
    const evidence = escapeText(block?.evidence || "snort2c cannot be queried");
    const timing = escapeText(telemetryTiming(block));
    const path = escapeText(controlPath?.mode || "unknown");
    const independence =
      controlPath?.blind_spot === true
        ? "shared WAN · not independent"
        : "independent or application-level failure";
    container.className =
      "truenas-ingress-block truenas-ingress-block--warning";
    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ pfSense security telemetry temporarily unavailable</strong>" +
      `<span>${evidence}</span>` +
      (timing ? `<span>${timing}</span>` : "") +
      `<span>Control path: ${path} · ${escapeText(independence)}</span>`;
    return;
  }

  if (block?.state === "telemetry_stale") {
    const evidence = escapeText(
      block?.evidence || "Last-known-good snort2c table retained",
    );
    const timing = escapeText(telemetryTiming(block));
    const match =
      block?.last_known_match === true
        ? "Observed egress was present in the stale table; current attribution is withheld."
        : "No current clear/blocked verdict is emitted from stale data.";
    container.className =
      "truenas-ingress-block truenas-ingress-block--warning";
    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ Snort telemetry stale · last-known-good table retained</strong>" +
      `<span>${evidence}</span>` +
      (timing ? `<span>${timing}</span>` : "") +
      `<span>${escapeText(match)}</span>`;
    return;
  }

  if (block?.state === "attribution_unavailable") {
    container.className =
      "truenas-ingress-block truenas-ingress-block--warning";
    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ Snort telemetry available · egress attribution unavailable</strong>" +
      `<span>${escapeText(block?.evidence || "Runtime public egress IP was not observed")}</span>`;
    return;
  }

  if (block?.state !== "blocked") {
    container.hidden = true;
    container.innerHTML = "";
    container.className = "truenas-ingress-block";
    return;
  }

  const engine = escapeText(block?.engine || "filter");
  const firewall = escapeText(block?.firewall || "firewall");
  const mechanism = escapeText(block?.mechanism || "filter table");
  const source = escapeText(endpointText(block?.source));
  const destination = escapeText(endpointText(block?.destination));
  const evidence = escapeText(block?.evidence || "");
  container.className = "truenas-ingress-block";
  container.hidden = false;
  container.innerHTML =
    `<strong>💀 Ingress blocked by ${engine} → ${firewall}</strong>` +
    `<span>${source} → ${destination}</span>` +
    `<span>Evidence: ${mechanism} · ${evidence}</span>`;
}

function apiFailureState(api) {
  const stale = api?.stale === true ? " · stale last-good available" : "";
  if (api?.stage === "source_allowlist")
    return `source IP blocked by TrueNAS allowlist${stale}`;
  if (api?.stage === "access_denied")
    return `TrueNAS API access denied after connection${stale}`;
  if (api?.stage === "connection_reset") return `API connection reset${stale}`;
  if (api?.stage === "tls_handshake_timeout")
    return `TLS handshake timeout${stale}`;
  if (api?.stage === "api_call_timeout") return `API call timeout${stale}`;
  if (api?.stage === "connect_timeout") return `API connect timeout${stale}`;
  if (api?.stage === "tls_error") return `TLS error${stale}`;
  return null;
}

function probeTarget(row, scope) {
  if (scope === "internal") {
    return row?.host && row?.port != null
      ? `${row.host}:${row.port}`
      : "internal target unavailable";
  }
  return row?.url || "public target unavailable";
}

function probeSeverity(row) {
  if (row?.timed_out === true) return 0;
  if (row?.state === "fail") return 1;
  if (row?.state === "warn") return 2;
  return 3;
}

function probeRows(data) {
  const internal = Array.isArray(data?.internal_services)
    ? data.internal_services.map((row) => ({ ...row, probe_scope: "internal" }))
    : [];
  const publicRows = Array.isArray(data?.public_probe_results)
    ? data.public_probe_results.map((row) => ({
        ...row,
        probe_scope: "public",
      }))
    : [];
  return [...internal, ...publicRows].sort((left, right) => {
    const severity = probeSeverity(left) - probeSeverity(right);
    if (severity !== 0) return severity;
    return Number(right?.latency_ms || 0) - Number(left?.latency_ms || 0);
  });
}

function probeFreshnessText(data) {
  const cache = data?.probe_cache || {};
  const source = cache.source;
  const age = Number(cache.age_seconds);
  const checkedAt = data?.checked_at;
  const parts = [];

  if (source === "origin") parts.push("🟢 probes from origin");
  else if (source === "memory") parts.push("🧊 probes from memory cache");
  else parts.push("◌ probe source unknown");

  if (Number.isFinite(age)) parts.push(`${Math.round(age)}s old`);
  if (checkedAt) parts.push(`checked ${String(checkedAt)}`);
  if (cache.stale === true) parts.push("stale");
  return parts.join(" · ");
}

function renderProbeFanout(data) {
  const summary = document.getElementById("truenas-probe-summary");
  const detailsSummary = document.getElementById(
    "truenas-probe-details-summary",
  );
  const list = document.getElementById("truenas-probe-list");
  if (!summary || !detailsSummary || !list) return;

  const probeSummary = data?.probe_summary || {};
  const internal = probeSummary.internal || {};
  const publicSummary = probeSummary.public || {};
  const rows = probeRows(data);
  const catalogCount = probeSummary.catalog_service_count;

  const internalEnabled =
    data?.internal_probes_enabled ?? internal.enabled ?? false;
  const internalEligible = internal.eligible ?? internal.scheduled ?? "?";
  const internalSampled = internal.sampled ?? internal.scheduled ?? 0;
  const publicEligible =
    publicSummary.eligible ?? publicSummary.scheduled ?? "?";
  const publicSampled = publicSummary.sampled ?? publicSummary.scheduled ?? 0;
  const internalEvidence = internal.evidence || {};
  const publicEvidence = publicSummary.evidence || {};
  const internalCoverage =
    internalEvidence.known != null
      ? ` · evidence ${internalEvidence.known}/${internalEligible} (${internalEvidence.fresh ?? 0} fresh · ${internalEvidence.cached ?? 0} cached)`
      : "";
  const publicCoverage =
    publicEvidence.known != null
      ? ` · evidence ${publicEvidence.known}/${publicEligible} (${publicEvidence.fresh ?? 0} fresh · ${publicEvidence.cached ?? 0} cached)`
      : "";
  const internalText =
    internalEnabled === false
      ? `⏸ LAN probes disabled · 0/${internalEligible} sampled`
      : `● LAN probes enabled · ${internalSampled}/${internalEligible} sampled · ${internal.completed ?? 0} completed · ${internal.timed_out ?? 0} deadline${internalCoverage}`;
  const publicText = `🌐 public probes · ${publicSampled}/${publicEligible} sampled · ${publicSummary.completed ?? 0} completed · ${publicSummary.timed_out ?? 0} deadline${publicCoverage}`;
  const budget =
    internal.budget_seconds ?? publicSummary.budget_seconds ?? "unknown";
  const concurrency =
    internal.max_concurrency ?? publicSummary.max_concurrency ?? "unknown";
  const catalog =
    catalogCount != null ? `declared service catalog ${catalogCount} · ` : "";
  const pathMode = data?.truenas?.diagnostics?.path_mode;
  const runtimeMode =
    pathMode === "direct_lan" ? "🏠 local/direct LAN" : "☁ external/public WAN";
  const verifySsl = data?.truenas?.verify_ssl;
  const tlsMode =
    verifySsl === true
      ? "🔐 TLS verify on"
      : verifySsl === false
        ? "⚠ TLS verify off"
        : "🔐 TLS verify unknown";
  const api = data?.truenas?.api || {};
  const appInventoryCount = Array.isArray(api?.apps) ? api.apps.length : null;
  const appInventory =
    appInventoryCount != null
      ? ` · TrueNAS app inventory ${appInventoryCount}`
      : "";
  const apiMode =
    api.reachable === true
      ? `🔌 TrueNAS API healthy${api.version ? ` · ${api.version}` : ""}${appInventory}`
      : api.reachable === false
        ? `⚠ TrueNAS API ${api.stage || "unreachable"}`
        : "◌ TrueNAS API not measured";
  const https = data?.truenas?.public || {};
  const httpsMode =
    https.reachable === true
      ? `🔒 TrueNAS HTTPS HTTP ${https.http_status ?? "?"}`
      : https.reachable === false
        ? "⚠ TrueNAS HTTPS unreachable"
        : "◌ TrueNAS HTTPS not measured";

  const freshness = probeFreshnessText(data);
  summary.textContent = `${freshness} · ${runtimeMode} · ${httpsMode} · ${apiMode} · ${internalText} · ${publicText} · ${catalog}fan-out budget ${budget}s · concurrency ${concurrency} · ${tlsMode}`;
  detailsSummary.textContent = `Homelab probe fan-out · ${rows.length} observed rows · LAN ${internalSampled}/${internalEligible} · public ${publicSampled}/${publicEligible}`;

  list.innerHTML = rows
    .map((row) => {
      const state = row?.timed_out === true ? "warn" : row?.state || "warn";
      const scope = row?.probe_scope || "unknown";
      const latency =
        row?.latency_ms != null
          ? `${row.latency_ms} ms`
          : row?.timed_out === true
            ? "deadline"
            : "—";
      const source = row?.probe_source;
      const age = Number(row?.probe_age_seconds);
      const provenance =
        source === "memory"
          ? `cache${Number.isFinite(age) ? ` ${Math.round(age)}s` : ""}`
          : source === "origin"
            ? "fresh"
            : source === "deadline"
              ? "deadline"
              : "";
      const stateText =
        row?.timed_out === true
          ? `deadline · ${row?.error || "fan-out budget exceeded"}`
          : row?.error_kind
            ? `${row.error_kind} · ${row?.error || state}`
            : row?.error || state;
      const stateWithProvenance = [stateText, provenance]
        .filter(Boolean)
        .join(" · ");
      return (
        `<div class="truenas-probe-row truenas-probe-row--${escapeText(state)}">` +
        `<span class="truenas-probe-name">${escapeText(row?.name || row?.id || "probe")} · ${escapeText(scope)}</span>` +
        `<span class="truenas-probe-target">${escapeText(probeTarget(row, scope))}</span>` +
        `<span class="truenas-probe-state">${escapeText(stateWithProvenance)}</span>` +
        `<span class="truenas-probe-latency">${escapeText(latency)}</span>` +
        "</div>"
      );
    })
    .join("");
}

function diagnosticsUnavailable(data, truenas) {
  const diagnostics = truenas?.diagnostics;
  if (data?.timed_out === true || diagnostics?.error_kind === "deadline") {
    return {
      state: "homelab diagnostics timeout",
      detail:
        diagnostics?.detail ||
        data?.error ||
        "aggregate homelab diagnostic deadline exceeded",
    };
  }
  return {
    state: "diagnostics unavailable",
    detail: "TrueNAS diagnostics are missing from /api/homelab/health.",
  };
}

function pfsenseServiceTone(state) {
  const value = String(state || "").toLowerCase();
  if (["running", "up", "active", "healthy"].includes(value)) return "ok";
  if (["stopped", "down", "failed", "unhealthy"].includes(value)) return "fail";
  return "warn";
}

function ensurePfsenseServices(pipeline) {
  let container = document.getElementById("truenas-pfsense-services");
  if (container || !pipeline) return container;
  container = document.createElement("div");
  container.id = "truenas-pfsense-services";
  container.className = "truenas-pfsense-services";
  pipeline.insertAdjacentElement("afterend", container);
  return container;
}

function renderPfsenseServices(data, pipeline) {
  const container = ensurePfsenseServices(pipeline);
  if (!container) return;
  const posture = data?.pfsense?.dns || {};
  const services = Array.isArray(posture?.services) ? posture.services : [];
  const resolver = posture?.resolver || {};
  const rows = [...services];
  if (!rows.some((row) => String(row?.identity || "").toLowerCase().includes("unbound"))) {
    rows.unshift({
      identity: "Unbound / DNS Resolver",
      runtime_state:
        resolver?.running === true
          ? "running"
          : resolver?.running === false
            ? "stopped"
            : "unknown",
    });
  }
  if (rows.length === 0 && posture?.configured !== true) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  container.hidden = false;
  const chips = rows
    .map((row) => {
      const value = row?.runtime_state || "unknown";
      const tone = pfsenseServiceTone(value);
      return `<span class="truenas-pfsense-service truenas-pfsense-service--${tone}">${escapeText(row?.identity || "service")} · ${escapeText(value)}</span>`;
    })
    .join("");
  const warning = posture?.warning || posture?.error;
  container.innerHTML =
    `<strong>🧱 pfSense services / DNS</strong>` +
    `<div class="truenas-pfsense-service-list">${chips}</div>` +
    (warning ? `<span class="truenas-pfsense-service-warning">⚠ ${escapeText(warning)}</span>` : "");
}

function render(data) {
  const truenas = data?.truenas;
  const measuredStages = truenas?.diagnostics?.stages;
  const pipeline = document.getElementById("truenas-pipeline");
  const state = document.getElementById("truenas-platform-state");
  const target = document.getElementById("truenas-platform-target");
  const error = document.getElementById("truenas-platform-error");
  if (!pipeline || !state || !target || !error) return;

  renderProbeFanout(data);
  renderPfsenseServices(data, pipeline);
  error.hidden = true;
  error.textContent = "";
  target.textContent = targetText(truenas);
  renderIngressBlock(data, target);

  if (!Array.isArray(measuredStages) || measuredStages.length === 0) {
    const unavailable = diagnosticsUnavailable(data, truenas);
    pipeline.innerHTML = "";
    state.className = "truenas-platform-state truenas-platform-state--fail";
    state.textContent = unavailable.state;
    error.hidden = false;
    error.textContent = unavailable.detail;
    return;
  }

  const stages = trafficStages(data, measuredStages);
  let html = "";
  stages.forEach((stage, index) => {
    if (index > 0) html += renderConnector(stages[index - 1], stage);
    html += renderStage(stage);
  });
  pipeline.innerHTML = html;

  const ingressBlock = data?.pfsense?.dns?.ingress_block;
  const overall = truenas?.state || "fail";
  const api = truenas?.api || {};
  const runtimeError = data?.truenas_runtime_error;
  const ingressIsInline = truenas?.diagnostics?.path_mode !== "direct_lan";
  if (ingressIsInline && ingressBlock?.state === "blocked") {
    state.className = "truenas-platform-state truenas-platform-state--fail";
    state.textContent = "blocked by Snort/PF";
  } else {
    state.className = `truenas-platform-state truenas-platform-state--${overall}`;
    const failureState = apiFailureState(api);
    if (api.stage === "missing_api_key") {
      state.textContent = "authentication blocked · API key missing";
    } else if (api.stage === "invalid_api_key_reference") {
      state.textContent = "authentication failed · invalid secret reference";
    } else if (failureState) {
      state.textContent = failureState;
    } else if (api.reachable === true) {
      const version = api.version ? ` · ${api.version}` : "";
      const cached = api.cached === true ? " · cached" : "";
      const platform = overall === "ok" ? "" : ` · platform ${overall}`;
      state.textContent = `TrueNAS API healthy${version}${cached}${platform}`;
    } else {
      state.textContent = overall;
    }
  }

  const notes = [];
  if (data?._probe_first === true) {
    notes.push(
      "TrueNAS flow rendered from bounded /api/homelab/probes first; aggregate health enriches the view when available.",
    );
  }
  if (data?._bounded_probe_fallback === true) {
    notes.push(
      "Aggregate homelab diagnostics exceeded their deadline; TrueNAS flow and probe fan-out were recovered from bounded /api/homelab/probes.",
    );
  }
  if (data?._probe_fallback_error) {
    notes.push(`Bounded probe fallback failed: ${data._probe_fallback_error}`);
  }
  if (data?._aggregate_enrichment_error) {
    notes.push(
      `Aggregate enrichment unavailable: ${data._aggregate_enrichment_error}`,
    );
  }
  if (runtimeError) {
    notes.push(`TrueNAS runtime: ${String(runtimeError)}`);
  } else if (api.stage === "source_allowlist") {
    notes.push(
      `TrueNAS connection: ${String(api.error || "source IP is not allowlisted")} · verify System → Advanced Settings → Allowed IP Addresses for the observer source IP.`,
    );
  } else if (api.stage === "access_denied") {
    notes.push(
      `TrueNAS API authorization: ${String(api.error || "authenticated identity lacks permission")} · connection/authentication succeeded far enough to distinguish this from the HTTPS listener and source allowlist.`,
    );
  }
  if (notes.length > 0) {
    error.hidden = false;
    error.textContent = notes.join(" · ");
  }
}

function needsBoundedProbeFallback(data) {
  const stages = data?.truenas?.diagnostics?.stages;
  return (
    data?.timed_out === true ||
    !Array.isArray(stages) ||
    stages.length === 0 ||
    !data?.probe_summary
  );
}

function mergeBoundedProbeFallback(aggregate, probes) {
  return {
    ...aggregate,
    truenas: probes?.truenas || aggregate?.truenas,
    checked_at: probes?.checked_at || aggregate?.checked_at,
    refresh_elapsed_ms:
      probes?.refresh_elapsed_ms ?? aggregate?.refresh_elapsed_ms,
    probe_cache: probes?.probe_cache || aggregate?.probe_cache,
    probe_summary: probes?.probe_summary || aggregate?.probe_summary,
    pfsense:
      aggregate?.pfsense?.dns != null
        ? aggregate.pfsense
        : probes?.pfsense || aggregate?.pfsense,
    internal_services:
      probes?.internal_services || aggregate?.internal_services || [],
    public_probe_results:
      probes?.public_probe_results ||
      probes?.services ||
      aggregate?.public_probe_results ||
      [],
    _probe_first: true,
    _bounded_probe_fallback: needsBoundedProbeFallback(aggregate),
  };
}

function renderFetchFailure(errorValue) {
  const state = document.getElementById("truenas-platform-state");
  const error = document.getElementById("truenas-platform-error");
  const pipeline = document.getElementById("truenas-pipeline");
  if (state) {
    state.className = "truenas-platform-state truenas-platform-state--fail";
    state.textContent = "health fetch failed";
  }
  if (pipeline) pipeline.innerHTML = "";
  if (error) {
    error.hidden = false;
    error.textContent = String(errorValue?.message || errorValue);
  }
}

export async function loadTrueNas() {
  let probes = null;
  let probeError = null;

  try {
    probes = await fetchHomelabProbeMatrix();
    render({
      ...probes,
      _probe_first: true,
    });
  } catch (err) {
    probeError = err;
  }

  try {
    const aggregate = await fetchHomelabHealth();
    if (probes) {
      render(mergeBoundedProbeFallback(aggregate, probes));
      return;
    }
    render({
      ...aggregate,
      _probe_fallback_error: probeError
        ? String(probeError?.message || probeError)
        : null,
    });
  } catch (aggregateError) {
    if (probes) {
      render({
        ...probes,
        _probe_first: true,
        _aggregate_enrichment_error: String(
          aggregateError?.message || aggregateError,
        ),
      });
      return;
    }
    renderFetchFailure(aggregateError);
  }
}
