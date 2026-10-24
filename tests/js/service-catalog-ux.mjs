import assert from "node:assert/strict";
import { test } from "node:test";

import {
  gatusCoverage,
  gatusServiceEvidence,
} from "../../nabla/api/assets/api-service-gatus-coverage.js";
import { serviceRelations } from "../../nabla/api/assets/api-service-relations.js";
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
