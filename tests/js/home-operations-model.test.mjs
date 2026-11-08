import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  appendAlignedPair,
  alignedHistoryCorrelation,
  projectPrometheusHistory,
  pearsonCorrelation,
  appendObservation,
  projectFleet,
  projectLatency,
  projectProbes,
  projectResources,
  projectSecurity,
  sparklinePath,
} from "../../nabla/api/assets/home-operations-model.js";

const NOW = Date.parse("2026-11-04T17:30:00Z");
const AT = "2026-11-04T17:29:45Z";

function board(overrides = {}) {
  return {
    state: "fresh",
    generated_at: AT,
    age_seconds: 15,
    homelab: {
      probe_summary: {
        public: { eligible: 4, evidence: { known: 2 } },
        internal: { enabled: false, eligible: 44, evidence: { known: 36 } },
      },
      public_probe_results: [
        {
          id: "sample", state: "ok", probe_source: "origin",
          probe_stale: false, latency_ms: 97,
          probe_observed_at: AT,
        },
      ],
      connection_matrix: { rows: [{ id: "cloudflare_access", state: "warn" }] },
    },
    ...overrides,
  };
}

test("public fleet uses verified states only", () => {
  const fresh = {
    schemaVersion: 2, model: "public-service-overview",
    catalogSource: "backstage-v2", boardState: "fresh",
    services: [
      { name: "Gatus", kind: "Component", state: "ok" },
      { name: "TrueNAS", kind: "Resource", state: "fail" },
    ],
  };
  assert.equal(projectFleet(fresh).counts.ok, 1);
  assert.equal(projectFleet(fresh).counts.fail, 1);
  const stale = projectFleet({ ...fresh, boardState: "stale" });
  assert.deepEqual(stale.counts, { ok: 0, warn: 0, fail: 0, unknown: 2 });
  assert.equal(projectFleet({ ...fresh, services: [{ name: "X", kind: "API", state: "green" }] }), null);
});

test("probe coverage excludes disabled LAN and never invents healthy slots", () => {
  const coverage = projectProbes(board(), NOW);
  assert.equal(coverage.eligible, 4);
  assert.equal(coverage.known, 2);
  assert.equal(coverage.healthy, 1);
  assert.equal(coverage.coverage, 50);
  assert.equal(coverage.healthyCoverage, 25);
  assert.equal(coverage.unobserved, 2);
});

test("no probe or security result survives an outdated board", () => {
  const stale = board({ generated_at: "2026-11-04T17:20:00Z" });
  assert.equal(projectProbes(stale, NOW), null);
  assert.equal(projectLatency(stale, NOW), null);
  assert.equal(projectSecurity(stale, NOW), null);
});

test("separate HTTP duration from actual network RTT", () => {
  const latency = projectLatency(board(), NOW);
  assert.equal(latency.valueMs, 97);
  assert.match(latency.source, /not ICMP RTT/);
  assert.equal(projectLatency(board({ state: "stale" }), NOW), null);
});

test("resource units retain their actual meanings", () => {
  const telemetry = {
    state: "partial", generated_at: AT,
    resources: {
      sample: {
        cpu_cores: 0.5,
        memory_bytes: 209715200,
        network_bytes_per_second: 10240,
      },
    },
  };
  assert.deepEqual(projectResources(telemetry, NOW), {
    observedAt: AT, cpuCores: 0.5, memoryMiB: 200,
    networkKiBs: 10, source: "Prometheus / TrueNAS cAdvisor",
  });
  assert.equal(projectResources({
    ...telemetry, generated_at: "2026-11-04T17:00:00Z",
  }, NOW), null);
});

test("ambiguous containers or missing data do not produce synthetic metrics", () => {
  const sample = { cpu_cores: 0.2, memory_bytes: 100, network_bytes_per_second: 200 };
  assert.equal(projectResources({
    state: "healthy", generated_at: AT,
    resources: { sample, "fastapi-sample": sample },
  }, NOW), null);
  assert.equal(projectResources({
    state: "healthy", generated_at: AT, resources: { sample: {} },
  }, NOW).cpuCores, null);
  assert.equal(projectResources({ state: "not_configured" }, NOW), null);
});

