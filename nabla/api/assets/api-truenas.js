import { fetchHomelabHealth } from "./api-homelab-health.js";
import { escapeText } from "./api-health-ui.js";

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
  return `<div class="truenas-stage truenas-stage--${cls}" title="${escapeText(stage?.detail || "")}">` +
    `<span class="truenas-stage-icon" aria-hidden="true">${stageIcon(stage)}</span>` +
    `<span class="truenas-stage-label">${escapeText(stage?.label || stage?.id || "stage")}</span>` +
    `<span class="truenas-stage-time">${escapeText(stageTime(stage))}</span>` +
    `<span class="truenas-stage-detail">${escapeText(stage?.detail || "")}</span>` +
    `</div>`;
}

function renderConnector(left, right) {
  const broken = left?.state !== "ok" || right?.state !== "ok";
  return `<div class="truenas-connector${broken ? " truenas-connector--broken" : ""}" aria-hidden="true"></div>`;
}

function targetText(truenas) {
  const diagnostics = truenas?.diagnostics;
  const configuredTarget = diagnostics?.target || truenas?.public?.url || "TrueNAS";
  const wan = diagnostics?.wan;
  if (!wan?.ipv4) return configuredTarget;
  const provider = wan?.provider ? ` · ${wan.provider}` : "";
  const addressKind = wan?.static ? " static IPv4" : " IPv4";
  return `${configuredTarget} · pfSense WAN / homelab public endpoint ${wan.ipv4}${provider}${addressKind}`;
}

function filterIcon(filter) {
  if (filter?.state === "blocked") return "💀";
  if (filter?.state === "running") return "●";
  if (filter?.state === "in_path") return "◐";
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

function renderIngressBlock(data, target) {
  const container = ensureIngressBlock(target);
  if (!container) return;
  const block = data?.pfsense?.dns?.ingress_block;
  const controlPath = block?.control_path;

  if (block?.state === "telemetry_unavailable" && controlPath?.blind_spot === true) {
    const detail = escapeText(controlPath?.detail || "pfSense security telemetry shares the WAN path");
    const evidence = escapeText(block?.evidence || "snort2c cannot be queried");
    container.className = "truenas-ingress-block truenas-ingress-block--warning";
    container.hidden = false;
    container.innerHTML =
      "<strong>⚠ Snort attribution unavailable · self-diagnostic blind spot</strong>" +
      `<span>${detail}</span>` +
      `<span>${evidence}</span>`;
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

function render(data) {
  const truenas = data?.truenas;
  const measuredStages = truenas?.diagnostics?.stages;
  const pipeline = document.getElementById("truenas-pipeline");
  const state = document.getElementById("truenas-platform-state");
  const target = document.getElementById("truenas-platform-target");
  const error = document.getElementById("truenas-platform-error");
  if (!pipeline || !state || !target || !error) return;

  error.hidden = true;
  error.textContent = "";
  target.textContent = targetText(truenas);
  renderIngressBlock(data, target);

  if (!Array.isArray(measuredStages) || measuredStages.length === 0) {
    pipeline.innerHTML = "";
    state.className = "truenas-platform-state truenas-platform-state--fail";
    state.textContent = "diagnostics unavailable";
    error.hidden = false;
    error.textContent = "TrueNAS diagnostics are missing from /api/homelab/health.";
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
  if (ingressBlock?.state === "blocked") {
    state.className = "truenas-platform-state truenas-platform-state--fail";
    state.textContent = "blocked by Snort/PF";
  } else {
    state.className = `truenas-platform-state truenas-platform-state--${overall}`;
    if (api.stage === "missing_api_key") {
      state.textContent = "authentication blocked · API key missing";
    } else if (api.stage === "invalid_api_key_reference") {
      state.textContent = "authentication failed · invalid secret reference";
    } else if (overall === "ok") {
      const version = api.version ? ` · ${api.version}` : "";
      state.textContent = `healthy${version}`;
    } else {
      state.textContent = overall;
    }
  }
}

export function loadTrueNas() {
  fetchHomelabHealth()
    .then(render)
    .catch((err) => {
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
    });
}
