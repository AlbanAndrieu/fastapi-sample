import { fetchHealthBoard } from "./api-health-board.js";
import { dependencyDetailText } from "./api-health-dependency.js";

const HEALTH_STATES = new Set(["ok", "warn", "fail", "unknown"]);

function healthState(value) {
  const state = String(value || "unknown")
    .trim()
    .toLowerCase();
  return HEALTH_STATES.has(state) ? state : "unknown";
}

function serviceRows(snapshot) {
  return Array.isArray(snapshot?.homelab?.services)
    ? snapshot.homelab.services
    : [];
}

function serviceIndex(snapshot) {
  return new Map(
    serviceRows(snapshot)
      .filter((row) => row?.id)
      .map((row) => [String(row.id), row]),
  );
}

function listText(value) {
  return Array.isArray(value) ? value.filter(Boolean).join(", ") : "";
}

function observationAge(row) {
  const age = Number(row?.observation_age_seconds);
  return Number.isFinite(age) ? Math.round(age) : "";
}

function requiredEdgeState(sourceRow, target, relationType) {
  const evidence = Array.isArray(sourceRow?.dependency_evidence)
    ? sourceRow.dependency_evidence
    : [];
  const match = evidence.find(
    (entry) =>
      String(entry?.target || "") === String(target) &&
      String(entry?.relation_type || "") === String(relationType),
  );
  return match ? healthState(match.target_state) : "unknown";
}

function setNodeHealth(node, row) {
  const available = Boolean(row);
  node.data("healthOverlay", available ? "on" : "missing");
  node.data(
    "healthEffectiveState",
    healthState(row?.effective_state || row?.state),
  );
  node.data("healthLocalState", healthState(row?.local_state));
  node.data("healthDependencyState", healthState(row?.dependency_state));
  node.data("healthBlockedBy", listText(row?.blocked_by));
  node.data("healthDegradedBy", listText(row?.degraded_by));
  node.data(
    "healthUnconfirmedDependencies",
    listText(row?.unconfirmed_dependencies),
  );
  node.data("healthObservationAge", observationAge(row));
  node.data(
    "healthObservationStale",
    row?.observation_stale === true ? "yes" : "no",
  );
  node.data("healthRuntimeState", row?.runtime_state || "");
  node.data("healthDirectState", row?.direct_state || "");
  node.data("healthInternalState", row?.internal_state || "");
  node.data("healthDetail", row ? dependencyDetailText(row) : "");
}

function setEdgeHealth(edge, sourceRow) {
  if (edge.data("strength") !== "required") {
    edge.data("healthOverlay", "optional");
    edge.data("healthEdgeState", "unknown");
    return;
  }
  edge.data("healthOverlay", sourceRow ? "on" : "missing");
  edge.data(
    "healthEdgeState",
    sourceRow
      ? requiredEdgeState(
          sourceRow,
          edge.data("target"),
          edge.data("relationType"),
        )
      : "unknown",
  );
}

export async function loadTopologyHealthOverlay() {
  const snapshot = await fetchHealthBoard();
  return {
    snapshot,
    services: serviceIndex(snapshot),
  };
}

export function applyTopologyHealthOverlay(graph, overlay) {
  const services =
    overlay?.services instanceof Map ? overlay.services : new Map();
  let matchedNodes = 0;
  graph.batch(() => {
    graph.nodes().forEach((node) => {
      const row = services.get(node.id()) || null;
      if (row) matchedNodes += 1;
      setNodeHealth(node, row);
    });
    graph.edges().forEach((edge) => {
      setEdgeHealth(edge, services.get(String(edge.data("source"))) || null);
    });
  });
  return matchedNodes;
}

export function clearTopologyHealthOverlay(graph) {
  graph.batch(() => {
    graph.nodes().forEach((node) => {
      setNodeHealth(node, null);
      node.data("healthOverlay", "off");
    });
    graph.edges().forEach((edge) => {
      edge.data("healthOverlay", "off");
      edge.data("healthEdgeState", "unknown");
    });
  });
}

export function topologyHealthSummary(overlay, matchedNodes) {
  const snapshot = overlay?.snapshot || {};
  const state = String(snapshot.state || "unknown");
  const age = Number(snapshot.age_seconds);
  const parts = [`health ${state}`, `${matchedNodes} matched nodes`];
  if (Number.isFinite(age)) parts.push(`${Math.round(age)}s old`);
  if (snapshot.refreshing === true) parts.push("refresh in progress");
  return parts.join(" · ");
}
