/** Presentation-only, bounded phase timing. Missing phases are not zero latency. */
const PHASES = [
  ["queue_wait_ms", "queue"],
  ["dns_probe_ms", "DNS"],
  ["http_request_ms", "HTTP"],
  ["access_secondary_ms", "Access"],
];

const DEADLINE_PHASE_LABELS = [
  ["not_started", "not started"],
  ["waiting_on_semaphore", "queue"],
  ["dns_in_progress", "DNS"],
  ["head_get_in_progress", "HTTP"],
  ["access_secondary_in_progress", "Access"],
  ["tcp_in_progress", "TCP"],
];

export function sanitizedDeadlinePhaseCounts(counts) {
  if (!counts || typeof counts !== "object" || Array.isArray(counts)) return null;
  return Object.fromEntries(
    DEADLINE_PHASE_LABELS.map(([key]) => [key, nonnegativeCount(counts[key])]),
  );
}

export function deadlinePhaseSummaryText(counts) {
  const safe = sanitizedDeadlinePhaseCounts(counts);
  if (!safe) return "";
  const entries = DEADLINE_PHASE_LABELS.flatMap(([key, label]) =>
    safe[key] > 0 ? [`${label} ${safe[key]}`] : [],
  );
  return entries.length ? `unfinished at deadline: ${entries.join(" · ")}` : "";
}

function phaseDeadlineText(phase, elapsed, lastAttempt = false) {
  const allowed = DEADLINE_PHASE_LABELS.find(([key]) => key === phase);
  if (!allowed) return "";
  const ms = milliseconds(elapsed);
  const duration = ms === null ? "" : ` (at least ${ms}ms in phase)`;
  const prefix = lastAttempt ? "last probe attempt timed out during" : "deadline during";
  return `${prefix} ${allowed[1]}${duration}`;
}

export function deadlineDetailText(row) {
  if (!row || typeof row !== "object") return "";
  if (row.timed_out === true && row.probe_source !== "memory") {
    return phaseDeadlineText(row.deadline_phase, row.deadline_phase_elapsed_ms);
  }
  if (row.probe_source === "memory") {
    return phaseDeadlineText(
      row.last_probe_attempt_deadline_phase,
      row.last_probe_attempt_deadline_phase_elapsed_ms,
      true,
    );
  }
  return "";
}

function milliseconds(value) {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 60000
    ? Math.round(value)
    : null;
}

function nonnegativeCount(value) {
  return Number.isInteger(value) && value >= 0 && value <= 10000 ? value : null;
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
      PHASES.map(([key]) => [`max_${key}`, milliseconds(timing[`max_${key}`])]),
    ),
  };
}

/** Cycle summary: maxima only across observed, completed probes. */
export function phaseSummaryText(timing, scheduled, timedOut, deadlinePhases = null) {
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
  const unfinished = deadlinePhaseSummaryText(deadlinePhases);
  if (unfinished) parts.push(unfinished);
  return parts.join(" · ");
}

/** Per-probe phase evidence; timeout/cancelled probes may have no result. */
export function phaseDetailText(timing) {
  const phases = measuredPhases(timing, "");
  if (phases.length === 0) return "";
  const count = nonnegativeCount(timing?.http_request_count);
  if (count !== null)
    phases.push(`${count} HTTP request${count === 1 ? "" : "s"}`);
  return `phases: ${phases.join(" · ")}`;
}
