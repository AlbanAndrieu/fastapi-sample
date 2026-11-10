/** Economical, deterministic browser cadence. Private data is never cached. */
export function homepageCadence(runtimeMode, owner) {
  const cloud = runtimeMode === "fastapi_cloud";
  return {
    // Anonymous Cloud dashboards are on-demand; no permanent wake-up loop.
    pollEnabled: !cloud || owner === true,
    pollIntervalMs: cloud ? 180000 : 30000,
    warmupDelaysMs: cloud ? [15000] : [2000, 4000, 8000, 15000, 30000],
  };
}