test("security checks use connection matrix evidence but never infer compliance", () => {
  const value = projectSecurity(board(), NOW);
  assert.equal(value.checks.find((v) => v.id === "cloudflare_access").state, "warn");
  assert.equal(value.checks.find((v) => v.id === "truenas_api").state, "unknown");
  assert.equal(value.policyObserved, 0);
  assert.equal(value.issues, 0);
});

test("observed policy violations are counted independently from service health", () => {
  const value = projectSecurity(board({
    sickz: {
      checks: {
        safe: { security_policy_status: "ok" },
        exposed: { security_policy_status: "fail" },
        missing: { security_policy_status: "unknown" },
      },
    },
  }), NOW);
  assert.equal(value.policyObserved, 2);
  assert.deepEqual(value.policyCounts, { ok: 1, warn: 0, fail: 1 });
});

test("one browser refresh never duplicates a chart point", () => {
  const initial = appendObservation([], AT, 21);
  assert.equal(initial.length, 1);
  const revised = appendObservation(initial, AT, 22);
  assert.equal(revised.length, 1);
  assert.equal(revised[0].value, 22);
  assert.equal(appendObservation([], AT, null).length, 0);
  assert.equal(appendObservation([], AT, Number.NaN).length, 0);
  assert.equal(sparklinePath(initial), null);
  assert.match(sparklinePath([
    { at: AT, value: 21 },
    { at: "2026-11-04T17:29:55Z", value: 23 },
  ]), /^M7\.0 /);
});

test("home only reveals detailed fetch after owner session, never auto-polls sensor SSE", () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const html = readFileSync(new URL("../../templates/index.html", import.meta.url), "utf8");
  const source = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url), "utf8",
  );
  assert.match(html, /Operations Overview/);
  assert.doesNotMatch(html, /(?:tempChart|humidityChart|pressureChart|sensor_update|sse-connect)/);
  assert.match(source, /sessionResult\.value\?\.authenticated === true/);
  assert.match(source, /if \(!owner\)/);
  assert.match(source, /fetchJSON\("\/api\/health-board"/);
  assert.match(source, /fetchJSON\("\/api\/topology-telemetry"/);
  assert.doesNotMatch(source, /\/(?:stream|charts|sensor-data)/);
  assert.equal(typeof root, "string");
});

test("CPU–HTTP correlation requires six independent, time-aligned pairs", () => {
  let pairs = [];
  for (let i = 0; i < 6; i += 1) {
    const at = new Date(NOW - i * 60000).toISOString();
    const candidate = appendAlignedPair(pairs, {
      cpuCores: i + 1, observedAt: at,
    }, {
      valueMs: 10 * (i + 1), observedAt: new Date(Date.parse(at) + 5000).toISOString(),
    });
    pairs = candidate;
  }
  assert.equal(pairs.length, 6);
  assert.equal(pearsonCorrelation(pairs), 1);
  const same = appendAlignedPair(pairs, {
    cpuCores: 6, observedAt: new Date(NOW).toISOString(),
  }, {
    valueMs: 60, observedAt: new Date(NOW + 5000).toISOString(),
  });
  assert.equal(same.length, 6);
  assert.equal(pearsonCorrelation(pairs.slice(0, 5)), null);
});

test("correlation never pairs measurements with 30+ seconds skew", () => {
  const pairs = appendAlignedPair([], {
    cpuCores: 0.5, observedAt: AT,
  }, {
    valueMs: 32, observedAt: "2026-11-04T17:28:00Z",
  });
  assert.equal(pairs.length, 0);
  assert.equal(pearsonCorrelation(
    Array.from({ length: 6 }, (_, index) => ({ cpu: 0, httpMs: index + 1 })),
  ), null);
});

test("repeated CPU or HTTP sample cannot inflate the correlation sample count", () => {
  const initial = appendAlignedPair([], {
    cpuCores: 0.4, observedAt: AT,
  }, {
    valueMs: 50, observedAt: "2026-11-04T17:29:40Z",
  });
  assert.equal(appendAlignedPair(initial, {
    cpuCores: 0.4, observedAt: AT,
  }, {
    valueMs: 70, observedAt: "2026-11-04T17:29:42Z",
  }).length, 1);
  assert.equal(pearsonCorrelation(
    Array.from({ length: 6 }, (_, i) => ({ cpu: i === 0 ? 1e300 : i, httpMs: 100 + i })),
  ), null);
});

