import assert from "node:assert/strict";
import { test } from "node:test";
import {
  expectedAnonymousAuth, httpObservationTone,
} from "../../nabla/api/assets/api-service-http-auth.js";

test("Garage S3 GET / anonymous 403 is blue transport evidence, not operational success", () => {
  const check = {
    url: "http://172.17.0.24:3900/", http_status: 403,
    reachable: false,
  };
  assert.equal(expectedAnonymousAuth("garage", check)?.tone, "info");
  assert.equal(httpObservationTone(check, "garage"), "info");
  assert.match(expectedAnonymousAuth("garage", check).detail, /readiness.*not proven/);
});

test("LiteLLM /health HTTP 401 is expected auth, not HTTP failure", () => {
  const check = {
    url: "http://172.17.0.24:4000/health", http_status: 401,
    reachable: false,
  };
  assert.equal(expectedAnonymousAuth("litellm", check)?.status, 401);
  assert.equal(httpObservationTone(check, "litellm"), "info");
});

test("missing, stale, redirected and credentials-submitted results never become expected auth", () => {
  for (const extra of [
    { auth_attempted: true }, { authenticated_http_status: 401 },
    { cloudflare_service_auth_attempted: true }, { stale: true },
    { probe_stale: true }, { failure_stage: "tcp_connect" },
    { path: "/metrics" }, { public_probe_auth_mode: "authenticated" },
  ]) {
    assert.equal(expectedAnonymousAuth("litellm", {
      http_status: 401, url: "http://172.17.0.24:4000/health", ...extra,
    }), null);
  }
  assert.equal(expectedAnonymousAuth("unknown", {
    http_status: 401,
  }), null);
});

test("401/403 remain warnings without declared anonymous expectation", () => {
  assert.equal(httpObservationTone({
    http_status: 401, reachable: false,
  }, "fastapi-sample"), "warn");
  assert.equal(httpObservationTone({
    http_status: 403, reachable: false,
  }, "litellm"), "warn");
  assert.equal(httpObservationTone({
    http_status: 403, reachable: false, auth_attempted: true,
  }, "garage"), "warn");
  assert.equal(httpObservationTone({
    http_status: 503, reachable: false,
  }, "garage"), "fail");
  assert.equal(httpObservationTone({
    http_status: 200, reachable: true,
  }, "garage"), "ok");
  assert.equal(httpObservationTone({
    reachable: false,
  }, "garage"), "fail");
  assert.equal(httpObservationTone(null, "garage"), "unknown");
});

test("auth classification is independent of security ingress policy", () => {
  const check = { http_status: 403, url: "http://172.17.0.24:3900/" };
  assert.equal(httpObservationTone(check, "garage"), "info");
  // A separate /sickz security failure must remain visible.
  assert.equal(check.policy_status, undefined);
});
