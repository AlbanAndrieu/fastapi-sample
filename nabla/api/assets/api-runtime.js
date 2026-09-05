import { fetchHealthBoard } from "./api-health-board.js";
import { escapeText } from "./api-health-ui.js";

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function renderPills(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return '<span class="runtime-topology-empty">none observed</span>';
  }
  return values
    .map((value) => `<code class="runtime-topology-pill">${escapeText(value)}</code>`)
    .join("");
}

function renderInstances(instances) {
  const target = document.getElementById("runtime-instance-list");
  if (!target) return;
  if (!Array.isArray(instances) || instances.length === 0) {
    target.innerHTML = '<span class="runtime-topology-empty">No active runtime heartbeat observed.</span>';
    return;
  }
  target.innerHTML = instances
    .map((instance) => {
      const id = escapeText(instance?.id || "runtime-unknown");
      const egress = escapeText(instance?.egress_ip || "egress unknown");
      const seen = escapeText(instance?.last_seen_at || "time unknown");
      return (
        '<div class="runtime-instance-row">' +
        `<code>${id}</code>` +
        `<span>${egress}</span>` +
        `<time>${seen}</time>` +
        "</div>"
      );
    })
    .join("");
}

function render(snapshot) {
  const runtime = snapshot?.runtime;
  const panel = document.getElementById("runtime-topology");
  const state = document.getElementById("runtime-topology-state");
  const activeEgress = document.getElementById("runtime-active-egress");
  const recentEgress = document.getElementById("runtime-recent-egress");
  if (!panel || !state || !activeEgress || !recentEgress) return;

  if (!runtime) {
    state.className = "runtime-topology-state runtime-topology-state--warn";
    state.textContent = "telemetry unavailable";
    return;
  }

  const count = Number(runtime.observed_instance_count);
  const runtimeMode = runtime.runtime_mode || panel.dataset.runtimeMode || "local";
  const isFastapiCloud = runtimeMode === "fastapi_cloud";
  setText("runtime-instance-count", Number.isFinite(count) ? String(count) : "—");
  setText(
    "runtime-replica-label",
    isFastapiCloud ? "FastAPI Cloud replicas" : "Runtime scope",
  );
  setText(
    "runtime-replica-count",
    isFastapiCloud
      ? runtime.platform_replica_count == null
        ? "control-plane only"
        : String(runtime.platform_replica_count)
      : Number.isFinite(count) && count > 1
        ? `${count} observed processes`
        : "local process",
  );
  setText("runtime-count-semantics", runtime.count_semantics || "Observed runtime heartbeats.");
  setText("runtime-aggregation", runtime.aggregation || "unknown");
  activeEgress.innerHTML = renderPills(runtime.active_egress_ips);
  recentEgress.innerHTML = renderPills(runtime.recent_egress_ips);
  renderInstances(runtime.instances);

  const degraded = runtime.degraded === true;
  state.className = `runtime-topology-state runtime-topology-state--${degraded ? "warn" : "ok"}`;
  if (isFastapiCloud) {
    state.textContent = degraded ? "local observation only" : `${count} active observed`;
  } else {
    state.textContent = degraded
      ? "local telemetry degraded"
      : Number.isFinite(count) && count > 1
        ? `${count} local processes`
        : "local runtime";
  }
}

export function loadRuntimeTopology() {
  fetchHealthBoard()
    .then(render)
    .catch((error) => {
      const state = document.getElementById("runtime-topology-state");
      if (!state) return;
      state.className = "runtime-topology-state runtime-topology-state--warn";
      state.textContent = `fetch failed · ${String(error?.message || error)}`;
    });
}
