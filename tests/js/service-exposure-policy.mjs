import assert from "node:assert/strict";
import { test } from "node:test";

import { exposurePolicyPresentation } from "../../nabla/api/assets/api-service-exposure-policy.js";

test("internal-only unreachable endpoint is compliant only with observed policy", () => {
  const checked = exposurePolicyPresentation({
    external: false, policy_status: "ok", reachable: false,
  });
  assert.equal(checked.label, "Private OK");
  assert.equal(checked.state, "ok");
  const declaredOnly = exposurePolicyPresentation({
    external: false, reachable: false, policy_status: "unknown",
  });
  assert.equal(declaredOnly.state, "unknown");
});

test("forbidden HTTP 403 is still a public entry point for a private service", () => {
  const result = exposurePolicyPresentation({
    external: false, reachable: true, http_status: 403,
    policy_status: "ok",
  });
  assert.equal(result.state, "fail");
  assert.equal(result.label, "Exposure !");
  assert.match(result.detail, /401\/403/);
});

test("observed Cloudflare ingress for an internal-only service violates intent", () => {
  const r = exposurePolicyPresentation({
    external: false, reachable: null, policy_status: "unknown",
    cloudflare_tunnel_observed: true,
  });
  assert.equal(r.state, "fail");
  assert.match(r.summary, /Unexpected public/);
});

test("direct Internet exposure stays a warning even if catalog explicitly allows it", () => {
  const result = exposurePolicyPresentation({
    external: true, tunnel_secure: false, reachable: true,
    policy_status: "warn", security_exception: "approved operator exception",
  });
  assert.equal(result.state, "warn");
  assert.equal(result.label, "Direct · Risk");
});

test("Cloudflare routing is not verified security without control-plane proof", () => {
  const observed = {
    external: true, tunnel_secure: true, policy_status: "ok",
  };
  assert.equal(exposurePolicyPresentation(observed).state, "unknown");
  assert.equal(
    exposurePolicyPresentation(observed, { cloudflareConfirmed: true }).label,
    "Protected",
  );
});

test("explicit policy failures outrank security declarations", () => {
  const result = exposurePolicyPresentation({
    external: true, tunnel_secure: true, policy_status: "fail",
  }, { cloudflareConfirmed: false });
  assert.equal(result.state, "fail");
});

test("missing skipped and stale reports are never green", () => {
  assert.equal(exposurePolicyPresentation(null).state, "unknown");
  assert.equal(exposurePolicyPresentation({
    external: false, skipped: true, policy_status: "ok", reachable: false,
  }).state, "unknown");
  assert.equal(exposurePolicyPresentation({
    external: true, stale: true, policy_status: "ok",
  }).state, "unknown");
});

test("model does not pass user-controlled URL, token or raw error into labels", () => {
  const checked = exposurePolicyPresentation({
    external: true, tunnel_secure: true, policy_status: "warn",
    token: "SECRET_VALUE", url: "https://private.example.invalid",
  });
  assert.doesNotMatch(JSON.stringify(checked), /SECRET_VALUE|private\.example/);
});
