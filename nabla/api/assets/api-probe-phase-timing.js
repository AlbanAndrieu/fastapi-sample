/** Presentation-only, bounded phase timing. Missing phases are not zero latency. */
const PHASES = [
  ["queue_wait_ms", "queue"],
  ["dns_probe_ms", "DNS"],
  ["http_request_ms", "HTTP"],
  ["access_secondary_ms", "Access"],
];

function milliseconds(value) {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 60000
    ? Math.round(value)
    : null;
}

function nonnegativeCount(value) {
  return Number.isInteger(value) && value >= 0 && value <= 10000
    ? value
    : null;
}

function measuredPhases(timing, prefixes) {
  if (!timing || typeof timing !== "object") return [];
  return PHASES.flatMap(([key, label]) => {
    const value = milliseconds(timing[`${prefixes}${key}`]);
    return value === null ? [] : [`${label} ${value}ms`];
  });
}

/** Copy-safe timing fields only: never propagate arbitrary backend metadata. */
export function sanitizedPhaseTiming(timing) {
  if (!timing || typeof timing !== "object") return null;
  return {
    completed_samples: nonnegativeCount(timing.completed_samples),
    ...Object.fromEntries(
      PHASES.map(([key]) => [
        `max_${key}`,
        milliseconds(timing[`max_${key}`]),
      ]),
    ),
  };
}

/** Cycle summary: maxima only across observed, completed probes. */
export function phaseSummaryText(timing, scheduled, timedOut) {
  const measured = nonnegativeCount(timing?.completed_samples);
  if (measured === null) return "";
  const total = nonnegativeCount(scheduled);
  const deadlines = nonnegativeCount(timedOut);
  const units = total !== null ? `${measured}/${total}` : String(measured);
  const parts = [`Phase measurements ${units} completed probes`];
  if (deadlines !== null && deadlines > 0) {
    parts.push(`${deadlines} deadline (phase unknown)`);
  }
  const phases = measuredPhases(timing, "max_");
  if (phases.length > 0) parts.push(`observed maxima: ${phases.join(" · ")}`);
  return parts.join(" · ");
}

/** Per-probe phase evidence; timeout/cancelled probes may have no result. */
export function phaseDetailText(timing) {
  const phases = measuredPhases(timing, "");
  if (phases.length === 0) return "";
  const count = nonnegativeCount(timing?.http_request_count);
  if (count !== null) phases.push(`${count} HTTP request${count === 1 ? "" : "s"}`);
  return `phases: ${phases.join(" · ")}`;
}
