import { escapeText } from "./api-health-ui.js";
import {
  fetchHomelabHealth,
  fetchHomelabProbeMatrix,
} from "./api-homelab-health.js";

function stageClass(stage) {
  if (stage?.state === "ok") return "ok";
  if (stage?.state === "fail") return "fail";
  return "blocked";
}

function stageIcon(stage) {
  if (stage?.state === "ok") return "●";
  if (stage?.state === "fail") return "💀";
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
  const broken = left?.state !== "ok" || right?.state !== "ok";
  return `<div class="truenas-connector${broken ? " truenas-connector--broken" : ""}" aria-hidden="true"></div>`;
}

function targetText(truenas) {
  const diagnostics = truenas?.diagnostics;
  const configuredTarget =
    diagnostics?.target || truenas?.public?.url || "TrueNAS";
  if (diagnostics?.path_mode === "direct_lan") {
    return `${configuredTarget} · TrueNAS HTTPS listener + TrueNAS API (WebSocket /api/current) · direct LAN`;
  }
  const wan = diagnostics?.wan;
  if (!wan?.ipv4)
    return `${configuredTarget} · TrueNAS HTTPS listener + TrueNAS API (WebSocket /api/current)`;
  const provider = wan?.provider ? ` · ${wan.provider}` : "";
  const addressKind = wan?.static ? " static IPv4" : " IPv4";
  return `${configuredTarget} · public API path via pfSense/HAProxy · ${wan.ipv4}${provider}${addressKind}`;
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
  if (pathMode === "direct_lan") return stages;

  const output = [];
  let inserted = false;
  for (const stage of stages) {
    output.push(stage);
    if (!inserted && stage?.id === "dns") {
      output.push(ingressPolicyStage(data, stages));
      inserted = true;
    }
  }
  if (!inserted) output.unshift(ingressPolicyStage(data, stages));
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
  const internalText =
    internalEnabled === false
      ? "⏸ LAN probes disabled"
      : `● LAN probes enabled · ${internal.scheduled ?? "?"} targets · ${internal.completed ?? 0} completed · ${internal.timed_out ?? 0} deadline`;
  const publicText = `🌐 public probes · ${publicSummary.scheduled ?? "?"} targets · ${publicSummary.completed ?? 0} completed · ${publicSummary.timed_out ?? 0} deadline`;
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

  summary.textContent = `${runtimeMode} · ${httpsMode} · ${apiMode} · ${internalText} · ${publicText} · ${catalog}fan-out budget ${budget}s · concurrency ${concurrency} · ${tlsMode}`;
  detailsSummary.textContent = `Homelab probe fan-out · ${rows.length} observed/scheduled rows`;

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
      const stateText =
        row?.timed_out === true
          ? `deadline · ${row?.error || "fan-out budget exceeded"}`
          : row?.error_kind
            ? `${row.error_kind} · ${row?.error || state}`
            : row?.error || state;
      return (
        `<div class="truenas-probe-row truenas-probe-row--${escapeText(state)}">` +
        `<span class="truenas-probe-name">${escapeText(row?.name || row?.id || "probe")} · ${escapeText(scope)}</span>` +
        `<span class="truenas-probe-target">${escapeText(probeTarget(row, scope))}</span>` +
        `<span class="truenas-probe-state">${escapeText(stateText)}</span>` +
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

function render(data) {
  const truenas = data?.truenas;
  const measuredStages = truenas?.diagnostics?.stages;
  const pipeline = document.getElementById("truenas-pipeline");
  const state = document.getElementById("truenas-platform-state");
  const target = document.getElementById("truenas-platform-target");
  const error = document.getElementById("truenas-platform-error");
  if (!pipeline || !state || !target || !error) return;

  renderProbeFanout(data);
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
  if (ingressBlock?.state === "blocked") {
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
  if (data?._bounded_probe_fallback === true) {
    notes.push(
      "Aggregate homelab diagnostics exceeded their deadline; TrueNAS flow and probe fan-out were recovered from bounded /api/homelab/probes.",
    );
  }
  if (data?._probe_fallback_error) {
    notes.push(`Bounded probe fallback failed: ${data._probe_fallback_error}`);
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
    probe_summary: probes?.probe_summary || aggregate?.probe_summary,
    internal_services:
      probes?.internal_services || aggregate?.internal_services || [],
    public_probe_results:
      probes?.public_probe_results ||
      probes?.services ||
      aggregate?.public_probe_results ||
      [],
    _bounded_probe_fallback: true,
  };
}

export async function loadTrueNas() {
  try {
    const aggregate = await fetchHomelabHealth();
    if (!needsBoundedProbeFallback(aggregate)) {
      render(aggregate);
      return;
    }

    try {
      const probes = await fetchHomelabProbeMatrix();
      render(mergeBoundedProbeFallback(aggregate, probes));
    } catch (probeError) {
      render({
        ...aggregate,
        _probe_fallback_error: String(probeError?.message || probeError),
      });
    }
  } catch (err) {
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
      error.textContent = String(err?.message || err);
    }
  }
}
