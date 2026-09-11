import { analyzeTopology } from "./api-service-classification.js";
import { fetchTopology } from "./api-topology-data.js";

const RELATION_LABELS = {
  dependsOn: "depends on",
  consumesApi: "consumes API",
  providesApi: "provides API",
  partOf: "part of",
  hostedBy: "hosted by",
  routesTo: "routes to",
  observedBy: "observed by",
  storesIn: "stores in",
  authenticatesVia: "authenticates via",
  exposedBy: "exposed by",
  automates: "automates",
};

const state = {
  graph: null,
  topology: null,
  analysis: null,
};

function normalize(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function nodeElements(topology, analysis) {
  return (topology.nodes || []).map((node) => {
    const presentation = analysis.get(node.id) || {};
    return {
      data: {
        id: node.id,
        label: `${node.icon ? `${node.icon} ` : ""}${node.name}`,
        name: node.name,
        kind: node.kind,
        category: node.category,
        role: presentation.role || node.presentationRole || "support",
        criticality: presentation.criticality || node.criticality || "low",
        group: presentation.group || "support",
        directDependencies: presentation.directDependencies || 0,
        transitiveDependents: presentation.transitiveDependents || 0,
        description: node.description || "",
        url: node.url || "",
        internalUrl: node.internalUrl || "",
        sourcePath: node.sourcePath || "",
        securityFunctions: (presentation.securityFunctions || []).join(", "),
        searchText: normalize(
          [
            node.id,
            node.name,
            node.kind,
            node.category,
            node.description,
            presentation.role,
            presentation.criticality,
            presentation.group,
          ].join(" "),
        ),
      },
    };
  });
}

function edgeElements(topology) {
  return (topology.relations || []).map((relation, index) => ({
    data: {
      id: `relation-${index}-${relation.source}-${relation.target}`,
      source: relation.source,
      target: relation.target,
      relationType: relation.type,
      relationLabel: RELATION_LABELS[relation.type] || relation.type,
      strength: relation.strength,
      description: relation.description || "",
      evidence: Array.isArray(relation.evidence)
        ? relation.evidence.join(" · ")
        : "",
    },
  }));
}

function graphStyle() {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        color: "#e8e8e8",
        "font-size": 10,
        "text-wrap": "wrap",
        "text-max-width": 120,
        "text-valign": "bottom",
        "text-margin-y": 7,
        width: 36,
        height: 36,
        "background-color": "#38536d",
        "border-width": 2,
        "border-color": "#6784a1",
      },
    },
    {
      selector: 'node[criticality = "critical"]',
      style: {
        "background-color": "#7c2e2e",
        "border-color": "#d66868",
        width: 48,
        height: 48,
      },
    },
    {
      selector: 'node[criticality = "high"]',
      style: {
        "background-color": "#745125",
        "border-color": "#d39a4c",
        width: 43,
        height: 43,
      },
    },
    {
      selector: 'node[role = "service"]',
      style: {
        "background-color": "#235f49",
        "border-color": "#55ad85",
      },
    },
    {
      selector: 'node[group = "security-controls"]',
      style: {
        shape: "hexagon",
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": "#59616a",
        "target-arrow-color": "#59616a",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        label: "data(relationLabel)",
        color: "#8b949e",
        "font-size": 8,
        "text-background-color": "#080808",
        "text-background-opacity": 0.8,
        "text-background-padding": 2,
        "text-rotation": "autorotate",
      },
    },
    {
      selector: 'edge[strength = "optional"]',
      style: {
        "line-style": "dashed",
        opacity: 0.58,
      },
    },
    {
      selector: ".is-filtered",
      style: {
        display: "none",
      },
    },
    {
      selector: ".is-muted",
      style: {
        opacity: 0.12,
      },
    },
    {
      selector: ":selected",
      style: {
        "border-color": "#ffffff",
        "border-width": 4,
        "line-color": "#d9eaff",
        "target-arrow-color": "#d9eaff",
      },
    },
  ];
}

