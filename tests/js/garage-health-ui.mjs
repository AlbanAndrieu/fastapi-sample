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
