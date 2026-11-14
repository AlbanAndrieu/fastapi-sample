import assert from "node:assert/strict";
import { test } from "node:test";
import { exposurePolicyPresentation } from "../../nabla/api/assets/api-service-exposure-policy.js";
import {
  expectedHttpFailure,
  firstObservedCheck,
  httpObservationTone,
} from "../../nabla/api/assets/api-service-http-auth.js";
import {
  classifySick,
  detailSickText,
} from "../../nabla/api/assets/api-sickz-row-state.js";

test("internal-only service: unanswered public HTTP is expected (blue)", () => {
  const litellm = {
    id: "litellm",
    exposure_intent: "internal",
    reachable: false,
    http_status: 0,
    error: "[Errno -3] Temporary failure in name resolution",
  };
  assert.equal(httpObservationTone(litellm, "litellm"), "expected");
  assert.match(expectedHttpFailure(litellm).detail, /by design/);
  const sickz = {
    external: false,
    reachable: false,
    expected_reachable: false,
    alias_results: { "https://litellm.albandrieu.com/": { reachable: false } },
  };
  assert.equal(httpObservationTone(sickz, "litellm"), "expected");
});

test("a catalogue placeholder is not evidence and never hides a real answer", () => {
  const placeholder = {
    exposure_intent: "internal",
    reachable: false,
    http_status: 0,
    state: "unknown",
  };
  assert.equal(expectedHttpFailure(placeholder), null);
  const sickz403 = { external: false, reachable: true, http_status: 403 };
  assert.equal(firstObservedCheck(placeholder, sickz403), sickz403);
  assert.equal(
    httpObservationTone(firstObservedCheck(placeholder, sickz403), "x"),
    "warn",
  );
  const skipped = { skipped: true, reason: "LITELLM_HEALTHZ_URL empty" };
  assert.equal(firstObservedCheck(skipped, placeholder), placeholder);
});

test("an internal service that answers publicly is never expected", () => {
  const answered = {
    exposure_intent: "internal",
    reachable: true,
    http_status: 403,
  };
  assert.equal(expectedHttpFailure(answered), null);
  assert.equal(httpObservationTone(answered, "x"), "warn");
});

test("a public service that fails stays a failure", () => {
  const publicDown = { exposure_intent: "public", reachable: false };
  assert.equal(expectedHttpFailure(publicDown), null);
  assert.equal(httpObservationTone(publicDown, "x"), "fail");
  assert.equal(httpObservationTone({ reachable: false }, "x"), "fail");
});

test("LAN-only service without public hostname is expected, not 'not verified'", () => {
  const redis = exposurePolicyPresentation({
    external: false,
    policy_status: "unknown",
    public_route: false,
  });
  assert.equal(redis.state, "expected");
  assert.equal(redis.tone, "expected");
  assert.match(redis.summary, /by design/);
  const declaredRoute = exposurePolicyPresentation({
    external: false,
    policy_status: "unknown",
    public_route: true,
  });
  assert.equal(declaredRoute.state, "unknown");
});

test("outside-in check skipped on LAN for an internal service is expected", () => {
  const skipped = exposurePolicyPresentation({
    external: false,
    skipped: true,
  });
  assert.equal(skipped.state, "expected");
  // A design fact holds on a stale snapshot; observed public ingress still fails.
  const stale = exposurePolicyPresentation({
    external: false,
    skipped: true,
    stale: true,
  });
  assert.equal(stale.state, "expected");
  const leaked = exposurePolicyPresentation({
    external: false,
    public_route: false,
    cloudflare_tunnel_observed: true,
  });
  assert.equal(leaked.state, "fail");
  const publicSkip = exposurePolicyPresentation({
    external: true,
    skipped: true,
  });
  assert.equal(publicSkip.state, "unknown");
});

test("sickz LAN skip is blue for internal endpoints and never amber", () => {
  const litellm = {
    skipped: true,
    expected_reachable: false,
    external: false,
    reason: "Not probed (LAN / internal network skip).",
  };
  assert.equal(classifySick(litellm), "blue");
  assert.match(detailSickText(litellm), /^Expected by design/);
  assert.doesNotMatch(detailSickText(litellm), /Policy enrichment unavailable/);
  assert.equal(
    classifySick({ skipped: true, expected_reachable: true }),
    "gray",
  );
  assert.equal(classifySick({ skipped: true }), "gray");
});
