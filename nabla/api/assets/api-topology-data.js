let topologyRequest = null;

async function fetchJson(url) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function topologyFromDeclaredServices(catalog) {
  const services = Array.isArray(catalog?.services) ? catalog.services : [];
  return {
    nodes: services
      .map((service) => {
        const id = service?.id || service?.serviceId || service?.service_id;
        if (!id) return null;
        return {
          id: String(id),
          name: String(service?.name || id),
          kind: String(service?.kind || "service"),
          category: String(service?.category || "services"),
          presentationRole:
            service?.presentationRole || service?.presentation_role || null,
          criticality: service?.criticality || null,
          securityFunctions:
            service?.securityFunctions || service?.security_functions || [],
          environments: Array.isArray(service?.environments)
            ? service.environments
            : null,
          environment: service?.environment || null,
          runtime: service?.runtime || null,
          lifecycle: service?.lifecycle || null,
          sourcePath: service?.sourcePath || service?.source_path || null,
          url: service?.url || null,
        };
      })
      .filter(Boolean),
    relations: [],
    source: "declared-services-fallback",
  };
}

async function loadTopology() {
  try {
    const topology = await fetchJson("/api/homelab-topology");
    return { ...topology, source: topology.source || "homelab-topology" };
  } catch (topologyError) {
    try {
      const catalog = await fetchJson("/api/homelab/declared-services");
      return topologyFromDeclaredServices(catalog);
    } catch (catalogError) {
      return {
        nodes: [],
        relations: [],
        source: "classification-unavailable",
        error: `${topologyError.message}; fallback: ${catalogError.message}`,
      };
    }
  }
}

export function fetchTopology({ force = false } = {}) {
  if (force) topologyRequest = null;
  if (!topologyRequest) topologyRequest = loadTopology();
  return topologyRequest;
}
