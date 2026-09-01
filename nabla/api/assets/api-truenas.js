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
  return `${configuredTarget} · WAN ${wan.ipv4}${provider}${addressKind}`;
}

function filterClass(filter) {
  if (filter?.state === "running" || filter?.state === "in_path") return "possible";
  if (filter?.state === "stopped") return "stopped";
  return "unknown";
}

function filterIcon(filter) {
  if (filter?.state === "running") return "●";
  if (filter?.state === "in_path") return "◐";
  if (filter?.state === "stopped") return "○";
  return "?";
}

function ensureSecurityFilters(target) {
  let container = document.getElementById("truenas-security-filters");
  if (container || !target) return container;
  container = document.createElement("div");
  container.id = "truenas-security-filters";
  container.className = "truenas-security-filters";
  target.insertAdjacentElement("afterend", container);
  return container;
}

function renderSecurityFilters(data, target) {
  const container = ensureSecurityFilters(target);
  if (!container) return;
  const filters = data?.pfsense?.dns?.security_filters;
  if (!Array.isArray(filters) || filters.length === 0) {
    container.innerHTML = '<span class="truenas-security-filters-title">Ingress filters</span>' +
      '<span class="truenas-filter truenas-filter--unknown">? telemetry unavailable</span>';
    return;
  }
  const chips = filters.map((filter) => {
    const cls = filterClass(filter);
    const label = escapeText(filter?.label || filter?.id || "filter");
    const state = escapeText(filter?.state || "unknown");
    const detail = escapeText(filter?.detail || "");
    return `<span class="truenas-filter truenas-filter--${cls}" title="${detail}">` +
      `<span aria-hidden="true">${filterIcon(filter)}</span> ${label} · ${state}</span>`;
  }).join("");
  container.innerHTML = '<span class="truenas-security-filters-title">Ingress filters</span>' + chips;
}

function render(data) {
  const truenas = data?.truenas;
  const stages = truenas?.diagnostics?.stages;
  const pipeline = document.getElementById("truenas-pipeline");
  const state = document.getElementById("truenas-platform-state");
  const target = document.getElementById("truenas-platform-target");
  const error = document.getElementById("truenas-platform-error");
  if (!pipeline || !state || !target || !error) return;

  error.hidden = true;
  error.textContent = "";
  target.textContent = targetText(truenas);
  renderSecurityFilters(data, target);

  if (!Array.isArray(stages) || stages.length === 0) {
    pipeline.innerHTML = "";
    state.className = "truenas-platform-state truenas-platform-state--fail";
    state.textContent = "diagnostics unavailable";
    error.hidden = false;
    error.textContent = "TrueNAS diagnostics are missing from /api/homelab/health.";
    return;
  }

  let html = "";
  stages.forEach((stage, index) => {
    if (index > 0) html += renderConnector(stages[index - 1], stage);
    html += renderStage(stage);
  });
  pipeline.innerHTML = html;

  const overall = truenas?.state || "fail";
  state.className = `truenas-platform-state truenas-platform-state--${overall}`;
  const api = truenas?.api || {};
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