function layoutOptions(name) {
  if (name === "breadthfirst") {
    return {
      name,
      directed: true,
      padding: 28,
      spacingFactor: 1.15,
      animate: false,
    };
  }
  if (name === "concentric") {
    return {
      name,
      padding: 28,
      minNodeSpacing: 24,
      levelWidth: () => 2,
      concentric: (node) => Number(node.data("transitiveDependents")) || 0,
      animate: false,
    };
  }
  if (name === "grid") return { name, padding: 28, animate: false };
  return {
    name: "cose",
    padding: 28,
    nodeRepulsion: 7000,
    idealEdgeLength: 90,
    animate: false,
  };
}

function populateRelationFilter(topology) {
  const select = document.getElementById("topology-relation-filter");
  if (!select) return;
  const types = [
    ...new Set((topology.relations || []).map((relation) => relation.type)),
  ].sort((left, right) => left.localeCompare(right));
  for (const type of types) {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = RELATION_LABELS[type] || type;
    select.appendChild(option);
  }
}

function updateCounts() {
  const graph = state.graph;
  if (!graph) return;
  const visibleNodes = graph.nodes().not(".is-filtered").length;
  const visibleEdges = graph.edges().not(".is-filtered").length;
  document.getElementById("topology-visible-count").textContent =
    `${visibleNodes} / ${visibleEdges}`;
}

function clearFocus() {
  if (!state.graph) return;
  state.graph.elements().removeClass("is-muted");
}

function focusElement(element) {
  const graph = state.graph;
  if (!graph) return;
  clearFocus();
  const connected = element.isNode()
    ? element.closedNeighborhood()
    : element.connectedNodes().union(element);
  graph.elements().not(connected).addClass("is-muted");
}

function addDetail(list, label, value, href = "") {
  if (value === null || value === undefined || value === "") return;
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  if (href) {
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = String(value);
    description.appendChild(link);
  } else {
    description.textContent = String(value);
  }
  list.append(term, description);
}

function showDetails(element) {
  const empty = document.getElementById("topology-details-empty");
  const list = document.getElementById("topology-details-list");
  if (!empty || !list) return;
  list.replaceChildren();

  if (element.isNode()) {
    addDetail(list, "Name", element.data("name"));
    addDetail(list, "ID", element.id());
    addDetail(list, "Kind", element.data("kind"));
    addDetail(list, "Category", element.data("category"));
    addDetail(list, "Role", element.data("role"));
    addDetail(list, "Criticality", element.data("criticality"));
    addDetail(list, "Required deps", element.data("directDependencies"));
    addDetail(list, "Blast radius", element.data("transitiveDependents"));
    addDetail(list, "NIST CSF", element.data("securityFunctions"));
    addDetail(list, "Description", element.data("description"));
    addDetail(list, "Public URL", element.data("url"), element.data("url"));
    addDetail(
      list,
      "Internal URL",
      element.data("internalUrl"),
      element.data("internalUrl"),
    );
    addDetail(list, "Source", element.data("sourcePath"));
  } else {
    addDetail(list, "Relation", element.data("relationLabel"));
    addDetail(list, "Type", element.data("relationType"));
    addDetail(list, "Strength", element.data("strength"));
    addDetail(list, "Source", element.data("source"));
    addDetail(list, "Target", element.data("target"));
    addDetail(list, "Description", element.data("description"));
    addDetail(list, "Evidence", element.data("evidence"));
  }

  empty.hidden = true;
  list.hidden = false;
}

function resetDetails() {
  const empty = document.getElementById("topology-details-empty");
  const list = document.getElementById("topology-details-list");
  if (empty) empty.hidden = false;
  if (list) {
    list.hidden = true;
    list.replaceChildren();
  }
}

