export const DEFAULT_TOPOLOGY_PRESET = "dependencies";

export const DEPENDENCY_RELATIONS = new Set([
  "dependsOn",
  "consumesApi",
  "providesApi",
  "storesIn",
  "authenticatesVia",
]);

export const NETWORK_PATH_RELATIONS = new Set(["routesTo", "exposedBy"]);

const DEFAULTS = {
  relation: "all",
  strength: "all",
  layout: "cose",
};

const PARAMS = {
  search: "q",
  preset: "view",
  relation: "relation",
  strength: "strength",
  layout: "layout",
};

const PRESET_LABELS = {
  dependencies: "Dependencies",
  "network-paths": "Network paths",
  architecture: "Architecture / support",
  all: "All relations",
};

function selectValue(id, fallback) {
  return document.getElementById(id)?.value || fallback;
}

function setValidSelectValue(id, value, fallback) {
  const select = document.getElementById(id);
  if (!select) return fallback;
  const candidate = value || fallback;
  const valid = [...select.options].some(
    (option) => option.value === candidate,
  );
  select.value = valid ? candidate : fallback;
  return select.value;
}

function setOrDelete(params, key, value, defaultValue = "") {
  if (!value || value === defaultValue) {
    params.delete(key);
    return;
  }
  params.set(key, value);
}

export function relationFamily(type) {
  if (DEPENDENCY_RELATIONS.has(type)) return "dependencies";
  if (NETWORK_PATH_RELATIONS.has(type)) return "network-paths";
  return "architecture";
}

export function presetAllowsRelation(type, preset) {
  if (preset === "all") return true;
  return relationFamily(type) === preset;
}

export function topologyPresetLabel(preset) {
  return PRESET_LABELS[preset] || PRESET_LABELS[DEFAULT_TOPOLOGY_PRESET];
}

export function hydrateTopologyControlsFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const search = document.getElementById("topology-search");
  if (search) search.value = params.get(PARAMS.search) || "";

  const preset = setValidSelectValue(
    "topology-view-preset",
    params.get(PARAMS.preset),
    DEFAULT_TOPOLOGY_PRESET,
  );
  const relation = setValidSelectValue(
    "topology-relation-filter",
    params.get(PARAMS.relation),
    DEFAULTS.relation,
  );
  setValidSelectValue(
    "topology-strength-filter",
    params.get(PARAMS.strength),
    DEFAULTS.strength,
  );
  setValidSelectValue(
    "topology-layout",
    params.get(PARAMS.layout),
    DEFAULTS.layout,
  );

  if (relation !== DEFAULTS.relation && preset !== "all") {
    const presetSelect = document.getElementById("topology-view-preset");
    if (presetSelect) presetSelect.value = "all";
  }
}

export function syncTopologyControlsToUrl() {
  const url = new URL(window.location.href);
  const params = url.searchParams;
  const search = document.getElementById("topology-search")?.value.trim() || "";
  const preset = selectValue("topology-view-preset", DEFAULT_TOPOLOGY_PRESET);
  const relation = selectValue("topology-relation-filter", DEFAULTS.relation);
  const strength = selectValue("topology-strength-filter", DEFAULTS.strength);
  const layout = selectValue("topology-layout", DEFAULTS.layout);

  setOrDelete(params, PARAMS.search, search);
  setOrDelete(params, PARAMS.preset, preset, DEFAULT_TOPOLOGY_PRESET);
  setOrDelete(params, PARAMS.relation, relation, DEFAULTS.relation);
  setOrDelete(params, PARAMS.strength, strength, DEFAULTS.strength);
  setOrDelete(params, PARAMS.layout, layout, DEFAULTS.layout);

  window.history.replaceState(
    null,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

export function resetTopologyControls() {
  const search = document.getElementById("topology-search");
  const preset = document.getElementById("topology-view-preset");
  const relation = document.getElementById("topology-relation-filter");
  const strength = document.getElementById("topology-strength-filter");
  const layout = document.getElementById("topology-layout");

  if (search) search.value = "";
  if (preset) preset.value = DEFAULT_TOPOLOGY_PRESET;
  if (relation) relation.value = DEFAULTS.relation;
  if (strength) strength.value = DEFAULTS.strength;
  if (layout) layout.value = DEFAULTS.layout;
}
