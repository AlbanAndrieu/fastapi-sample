import assert from "node:assert/strict";
import { test } from "node:test";

import {
  gatusCoverage,
  gatusCatalogueCoverage,
  gatusServiceEvidence,
} from "../../nabla/api/assets/api-service-gatus-coverage.js";
import { serviceRelations } from "../../nabla/api/assets/api-service-relations.js";
import { evidenceAdvice, evidenceCounts, evidenceGroup, requestedServiceId, sanitizedEvidence } from "../../nabla/api/assets/api-service-evidence-ux.js";
import { serviceTelemetry } from "../../nabla/api/assets/api-service-telemetry.js";

const now = Date.parse("2026-10-25T01:00:00Z");
function snapshot(services, overrides = {}) {
  return { platform_metrics: {
    generated_at: new Date(now).toISOString(),
    synthetic_probes: {
      state: "observed",
      gatus_up: 1,
      truncated: false,
      services,
    },
    ...overrides,
  }};
}

test("Gatus monitor failure is not confused with Gatus scrape up", () => {
  const s = snapshot({
    gatus: { HTTP: { success: 1 } },
    "fastapi-sample": { HTTP: { success: 0 } },
    redis: { TCP: { success: 1 } },
  });
  const report = gatusCoverage(s, now);
  assert.equal(report.state, "observed");
  assert.equal(report.up, 2);
  assert.equal(report.down, 1);
  assert.deepEqual(report.failures, [
    { id: "fastapi-sample", type: "HTTP", status: "down" },
  ]);
  assert.equal(gatusServiceEvidence(s, "fastapi-sample", now).status, "down");
  assert.equal(gatusServiceEvidence(s, "missing", now).status, "not_observed");
});

test("Gatus missing, truncated or stale snapshot cannot be marked green", () => {
  assert.equal(gatusCoverage(null, now).state, "unverified");
  assert.equal(gatusCoverage(snapshot({}, {
    generated_at: "2026-10-24T00:00:00Z",
  }), now).state, "unverified");
  const truncated = snapshot({ gatus: { TCP: { success: 1 } } });
  truncated.platform_metrics.synthetic_probes.truncated = true;
  assert.equal(gatusCoverage(truncated, now).state, "unverified");
  assert.equal(gatusServiceEvidence(truncated, "gatus", now).status, "unverified");
});

test("Gatus invalid labels and non-binary observations do not fabricate UP", () => {
  const s = snapshot({
    "bad id /etc/passwd": { HTTP: { success: 1 } },
    valid: { TCP: { success: true }, HTTP: { success: 0.5 } },
  });
  const result = gatusCoverage(s, now);
  assert.equal(result.up, 0);
  assert.equal(result.down, 0);
  assert.equal(result.observedServices, 1);
  assert.equal(result.unobserved, 1);
});

test("only canonical published relations become navigable", () => {
  const topology = {
    nodes: [
      { id: "gatus", name: "Gatus" },
      { id: "postgres", name: "PostgreSQL" },
      { id: "fastapi-sample", name: "FastAPI Sample" },
    ],
    relations: [
      { source: "fastapi-sample", target: "postgres",
        type: "dependsOn", strength: "required" },
      { source: "gatus", target: "fastapi-sample",
        type: "routesTo", strength: "optional" },
      { source: "gatus", target: "https://external.invalid",
        type: "routesTo", strength: "required" },
      { source: "gatus", target: "postgres",
        type: "unknownRelation", strength: "required" },
    ],
  };
  assert.deepEqual(
    serviceRelations(topology, "postgres").dependents.map(x => x.id),
    ["fastapi-sample"],
  );
  assert.deepEqual(
    serviceRelations(topology, "fastapi-sample").dependencies.map(x => x.id),
    ["postgres"],
  );
  assert.deepEqual(
    serviceRelations(topology, "fastapi-sample").dependents.map(x => x.id),
    ["gatus"],
  );
  assert.deepEqual(serviceRelations(topology, "missing"), {
    dependencies: [], dependents: [],
  });
});

test("legacy healthz row identity joins Gatus without confusing scraper status", () => {
  const snapshot = {
    platform_metrics: {
      generated_at: new Date().toISOString(),
      state: "healthy",
      metrics: { prometheus_up: { value: 1 } },
      synthetic_probes: {
        state: "observed",
        gatus_up: 1,
        truncated: false,
        services: {
          "fastapi-sample": { HTTP: { success: 0 } },
          postgres: { TCP: { success: 1 } },
          gatus: { HTTP: { success: 1 } },
        },
      },
      exporter_jobs: { postgres_exporter: 1 },
      summary: { optional_exporters: { postgres_up: 1 } },
    },
  };
  const api = serviceTelemetry(snapshot, {
    dataset: { serviceKey: "albandrieu_fastapi_sample",
               topologyId: "fastapi-sample" },
  });
  assert.equal(api.serviceId, "fastapi-sample");
  assert.equal(api.gatus.status, "down");

  const postgres = serviceTelemetry(snapshot, {
    dataset: { serviceKey: "postgres", topologyId: "postgres" },
  });
  assert.equal(postgres.serviceId, "postgresql");
  assert.equal(postgres.gatus.status, "up");
  assert.equal(postgres.functional.status, "up");

  const monitor = serviceTelemetry(snapshot, {
    dataset: { serviceKey: "albandrieu_gatus", topologyId: "gatus" },
  });
  assert.equal(monitor.gatusFleet.tone, "fail");
  assert.equal(monitor.gatusFleet.status, "probes_down");
});

