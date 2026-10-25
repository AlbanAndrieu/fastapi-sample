// Summarize the bounded Gatus-via-Prometheus snapshot already in /api/health-board.
// A successful scrape does NOT imply successful checks or catalogue coverage.
const PROTOCOLS = ["HTTP", "HTTPS", "TCP"];
const MAX_SERVICES = 256;
const ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,127}$/;

function binary(value) {
  return typeof value === "number" && (value === 0 || value === 1);
}

function bounded(value, min, max) {
  return typeof value === "number" && Number.isFinite(value) &&
    value >= min && value <= max ? value : null;
}

function gatusProbe(type, sample) {
  const probe = { type, success: sample.success };
  const availability = bounded(sample.availability_ratio_5m, 0, 1);
  const duration = bounded(sample.duration_seconds, 0, 300);
  if (availability !== null) probe.availability = availability;
  if (duration !== null) probe.durationMs = duration * 1000;
  return probe;
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
      const entry = { id, type, status: sample.success === 0 ? "down" : "up" };
      const observation = gatusProbe(type, sample);
      if (observation.availability !== undefined) entry.availability = observation.availability;
      if (observation.durationMs !== undefined) entry.durationMs = observation.durationMs;
      if (sample.success === 0) {
        summary.down += 1;
        summary.failures.push(entry);
      } else {
        summary.up += 1;
        summary.successes.push(entry);
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
      ? [gatusProbe(type, service[type])]
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

/**
 * Catalogue/metrics reconciliation, not monitor configuration parity.
 * A card without a metric may be intentionally unmonitored or have a broken
 * recording rule. Neither state should be reported as a failed check.
 */
export function gatusCatalogueCoverage(snapshot, catalogueIds = [], now = Date.now()) {
  const fleet = gatusCoverage(snapshot, now);
  const ids = [...new Set((Array.isArray(catalogueIds) ? catalogueIds : [])
    .filter((id) => typeof id === "string" && ID_PATTERN.test(id)))].slice(0, MAX_SERVICES);
  const result = {
    state: fleet.state,
    reason: fleet.reason,
    catalogueTotal: ids.length,
    withSamples: 0,
    withoutSamples: [],
    failingServices: 0,
    status: fleet.state !== "observed" ? "unverified" : "partial",
    declaredMonitors: null,
  };
  if (fleet.state !== "observed") return result;
  for (const id of ids) {
    const check = gatusServiceEvidence(snapshot, id, now);
    if (check.probes.length) {
      result.withSamples++;
      if (check.status === "down") result.failingServices++;
    } else {
      result.withoutSamples.push(id);
    }
  }
  // Even 100% of visible cards with samples cannot establish Gatus config parity.
  return result;
}
