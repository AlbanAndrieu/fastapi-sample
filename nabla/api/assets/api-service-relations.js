// A pure read of /api/public-topology. No per-card requests or guessed URLs.
// Only canonical IDs existing in the received public graph are navigable.
const TYPES = new Set([
  "dependsOn", "consumesApi", "routesTo", "storesIn",
  "authenticatesVia", "partOf", "exposedBy", "hostedBy",
]);
const ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/;
const MAX_RELATIONS = 24;

export function serviceRelations(topology, serviceId) {
  const empty = { dependencies: [], dependents: [] };
  if (!ID_PATTERN.test(String(serviceId || ""))) return empty;
  const nodes = new Map(
    (Array.isArray(topology?.nodes) ? topology.nodes : [])
      .filter((node) => node && typeof node.id === "string" &&
        ID_PATTERN.test(node.id))
      .map((node) => [node.id, node]),
  );
  if (!nodes.has(serviceId)) return empty;
  const dependencies = [];
  const dependents = [];
  const seen = new Set();
  for (const edge of Array.isArray(topology?.relations) ? topology.relations : []) {
    if (!edge || !TYPES.has(edge.type) ||
        !ID_PATTERN.test(String(edge.source || "")) ||
        !ID_PATTERN.test(String(edge.target || ""))) continue;
    if (!nodes.has(edge.source) || !nodes.has(edge.target) ||
        edge.source === edge.target) continue;
    const direction = edge.source === serviceId
      ? "dependencies"
      : edge.target === serviceId ? "dependents" : null;
    if (!direction) continue;
    const target = direction === "dependencies" ? edge.target : edge.source;
    const dedup = `${direction}:${target}:${edge.type}`;
    if (seen.has(dedup)) continue;
    seen.add(dedup);
    const node = nodes.get(target);
    const relation = {
      id: target,
      name: typeof node.name === "string" && node.name.trim()
        ? node.name.slice(0, 90) : target,
      type: edge.type,
      required: edge.strength === "required",
    };
    const list = direction === "dependencies" ? dependencies : dependents;
    if (list.length < MAX_RELATIONS) list.push(relation);
  }
  return { dependencies, dependents };
}