test("standalone home imports no remote CDN or inline script", () => {
  const root = readFileSync(new URL("../../templates/index.html", import.meta.url), "utf8");
  assert.match(root, /<html lang="fr">/);
  assert.match(root, /src="\/api\/assets\/home-operations.js"/);
  assert.doesNotMatch(root, /\{% extends|https:\/\/|cdn\.jsdelivr|unpkg|chart\.js/i);
});

function historyFixture(overrides = {}) {
  const end = Math.floor(NOW / 1000 / 60) * 60;
  return {
    schema_version: 1,
    model: "owner-operations-history",
    window: "1h",
    step_seconds: 60,
    start: end - 3600,
    end,
    state: "partial",
    source: "prometheus_query_range",
    synthetic: false,
    series: {
      cpu_cores: [[end - 120, 0.2], [end - 60, 0.3], [end, 0.4]],
      memory_bytes: [[end, 104857600]],
      network_bytes_per_second: [[end, 8192]],
      http_p95_ms: [[end - 120, 20], [end - 60, 30], [end, 40]],
      gatus_availability_percent: [],
    },
    ...overrides,
  };
}

test("server range history accepts only bounded, real Prometheus samples", () => {
  const value = projectPrometheusHistory(historyFixture(), NOW);
  assert.equal(value.availableSeries, 4);
  assert.equal(value.window, "1h");
  assert.equal(value.fields.memory_bytes[0].value, 104857600);
  assert.equal(value.fields.cpu_cores.length, 3);
  assert.equal(projectPrometheusHistory({
    ...historyFixture(), synthetic: true,
  }, NOW), null);
  assert.equal(projectPrometheusHistory({
    ...historyFixture(), state: "not_executed",
  }, NOW), null);
});

test("stale, forged, duplicate, nonfinite history is rejected", () => {
  const payload = historyFixture();
  assert.equal(projectPrometheusHistory({
    ...payload, start: payload.start - 5000, end: payload.end - 5000,
  }, NOW), null);
  assert.equal(projectPrometheusHistory({
    ...payload, series: { ...payload.series, cpu_cores: [[1, 999]] },
  }, NOW), null);
  assert.equal(projectPrometheusHistory({
    ...payload, series: { ...payload.series,
      cpu_cores: [[payload.end, 1], [payload.end, 2]] },
  }, NOW), null);
  assert.equal(projectPrometheusHistory({
    ...payload, series: { ...payload.series,
      cpu_cores: [[payload.end, Number.NaN]] },
  }, NOW), null);
});

test("historical CPU and p95 Pearson only pairs identical sample timestamps", () => {
  const payload = historyFixture();
  const end = payload.end;
  const series = {
    ...payload.series,
    cpu_cores: Array.from({ length: 7 }, (_, i) => [end - (6 - i) * 60, i + 1]),
    http_p95_ms: Array.from({ length: 7 }, (_, i) => [end - (6 - i) * 60, (i + 1) * 10]),
  };
  const history = projectPrometheusHistory({ ...payload, series }, NOW);
  const { pairs, coefficient } = alignedHistoryCorrelation(history);
  assert.equal(pairs.length, 7);
  assert.ok(Math.abs(coefficient - 1) < 1e-12);
  const misaligned = { ...history, fields: {
    ...history.fields,
    http_p95_ms: history.fields.http_p95_ms.map((row) => ({
      ...row, at: new Date(Date.parse(row.at) + 30000).toISOString(),
    })),
  } };
  assert.equal(alignedHistoryCorrelation(misaligned).coefficient, null);
});

test("history UI only accepts bounded windows, never arbitrary PromQL", () => {
  const ui = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url), "utf8",
  );
  assert.match(ui, /projectPrometheusHistory/);
  assert.match(ui, /updatePrometheusHistory/);
  assert.match(ui, /\["1h", "24h", "7d"\]/);
  assert.match(ui, /\/api\/home\/metrics\/history\?window=/);
  assert.doesNotMatch(ui, /query=|prometheus\.albandrieu\.com/);
});
