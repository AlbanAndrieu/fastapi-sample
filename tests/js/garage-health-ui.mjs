/** Hermetic Garage projection checks; runs via Node without network access. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(process.argv[2], "utf8");
const url =
  "data:text/javascript;base64," + Buffer.from(source).toString("base64");
const { includeObservedGarageChecks } = await import(url);

const checks = { pfsense: { name: "pfSense", reachable: true } };
const homelab = {
  probe_cache: { stale: false },
  services: [
    {
      id: "garage",
      state: "ok",
      exposure_intent: "internal",
      url: "https://s3.int.albandrieu.com/",
    },
    {
      id: "garage-admin",
      state: "ok",
      exposure_intent: "internal",
      unexpected_tunnel_route: true,
      url: "https://garage-admin.albandrieu.com/",
    },
    {
      id: "garage-webui",
      state: "warn",
      exposure_intent: "public",
      url: "https://garage.albandrieu.com/path?secret=NEVER_LEAK",
    },
  ],
  internal_services: ["garage", "garage-admin", "garage-webui"].map((id) => ({
    id,
    state: "ok",
    probe_source: "origin",
    probe_stale: false,
  })),
};
const base = { checks };
const projected = includeObservedGarageChecks(base, homelab, "fresh");
assert.deepEqual(
  Object.keys(projected.checks).sort(),
  ["pfsense", "garage", "garage-admin", "garage-webui"].sort(),
);
assert.equal(projected.checks.garage.local_state, "ok");
assert.equal(projected.checks["garage-admin"].local_state, "ok");
assert.equal(projected.checks["garage-admin"].risk_state, "at_risk");
assert.equal(projected.checks["garage-admin"].url, undefined);
assert.equal(projected.checks.garage.url, undefined);
assert.equal(
  projected.checks["garage-webui"].url,
  "https://garage.albandrieu.com",
);
assert.equal(projected.checks["garage-webui"].risk_state, "at_risk");
assert.equal(base.checks.garage, undefined);

const again = includeObservedGarageChecks(projected, homelab, "fresh");
assert.equal(again.checks.garage, projected.checks.garage);

const stale = includeObservedGarageChecks(base, homelab, "stale");
assert.equal(stale.checks.garage.local_state, "unknown");
assert.equal(stale.checks.garage.reachable, null);

const timeout = structuredClone(homelab);
timeout.internal_services[0].timed_out = true;
assert.equal(
  includeObservedGarageChecks(base, timeout, "fresh").checks.garage.local_state,
  "unknown",
);
assert.equal(
  includeObservedGarageChecks(base, { services: [] }, "fresh").checks.garage,
  undefined,
);

const aliased = includeObservedGarageChecks(
  {
    checks: {
      albandrieu_garage_admin: {
        service_id: "garage-admin",
        local_state: "fail",
      },
    },
  },
  homelab,
  "fresh",
);
assert.equal(aliased.checks["garage-admin"], undefined);
assert.equal(aliased.checks.albandrieu_garage_admin.local_state, "fail");


// The public discovery card may present observed LAN runtime context but may
// not treat Gatus's monitored Uptime Kuma outcome as Gatus availability.
const observedGatus = structuredClone(homelab);
observedGatus.public_card_candidates = [{ id: "gatus", name: "Gatus" }];
observedGatus.services.push({
  id: "gatus", state: "ok", runtime_state: "RUNNING",
});
observedGatus.services.push({ id: "uptimekuma", state: "fail" });
observedGatus.internal_services.push({
  id: "gatus", state: "ok", probe_source: "origin", probe_stale: false,
});
const publicGatus = includeObservedGarageChecks(base, observedGatus, "fresh")
  .checks.gatus;
assert.equal(publicGatus.internal_state, "ok");
assert.equal(publicGatus.runtime_state, "RUNNING");
assert.equal(publicGatus.local_state, "unknown");
assert.equal(publicGatus.effective_state, "unknown");
assert.equal(publicGatus.reachable, null);
assert.match(publicGatus.warning, /independent public HTTP\/Access evidence/);
assert.equal(publicGatus.risk_state, "unknown");

const staleGatus = includeObservedGarageChecks(base, observedGatus, "stale")
  .checks.gatus;
assert.equal(staleGatus.internal_state, undefined);
assert.equal(staleGatus.runtime_state, undefined);
assert.equal(staleGatus.effective_state, "unknown");


const gatusHttp200 = structuredClone(observedGatus);
gatusHttp200.services = gatusHttp200.services.map((row) => row.id === "gatus"
  ? {
      ...row, url: "https://gatus.albandrieu.com/",
      direct_state: "ok", direct_probe_source: "origin",
      direct_probe_stale: false, http_status: 200, observation_stale: false,
    }
  : row);
const operationalGatus = includeObservedGarageChecks(base, gatusHttp200, "fresh")
  .checks.gatus;
assert.equal(operationalGatus.local_state, "ok");
assert.equal(operationalGatus.effective_state, "ok");
assert.equal(operationalGatus.reachable, true);
assert.equal(operationalGatus.http_status, 200);
assert.equal(operationalGatus.risk_state, "unknown");
assert.match(operationalGatus.warning, /Outside-in HTTP\/Access policy is unverified/);

// Uptime Kuma's observed HTTP 502 must never override Gatus's own 200.
const withFailedUptime = structuredClone(gatusHttp200);
withFailedUptime.services = withFailedUptime.services.map((row) =>
  row.id === "uptimekuma" ? { ...row, state: "fail", http_status: 502 } : row);
assert.equal(
  includeObservedGarageChecks(base, withFailedUptime, "fresh")
    .checks.gatus.effective_state,
  "ok",
);

// No positive state from a stale, non-2xx or unrelated public origin.
for (const invalid of [
  { http_status: 502 },
  { direct_probe_stale: true },
  { observation_stale: true },
  { url: "https://other.albandrieu.com" },
  { direct_state: "fail" },
]) {
  const candidate = structuredClone(gatusHttp200);
  candidate.services = candidate.services.map((row) => row.id === "gatus"
    ? { ...row, ...invalid } : row);
  const check = includeObservedGarageChecks(base, candidate, "fresh").checks.gatus;
  assert.equal(check.effective_state, "unknown");
  assert.equal(check.reachable, null);
}
