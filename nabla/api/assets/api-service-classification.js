const FUNCTIONAL_RELATION_TYPES = new Set([
  "dependsOn",
  "consumesApi",
  "routesTo",
  "storesIn",
  "authenticatesVia",
  "partOf",
  "exposedBy",
]);

const IMPACT_RELATION_TYPES = new Set([
  ...FUNCTIONAL_RELATION_TYPES,
  "hostedBy",
]);

const FOUNDATION_KINDS = new Set([
  "storage-platform",
  "container-runtime",
  "firewall",
  "edge",
  "network-gateway",
  "reverse-proxy",
  "orchestrator",
  "kubernetes-os",
  "cni",
  "csi",
  "dns",
  "ingress",
  "network-proxy",
]);

const FOUNDATION_IDS = new Set([
  "truenas",
  "docker",
  "pfsense",
  "pfsense-haproxy",
  "talos",
  "kubernetes",
  "etcd",
]);

const SHARED_DATA_KINDS = new Set([
  "database",
  "cache",
  "key-value-store",
  "object-storage",
  "analytics-database",
  "vector-database",
  "message-broker",
  "search",
  "log-store",
  "metrics-store",
  "trace-store",
]);

const SERVICE_KINDS = new Set([
  "application",
  "api",
  "service",
  "website",
  "web",
  "frontend",
  "workflow",
  "security-app",
]);

const SECURITY_CONTROL_KINDS = new Set([
  "firewall",
  "ids",
  "ips",
  "waf",
  "security-agent",
  "security-control",
  "siem",
  "vulnerability-scanner",
]);

const OBSERVABILITY_KINDS = new Set([
  "observability",
  "observability-ui",
  "metrics-exporter",
  "telemetry-collector",
  "log-store",
  "metrics-store",
  "trace-store",
]);

const VALID_PRESENTATION_ROLES = new Set(["service", "core", "support"]);
const VALID_CRITICALITIES = new Set(["critical", "high", "medium", "low"]);

export const NIST_CSF_FUNCTIONS = [
  {
    key: "govern",
    label: "Govern",
    description: "Cybersecurity risk strategy, policy, roles and oversight.",
  },
  {
    key: "identify",
    label: "Identify",
    description: "Assets, dependencies, risks and improvement opportunities.",
  },
  {
    key: "protect",
    label: "Protect",
    description: "Safeguards that reduce cybersecurity risk.",
  },
  {
    key: "detect",
    label: "Detect",
    description: "Discovery and analysis of possible attacks or compromises.",
  },
  {
    key: "respond",
    label: "Respond",
    description: "Incident management, containment, mitigation and communication.",
  },
  {
    key: "recover",
    label: "Recover",
    description: "Restoration of affected assets and operations.",
  },
];

const NIST_CSF_FUNCTION_KEYS = new Set(
  NIST_CSF_FUNCTIONS.map((item) => item.key),
);

export const CRITICALITY_WEIGHT = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function collectReachable(start, adjacency) {
  const seen = new Set();
  const pending = [...(adjacency.get(start) || [])];
  while (pending.length > 0) {
    const current = pending.pop();
    if (!current || current === start || seen.has(current)) continue;
    seen.add(current);
    for (const next of adjacency.get(current) || []) {
      if (!seen.has(next)) pending.push(next);
    }
  }
  return seen;
}

function inferredRole(node, directDependencies, transitiveDependents) {
  const explicit = String(node?.presentationRole || "");
  if (VALID_PRESENTATION_ROLES.has(explicit)) return explicit;

  if (FOUNDATION_IDS.has(node.id) || FOUNDATION_KINDS.has(node.kind)) return "core";
  if (SECURITY_CONTROL_KINDS.has(node.kind)) return "core";
  if (SERVICE_KINDS.has(node.kind)) return "service";

  if (
    directDependencies > 0 &&
    transitiveDependents === 0 &&
    !["infrastructure", "network", "data", "observability"].includes(node.category)
  ) {
    return "service";
  }
  if (transitiveDependents > 0) return "core";
  return "support";
}

function inferredCriticality(node, role, transitiveDependents) {
  const explicit = String(node?.criticality || "");
  if (VALID_CRITICALITIES.has(explicit)) return explicit;

  if (FOUNDATION_IDS.has(node.id) || FOUNDATION_KINDS.has(node.kind)) return "critical";
  if (role === "core" && SECURITY_CONTROL_KINDS.has(node.kind)) return "high";
  if (
    role === "core" &&
    (node.category === "data" || SHARED_DATA_KINDS.has(node.kind)) &&
    transitiveDependents > 0
  ) {
    return "high";
  }
  if (role === "core") return "high";
  if (role === "service") return "medium";
  return "low";
}

function declaredSecurityFunctions(node) {
  if (!Array.isArray(node?.securityFunctions)) return [];
  return node.securityFunctions.filter((value) =>
    NIST_CSF_FUNCTION_KEYS.has(String(value)),
  );
}

function presentationGroup(node, role, criticality, transitiveDependents) {
  if (criticality === "critical") return "core-critical";
  if (
    declaredSecurityFunctions(node).length > 0 ||
    SECURITY_CONTROL_KINDS.has(node.kind)
  ) {
    return "security-controls";
  }
  if (role === "service") return "services";
  if (
    role === "core" ||
    transitiveDependents > 0 ||
    SHARED_DATA_KINDS.has(node.kind)
  ) {
    return "shared-core";
  }
  if (OBSERVABILITY_KINDS.has(node.kind) || role === "support") return "support";
  return "support";
}

export function analyzeTopology(topology) {
  const functionalDependencies = new Map();
  const impactDependents = new Map();

  for (const relation of topology?.relations || []) {
    if (relation?.strength !== "required") continue;

    if (FUNCTIONAL_RELATION_TYPES.has(relation?.type)) {
      if (!functionalDependencies.has(relation.source)) {
        functionalDependencies.set(relation.source, new Set());
      }
      functionalDependencies.get(relation.source).add(relation.target);
    }

    if (IMPACT_RELATION_TYPES.has(relation?.type)) {
      if (!impactDependents.has(relation.target)) {
        impactDependents.set(relation.target, new Set());
      }
      impactDependents.get(relation.target).add(relation.source);
    }
  }

  const analysis = new Map();
  for (const node of topology?.nodes || []) {
    const directDependencies = functionalDependencies.get(node.id)?.size || 0;
    const transitiveDependents = collectReachable(
      node.id,
      impactDependents,
    ).size;
    const role = inferredRole(node, directDependencies, transitiveDependents);
    const criticality = inferredCriticality(node, role, transitiveDependents);
    const group = presentationGroup(
      node,
      role,
      criticality,
      transitiveDependents,
    );
    analysis.set(node.id, {
      role,
      criticality,
      group,
      securityFunctions: declaredSecurityFunctions(node),
      directDependencies,
      transitiveDependents,
    });
  }
  return analysis;
}
