import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isRetiredCheck } from "../../nabla/api/assets/api-retired-check.js";

const asset = (name) =>
  readFileSync(
    new URL(`../../nabla/api/assets/${name}`, import.meta.url),
    "utf8",
  );

test("retirement requires explicit edge or lifecycle evidence, never a failed probe", () => {
  assert.equal(
    isRetiredCheck("pfsense", {
      skipped: true,
      reason: "pfSense retired; Freebox is the active network edge",
    }),
    true,
  );
  assert.equal(
    isRetiredCheck("pfsense", { skipped: true, reason: "API key missing" }),
    false,
  );
  assert.equal(
    isRetiredCheck("pfsense", { reachable: false, state: "fail" }),
    false,
  );
  assert.equal(isRetiredCheck("pfsense", { state: "unknown" }), false);
  assert.equal(isRetiredCheck("any", { lifecycle_state: "retired" }), true);
});

test("retired is pink, filtered as historical, not counted as an issue", () => {
  assert.match(
    asset("api-health-core.js"),
    /isRetiredCheck\(key, check\)\) return "pink"/,
  );
  assert.match(asset("api-service-groups.js"), /return "Retired"/);
  assert.match(
    asset("api-service-filter.js"),
    /status !== "operational" && status !== "retired"/,
  );
  assert.match(asset("api-health.css"), /\.health-led--pink/);
  assert.match(asset("api-health.css"), /\.health-row-primary--pink/);
});

test("obsolete pfBlockerNG and Snort are not statically advertised by the active edge legend", () => {
  const legend = asset("api-platform-legend.js");
  assert.doesNotMatch(legend, /\["🚫", "pfBlockerNG"\]/);
  assert.match(legend, /Network edge · current router evidence/);
  const posture = asset("api-pfsense-security-posture.js");
  assert.match(posture, /container\.hidden = true/);
  assert.match(posture, /pfsense retired/i);
});
