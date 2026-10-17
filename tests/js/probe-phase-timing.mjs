/** Hermetic fan-out timing presentation regressions (no network). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const script = readFileSync(process.argv[2], "utf8");
const url =
  "data:text/javascript;base64," + Buffer.from(script).toString("base64");
const {
  deadlineDetailText,
  deadlinePhaseSummaryText,
  phaseSummaryText,
  phaseDetailText,
  sanitizedDeadlinePhaseCounts,
  sanitizedPhaseTiming,
} = await import(url);

const copied = sanitizedPhaseTiming({
  completed_samples: 1,
  max_queue_wait_ms: 17,
  max_dns_probe_ms: null,
  authorization: "Bearer NEVER_LEAK",
  url: "https://PRIVATE.example.invalid",
});
assert.deepEqual(copied, {
  completed_samples: 1,
  max_queue_wait_ms: 17,
  max_dns_probe_ms: null,
  max_http_request_ms: null,
  max_access_secondary_ms: null,
});
assert.doesNotMatch(JSON.stringify(copied), /NEVER_LEAK|PRIVATE/);
assert.equal(sanitizedPhaseTiming(null), null);

assert.equal(phaseSummaryText(null, 12, 11), "");
assert.equal(phaseDetailText(null), "");

const summary = phaseSummaryText(
  {
    completed_samples: 1,
    max_queue_wait_ms: 187,
    max_dns_probe_ms: 47,
    max_http_request_ms: 614,
    max_access_secondary_ms: null,
  },
  12,
  11,
);
assert.match(summary, /1\/12 completed probes/);
assert.match(summary, /11 deadline \(phase unknown\)/);
assert.match(summary, /queue 187ms/);
assert.match(summary, /DNS 47ms/);
assert.match(summary, /HTTP 614ms/);
assert.doesNotMatch(summary, /Access/);
assert.doesNotMatch(summary, /Access 0ms/);

const result = phaseDetailText({
  queue_wait_ms: 4,
  dns_probe_ms: 0,
  http_request_ms: 15,
  access_secondary_ms: 8,
  http_request_count: 2,
});
assert.match(result, /queue 4ms/);
assert.match(result, /DNS 0ms/); // A real measured zero is valid.
assert.match(result, /HTTP 15ms/);
assert.match(result, /Access 8ms/);
assert.match(result, /2 HTTP requests/);

assert.equal(phaseDetailText({ dns_probe_ms: null }), "");
assert.equal(phaseDetailText({ http_request_ms: "0", queue_wait_ms: -1 }), "");
assert.equal(
  phaseSummaryText(
    { completed_samples: true, max_dns_probe_ms: Infinity },
    12,
    0,
  ),
  "",
);
assert.equal(
  phaseSummaryText({ completed_samples: 0, max_queue_wait_ms: null }, 12, 12),
  "Phase measurements 0/12 completed probes · 12 deadline (phase unknown)",
);

const phaseCounts = {
  not_started: 1,
  waiting_on_semaphore: 3,
  dns_in_progress: 4,
  head_get_in_progress: 2,
  access_secondary_in_progress: 1,
  tcp_in_progress: 0,
  authorization: "Bearer NEVER_LEAK",
  target: "https://PRIVATE.example.invalid",
};
const sanitizedCounts = sanitizedDeadlinePhaseCounts(phaseCounts);
assert.deepEqual(sanitizedCounts, {
  not_started: 1,
  waiting_on_semaphore: 3,
  dns_in_progress: 4,
  head_get_in_progress: 2,
  access_secondary_in_progress: 1,
  tcp_in_progress: 0,
});
assert.doesNotMatch(JSON.stringify(sanitizedCounts), /NEVER_LEAK|PRIVATE/);
assert.equal(sanitizedDeadlinePhaseCounts(null), null);
assert.equal(sanitizedDeadlinePhaseCounts([]), null);
assert.match(deadlinePhaseSummaryText(phaseCounts), /DNS 4/);
assert.match(deadlinePhaseSummaryText(phaseCounts), /queue 3/);
assert.match(
  phaseSummaryText({ completed_samples: 1 }, 12, 11, phaseCounts),
  /unfinished at deadline: /,
);
assert.equal(
  deadlineDetailText({
    timed_out: true,
    probe_source: "deadline",
    deadline_phase: "dns_in_progress",
    deadline_phase_elapsed_ms: 1120,
  }),
  "deadline during DNS (at least 1120ms in phase)",
);
assert.equal(
  deadlineDetailText({
    probe_source: "memory",
    state: "ok",
    last_probe_attempt_deadline_phase: "waiting_on_semaphore",
    last_probe_attempt_deadline_phase_elapsed_ms: 830,
  }),
  "last probe attempt timed out during queue (at least 830ms in phase)",
);
assert.equal(
  deadlineDetailText({
    timed_out: true,
    deadline_phase: "https://PRIVATE.example.invalid",
    deadline_phase_elapsed_ms: "Bearer NEVER_LEAK",
  }),
  "",
);
