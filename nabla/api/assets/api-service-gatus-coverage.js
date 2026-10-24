// Summarize the bounded Gatus-via-Prometheus snapshot already in /api/health-board.
// A successful scrape does NOT imply successful checks or catalogue coverage.
const PROTOCOLS = ["HTTP", "HTTPS", "TCP"];
const MAX_SERVICES = 256;
const ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,127}$/;

function binary(value) {
  return typeof value === "number" && (value === 0 || value === 1);
}

export function gatusCoverage(snapshot, now = Date.now()) {
  const synthetic = snapshot?.platform_metrics?.synthetic_probes;
  const timestamp = Date.parse(String(snapshot?.platform_metrics?.generated_at || ""));
  const snapshotAge = Number.isFinite(timestamp) ? (now - timestamp) / 1000 : NaN;
  const fresh = Number.isFinite(snapshotAge) &&
    snapshotAge >= -60 && snapshotAge <= 180;
  const ready =
    fresh &&
    synthetic?.state === "observed" &&
    synthetic?.gatus_up === 1 &&
    synthetic?.truncated !== true;
  const entries =
    synthetic?.services && typeof synthetic.services === "object" &&
    !Array.isArray(synthetic.services)
      ? Object.entries(synthetic.services).slice(0, MAX_SERVICES)
      : [];
  const summary = {
    state: ready ? "observed" : "unverified",
    reason: !synthetic
      ? "metrics_snapshot_missing"
      : !fresh
        ? "snapshot_stale_or_missing_timestamp"
        : synthetic?.truncated === true
          ? "truncated"
        : synthetic?.gatus_up !== 1
          ? "gatus_scrape_unverified"
          : synthetic?.state !== "observed"
            ? "recording_rules_unverified"
            : "observed",
    observedServices: 0,
    observedProbes: 0,
    up: 0,
    down: 0,
    unobserved: 0,
    failures: [],
    successes: [],
    missing: [],
  };
  // Do not describe stored samples as live when the telemetry is unavailable.
  if (!ready) return summary;
  for (const [id, probes] of entries) {
    if (!ID_PATTERN.test(id) || !probes || typeof probes !== "object") continue;
    summary.observedServices += 1;
    let hasEvidence = false;
    for (const type of PROTOCOLS) {
      const sample = probes[type];
      if (!binary(sample?.success)) continue;
      hasEvidence = true;
      summary.observedProbes += 1;
      if (sample.success === 0) {
        summary.down += 1;
        summary.failures.push({ id, type, status: "down" });
      } else {
        summary.up += 1;
        summary.successes.push({ id, type, status: "up" });
      }
    }
    if (!hasEvidence) {
      summary.unobserved += 1;
      summary.missing.push({ id, type: "none", status: "not_observed" });
    }
  }
  return summary;
}

export function gatusServiceEvidence(snapshot, id, now = Date.now()) {
  const synthetic = snapshot?.platform_metrics?.synthetic_probes;
  const coverage = gatusCoverage(snapshot, now);
  if (coverage.state !== "observed") return { status: "unverified", probes: [] };
  const service =
    typeof id === "string" && ID_PATTERN.test(id)
      ? synthetic?.services?.[id]
      : null;
  const probes = PROTOCOLS.flatMap((type) =>
    binary(service?.[type]?.success)
      ? [{ type, success: service[type].success,
           availability: service[type].availability_ratio_5m }]
      : [],
  );
  return {
    status: probes.length === 0
      ? "not_observed"
      : probes.some((probe) => probe.success === 0)
        ? "down"
        : "up",
    probes,
  };
}