function applyFilters() {
  const graph = state.graph;
  if (!graph) return;
  const query = normalize(document.getElementById("topology-search")?.value);
  const relation =
    document.getElementById("topology-relation-filter")?.value || "all";
  const strength =
    document.getElementById("topology-strength-filter")?.value || "all";

  graph.batch(() => {
    clearFocus();
    graph.elements().removeClass("is-filtered");
    graph.nodes().forEach((node) => {
      if (query && !String(node.data("searchText")).includes(query)) {
        node.addClass("is-filtered");
      }
    });
    graph.edges().forEach((edge) => {
      const typeMismatch =
        relation !== "all" && edge.data("relationType") !== relation;
      const strengthMismatch =
        strength !== "all" && edge.data("strength") !== strength;
      const hiddenEndpoint = edge
        .connectedNodes()
        .some((node) => node.hasClass("is-filtered"));
      if (typeMismatch || strengthMismatch || hiddenEndpoint) {
        edge.addClass("is-filtered");
      }
    });
  });
  updateCounts();
}

function runLayout() {
  if (!state.graph) return;
  const name = document.getElementById("topology-layout")?.value || "cose";
  state.graph.elements().not(".is-filtered").layout(layoutOptions(name)).run();
  state.graph.fit(state.graph.elements().not(".is-filtered"), 36);
}

function resetView() {
  const search = document.getElementById("topology-search");
  const relation = document.getElementById("topology-relation-filter");
  const strength = document.getElementById("topology-strength-filter");
  if (search) search.value = "";
  if (relation) relation.value = "all";
  if (strength) strength.value = "all";
  state.graph?.elements().unselect();
  resetDetails();
  applyFilters();
  runLayout();
}

function installControls() {
  document
    .getElementById("topology-search")
    ?.addEventListener("input", applyFilters);
  document
    .getElementById("topology-relation-filter")
    ?.addEventListener("change", applyFilters);
  document
    .getElementById("topology-strength-filter")
    ?.addEventListener("change", applyFilters);
  document
    .getElementById("topology-layout")
    ?.addEventListener("change", runLayout);
  document.getElementById("topology-fit")?.addEventListener("click", () => {
    state.graph?.fit(state.graph.elements().not(".is-filtered"), 36);
  });
  document
    .getElementById("topology-reset")
    ?.addEventListener("click", resetView);
}

function installGraphEvents() {
  const graph = state.graph;
  if (!graph) return;
  graph.on("tap", "node, edge", (event) => {
    showDetails(event.target);
    focusElement(event.target);
  });
  graph.on("tap", (event) => {
    if (event.target !== graph) return;
    graph.elements().unselect();
    clearFocus();
    resetDetails();
  });
}

async function start() {
  const error = document.getElementById("topology-error");
  const status = document.getElementById("topology-status");
  const container = document.getElementById("topology-graph");
  if (!container) return;

  if (typeof window.cytoscape !== "function") {
    if (error) {
      error.hidden = false;
      error.textContent =
        "Cytoscape.js could not be loaded. The topology JSON remains available from the navigation link.";
    }
    return;
  }

  const topology = await fetchTopology();
  state.topology = topology;
  state.analysis = analyzeTopology(topology);
  document.getElementById("topology-node-count").textContent = String(
    topology.nodes?.length || 0,
  );
  document.getElementById("topology-edge-count").textContent = String(
    topology.relations?.length || 0,
  );

  if (!topology.nodes?.length) {
    if (error) {
      error.hidden = false;
      error.textContent = `Topology unavailable${topology.error ? `: ${topology.error}` : "."}`;
    }
    if (status) status.textContent = "No declared topology could be loaded.";
    return;
  }

  populateRelationFilter(topology);
  state.graph = window.cytoscape({
    container,
    elements: [
      ...nodeElements(topology, state.analysis),
      ...edgeElements(topology),
    ],
    style: graphStyle(),
    layout: layoutOptions("cose"),
    minZoom: 0.08,
    maxZoom: 3,
    wheelSensitivity: 0.22,
  });
  installControls();
  installGraphEvents();
  updateCounts();
  if (status) {
    status.textContent = `Source: ${topology.source || "homelab-topology"} · select a node to inspect dependencies and blast radius.`;
  }
}

start().catch((caught) => {
  const error = document.getElementById("topology-error");
  if (!error) return;
  error.hidden = false;
  error.textContent = `Topology rendering failed: ${caught.message}`;
});