test("Gatus catalogue parity remains unverified even when labelled samples are UP", () => {
  const s = snapshot({
    gatus: { HTTP: { success: 1 } },
    redis: { TCP: { success: 1 } },
  });
  const coverage = gatusCatalogueCoverage(s, ["gatus", "redis", "postgres"], now);
  assert.equal(coverage.state, "observed");
  assert.equal(coverage.catalogueTotal, 3);
  assert.equal(coverage.withSamples, 2);
  assert.deepEqual(coverage.withoutSamples, ["postgres"]);
  assert.equal(coverage.declaredMonitors, null);
  assert.equal(coverage.status, "partial");
  const missing = gatusCatalogueCoverage(null, ["gatus"], now);
  assert.equal(missing.withSamples, 0);
  assert.equal(missing.state, "unverified");
});

test("categorize actionable protocol evidence and avoid interpreting no metric as success", () => {
  assert.equal(evidenceGroup({kind: "dns", label: "DNS", detail: "NXDOMAIN"}), "DNS");
  assert.equal(evidenceGroup({kind: "http", detail: "HTTP 403 Cloudflare Access"}), "Access / tokens");
  assert.equal(evidenceGroup({kind: "metrics", label: "Postgres exporter"}), "Metrics / exporters");
  assert.equal(evidenceGroup({kind: "gatus", detail: "Gatus check down"}), "Gatus checks");
  assert.match(evidenceAdvice({kind: "http", tone: "fail", detail: "HTTP 401"}).reason, /401/);
  assert.match(evidenceAdvice({kind: "http", tone: "fail", detail: "HTTP 403"}).action, /Access/);
  assert.deepEqual(evidenceCounts([
    {tone:"fail"}, {tone:"warn"}, {tone:"unknown"}, {tone:"ok"}, {tone:"fail",disabled:true},
  ]), {failed:1, warning:1, unknown:1, up:1, notRun:1});
});

test("do not leak credentials through a probe diagnostic", () => {
  const raw = "HTTP 403 Authorization: Bearer abcDEF.123 C F CF-Access-Client-Secret=very-secret " +
    "https://operator:pass@internal.example/path?token=123&password=abc";
  const safe = sanitizedEvidence(raw);
  for (const secret of ["abcDEF.123", "very-secret", "operator:pass", "token=123", "password=abc"]) {
    assert.equal(safe.includes(secret), false, secret);
  }
  assert.match(safe, /redacted/);
});

test("only valid canonical service IDs may be used for deep links", () => {
  assert.equal(requestedServiceId("?q=test&service=gatus"), "gatus");
  assert.equal(requestedServiceId("?service=component%3Adefault%2Fpostgres"), "component:default/postgres");
  assert.equal(requestedServiceId("?service=https%3A%2F%2Fprivate.example"), null);
  assert.equal(requestedServiceId("?service=../../admin"), null);
  assert.equal(requestedServiceId("?service="), null);
});

test("Gatus exposes only valid bounded monitor duration and 5m availability", () => {
  const s = snapshot({
    gatus: { HTTP: { success: 1, duration_seconds: 0.125, availability_ratio_5m: 0.95 } },
    redis: { TCP: { success: 0, duration_seconds: -12, availability_ratio_5m: 2 } },
  });
  const fleet = gatusCoverage(s, now);
  assert.equal(fleet.successes[0].durationMs, 125);
  assert.equal(fleet.successes[0].availability, 0.95);
  assert.equal("durationMs" in fleet.failures[0], false);
  assert.equal("availability" in fleet.failures[0], false);
  const details = gatusServiceEvidence(s, "gatus", now);
  assert.equal(details.probes[0].durationMs, 125);
  // serviceTelemetry evaluates freshness against the real clock.
  // Preserve the fixed clock for gatusCoverage fixture assertions above.
  s.platform_metrics.generated_at = new Date().toISOString();
  const row = { dataset: { serviceKey: "gatus", topologyId: "gatus" } };
  const telemetry = serviceTelemetry(s, row);
  assert.match(telemetry.gatus.detail, /125 ms/);
});
