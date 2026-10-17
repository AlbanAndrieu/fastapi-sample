/** Hermetic fan-out timing presentation regressions (no network). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const script = readFileSync(process.argv[2], "utf8");
const url =
  "data:text/javascript;base64," + Buffer.from(script).toString("base64");
const { phaseSummaryText, phaseDetailText } = await import(url);

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
assert.equal(
  phaseDetailText({ http_request_ms: "0", queue_wait_ms: -1 }),
  "",
);
assert.equal(
  phaseSummaryText(
    { completed_samples: true, max_dns_probe_ms: Infinity },
    12,
    0,
  ),
  "",
);
assert.equal(
  phaseSummaryText(
    { completed_samples: 0, max_queue_wait_ms: null },
    12,
    12,
  ),
  "Phase measurements 0/12 completed probes · 12 deadline (phase unknown)",
);
