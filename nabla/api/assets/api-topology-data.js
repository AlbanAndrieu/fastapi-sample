let topologyRequest = null;

async function fetchJson(url) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function loadTopology() {
  try {
    const topology = await fetchJson("/api/public-topology");
    return {
      ...topology,
      source: topology.source || topology.projection || "public-topology",
    };
  } catch (error) {
    return {
      nodes: [],
      relations: [],
      source: "public-topology-unavailable",
      error: error.message,
      endpoint: "/api/public-topology",
    };
  }
}

export function fetchTopology({ force = false } = {}) {
  if (force) topologyRequest = null;
  if (!topologyRequest) topologyRequest = loadTopology();
  return topologyRequest;
}
