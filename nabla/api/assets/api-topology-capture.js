(() => {
  const original = window.cytoscape;
  if (typeof original !== "function" || original.__nablaWrapped === true)
    return;

  function wrapped(options) {
    const graph = original(options);
    window.__nablaTopologyGraph = graph;
    document.dispatchEvent(
      new CustomEvent("nabla-topology-graph-ready", { detail: { graph } }),
    );
    return graph;
  }

  Object.assign(wrapped, original);
  wrapped.__nablaWrapped = true;
  window.cytoscape = wrapped;
})();
