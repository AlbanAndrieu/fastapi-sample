import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  alignedHistoryCorrelation,
  appendObservation,
  pearsonCorrelation,
  projectAppliancePulse,
  projectFleet,
  projectLatency,
  projectProbes,
  projectPrometheusHistory,
  projectResources,
  projectSecurity,
  sparklinePath,
  temporalSparklinePath,
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
          id: "sample",
          state: "ok",
          probe_source: "origin",
          probe_stale: false,
          latency_ms: 97,
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
    schemaVersion: 2,
    model: "public-service-overview",
    catalogSource: "backstage-v2",
    boardState: "fresh",
    services: [
      { name: "Gatus", kind: "Component", state: "ok" },
      { name: "TrueNAS", kind: "Resource", state: "fail" },
    ],
  };
  assert.equal(projectFleet(fresh).counts.ok, 1);
  assert.equal(projectFleet(fresh).counts.fail, 1);
  const stale = projectFleet({ ...fresh, boardState: "stale" });
  assert.deepEqual(stale.counts, { ok: 0, warn: 0, fail: 0, unknown: 2 });
  assert.equal(
    projectFleet({
      ...fresh,
      services: [{ name: "X", kind: "API", state: "green" }],
    }),
    null,
  );
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
    state: "partial",
    generated_at: AT,
    resources: {
      sample: {
        cpu_cores: 0.5,
        memory_bytes: 209715200,
        network_bytes_per_second: 10240,
      },
    },
  };
  assert.deepEqual(projectResources(telemetry, NOW), {
    observedAt: AT,
    cpuCores: 0.5,
    memoryMiB: 200,
    networkKiBs: 10,
    source: "Prometheus / TrueNAS cAdvisor",
  });
  assert.equal(
    projectResources(
      {
        ...telemetry,
        generated_at: "2026-11-04T17:00:00Z",
      },
      NOW,
    ),
    null,
  );
});

test("ambiguous containers or missing data do not produce synthetic metrics", () => {
  const sample = {
    cpu_cores: 0.2,
    memory_bytes: 100,
    network_bytes_per_second: 200,
  };
  assert.equal(
    projectResources(
      {
        state: "healthy",
        generated_at: AT,
        resources: { sample, "fastapi-sample": sample },
      },
      NOW,
    ),
    null,
  );
  assert.equal(
    projectResources(
      {
        state: "healthy",
        generated_at: AT,
        resources: { sample: {} },
      },
      NOW,
    ).cpuCores,
    null,
  );
  assert.equal(projectResources({ state: "not_configured" }, NOW), null);
});

test("security checks use connection matrix evidence but never infer compliance", () => {
  const value = projectSecurity(board(), NOW);
  assert.equal(
    value.checks.find((v) => v.id === "cloudflare_access").state,
    "warn",
  );
  assert.equal(
    value.checks.find((v) => v.id === "truenas_api").state,
    "unknown",
  );
  assert.equal(value.policyObserved, 0);
  assert.equal(value.issues, 0);
});

test("observed policy violations are counted independently from service health", () => {
  const value = projectSecurity(
    board({
      sickz: {
        checks: {
          safe: { security_policy_status: "ok" },
          exposed: { security_policy_status: "fail" },
          missing: { security_policy_status: "unknown" },
        },
      },
    }),
    NOW,
  );
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
  assert.match(
    sparklinePath([
      { at: AT, value: 21 },
      { at: "2026-11-04T17:29:55Z", value: 23 },
    ]),
    /^M7\.0 /,
  );
});

test("home only reveals detailed fetch after owner session, never auto-polls sensor SSE", () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const html = readFileSync(
    new URL("../../templates/index.html", import.meta.url),
    "utf8",
  );
  const source = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  assert.match(html, /Operations Overview/);
  assert.doesNotMatch(
    html,
    /(?:tempChart|humidityChart|pressureChart|sensor_update|sse-connect)/,
  );
  assert.match(source, /sessionResult\.value\?\.authenticated === true/);
  assert.match(source, /if \(!owner\)/);
  assert.match(source, /fetchJSON\("\/api\/health-board"/);
  assert.match(source, /fetchJSON\("\/api\/topology-telemetry"/);
  assert.doesNotMatch(source, /\/(?:stream|charts|sensor-data)/);
  assert.equal(typeof root, "string");
});

test("standalone home imports no remote CDN or inline script", () => {
  const root = readFileSync(
    new URL("../../templates/index.html", import.meta.url),
    "utf8",
  );
  assert.match(root, /<html lang="fr">/);
  assert.match(root, /src="\/api\/assets\/home-operations.js"/);
  assert.doesNotMatch(
    root,
    /\{% extends|https:\/\/|cdn\.jsdelivr|unpkg|chart\.js/i,
  );
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
      cpu_cores: [
        [end - 120, 0.2],
        [end - 60, 0.3],
        [end, 0.4],
      ],
      memory_bytes: [[end, 104857600]],
      network_bytes_per_second: [[end, 8192]],
      http_p95_ms: [
        [end - 120, 20],
        [end - 60, 30],
        [end, 40],
      ],
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
  assert.equal(
    projectPrometheusHistory(
      {
        ...historyFixture(),
        synthetic: true,
      },
      NOW,
    ),
    null,
  );
  assert.equal(
    projectPrometheusHistory(
      {
        ...historyFixture(),
        state: "not_executed",
      },
      NOW,
    ),
    null,
  );
});

test("stale, forged, duplicate, nonfinite history is rejected", () => {
  const payload = historyFixture();
  assert.equal(
    projectPrometheusHistory(
      {
        ...payload,
        start: payload.start - 5000,
        end: payload.end - 5000,
      },
      NOW,
    ),
    null,
  );
  assert.equal(
    projectPrometheusHistory(
      {
        ...payload,
        series: { ...payload.series, cpu_cores: [[1, 999]] },
      },
      NOW,
    ),
    null,
  );
  assert.equal(
    projectPrometheusHistory(
      {
        ...payload,
        series: {
          ...payload.series,
          cpu_cores: [
            [payload.end, 1],
            [payload.end, 2],
          ],
        },
      },
      NOW,
    ),
    null,
  );
  assert.equal(
    projectPrometheusHistory(
      {
        ...payload,
        series: { ...payload.series, cpu_cores: [[payload.end, Number.NaN]] },
      },
      NOW,
    ),
    null,
  );
});

test("historical CPU and p95 Pearson only pairs identical sample timestamps", () => {
  const payload = historyFixture();
  const end = payload.end;
  const series = {
    ...payload.series,
    cpu_cores: Array.from({ length: 7 }, (_, i) => [end - (6 - i) * 60, i + 1]),
    http_p95_ms: Array.from({ length: 7 }, (_, i) => [
      end - (6 - i) * 60,
      (i + 1) * 10,
    ]),
  };
  const history = projectPrometheusHistory({ ...payload, series }, NOW);
  const { pairs, coefficient } = alignedHistoryCorrelation(history);
  assert.equal(pairs.length, 7);
  assert.ok(Math.abs(coefficient - 1) < 1e-12);
  const misaligned = {
    ...history,
    fields: {
      ...history.fields,
      http_p95_ms: history.fields.http_p95_ms.map((row) => ({
        ...row,
        at: new Date(Date.parse(row.at) + 30000).toISOString(),
      })),
    },
  };
  assert.equal(alignedHistoryCorrelation(misaligned).coefficient, null);
});

test("history UI only accepts bounded windows, never arbitrary PromQL", () => {
  const ui = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  assert.match(ui, /projectPrometheusHistory/);
  assert.match(ui, /updatePrometheusHistory/);
  assert.match(ui, /\["1h", "24h", "7d"\]/);
  assert.match(ui, /\/api\/home\/metrics\/history\?window=/);
  assert.doesNotMatch(ui, /query=|prometheus\.albandrieu\.com/);
});

test("timeline respects real time and draws explicit gaps", () => {
  const startMs = NOW - 3600000;
  const endMs = NOW;
  const line = temporalSparklinePath(
    [
      { at: new Date(startMs).toISOString(), value: 2 },
      { at: new Date(startMs + 60000).toISOString(), value: 4 },
      { at: new Date(endMs).toISOString(), value: 10 },
    ],
    { startMs, endMs, maxGapMs: 120000 },
  );
  assert.equal(line.match(/M/g).length, 2);
  assert.equal(line.match(/L/g).length, 1);
  assert.match(line, /^M7\.0 /);
  assert.match(line, /M413\.0 /);
  assert.equal(
    temporalSparklinePath([], { startMs, endMs, maxGapMs: 120000 }),
    null,
  );
});

function pulsePayload(overrides = {}) {
  const base = Date.parse(AT) / 1000 - 300;
  return {
    schema_version: 1,
    model: "owner-appliance-pulse",
    source: "truenas_middleware",
    synthetic: false,
    state: "observed",
    observed_at: AT,
    pressure_state: "warn",
    appliance: {
      state: "observed",
      version: "TrueNAS-27.0.0-RC.1",
      cores: 8,
      load: { "1m": 9.6 },
      load_per_core_1m: 1.2,
      uptime_seconds: 86400,
    },
    cpu: {
      state: "observed",
      busy_percent: 24,
      series: [
        [base, 20],
        [base + 60, 24],
      ],
    },
    memory: {
      state: "observed",
      used_percent: 70,
      series: [
        [base, 69.5],
        [base + 60, 70],
      ],
    },
    network: {
      state: "observed",
      throughput: 1500,
      vertical_label: "Bits/s",
      physical: [
        { name: "eno1", link_up: true },
        { name: "eno2", link_up: false },
      ],
      links_down: ["eno2"],
      series: [
        [base, 1200],
        [base + 60, 1500],
      ],
    },
    storage: {
      state: "observed",
      worst_used_percent: 86,
      pools: [
        { name: "cpool", status: "ONLINE", healthy: true, used_percent: 86 },
      ],
    },
    alerts: {
      state: "observed",
      total: 2,
      active: 1,
      by_level: { WARNING: 1 },
      items: [
        {
          klass: "ZpoolCapacityWarning",
          level: "WARNING",
          dismissed: false,
          text: "pool at 86%",
        },
      ],
    },
    apps: {
      state: "observed",
      total: 3,
      counts: { RUNNING: 1, STOPPED: 1, CRASHED: 1 },
      crashed: ["openrag"],
    },
    impacts: [
      {
        id: "storage_capacity",
        from: "storage",
        to: "alerts",
        state: "warn",
        evidence: "pool 86 %",
        linked: ["ZpoolCapacityWarning"],
      },
    ],
    errors: {},
    ...overrides,
  };
}

test("projectAppliancePulse keeps validated live TrueNAS signals and impacts", () => {
  const pulse = projectAppliancePulse(pulsePayload(), NOW);
  assert.ok(pulse);
  assert.equal(pulse.pressure, "warn");
  assert.equal(pulse.appliance.loadPerCore, 1.2);
  assert.equal(pulse.cpu.busyPercent, 24);
  assert.equal(pulse.cpu.series.length, 2);
  assert.equal(pulse.memory.usedPercent, 70);
  assert.equal(pulse.network.throughput, 1500);
  assert.equal(pulse.network.label, "Bits/s");
  assert.deepEqual(
    pulse.network.interfaces.map((row) => row.linkUp),
    [true, false],
  );
  assert.equal(pulse.storage.worstUsedPercent, 86);
  assert.deepEqual(pulse.alerts.byLevel, { WARNING: 1 });
  assert.deepEqual(pulse.apps.counts, { RUNNING: 1, STOPPED: 1, CRASHED: 1 });
  assert.deepEqual(pulse.impacts[0].linked, ["ZpoolCapacityWarning"]);
});

test("projectAppliancePulse refuses stale, synthetic, foreign or malformed payloads", () => {
  assert.equal(
    projectAppliancePulse(pulsePayload({ synthetic: true }), NOW),
    null,
  );
  assert.equal(
    projectAppliancePulse(
      pulsePayload({ model: "owner-operations-history" }),
      NOW,
    ),
    null,
  );
  assert.equal(
    projectAppliancePulse(pulsePayload({ state: "not_configured" }), NOW),
    null,
  );
  assert.equal(
    projectAppliancePulse(
      pulsePayload({ observed_at: "2026-11-04T17:00:00Z" }),
      NOW,
    ),
    null,
  );
  const unavailable = projectAppliancePulse(
    pulsePayload({
      state: "partial",
      alerts: { state: "unavailable", active: null, by_level: {}, items: [] },
    }),
    NOW,
  );
  assert.ok(unavailable);
  assert.equal(unavailable.partial, true);
  assert.equal(unavailable.alerts.observed, false);
  assert.equal(unavailable.alerts.active, null);
});

test("projectAppliancePulse drops impossible percentages, non-monotonic series and unsafe lists", () => {
  const broken = projectAppliancePulse(
    pulsePayload({
      cpu: {
        state: "observed",
        busy_percent: 140,
        series: [
          [10, 20],
          [5, 30],
        ],
      },
      storage: {
        state: "observed",
        worst_used_percent: -3,
        pools: [{ name: 42 }],
      },
      impacts: [
        { id: 7, state: "fail", evidence: "x" },
        { id: "ok", state: "weird", evidence: "y" },
      ],
    }),
    NOW,
  );
  assert.ok(broken);
  assert.equal(broken.cpu.busyPercent, null);
  assert.deepEqual(broken.cpu.series, []);
  assert.equal(broken.storage.worstUsedPercent, null);
  assert.deepEqual(broken.storage.pools, []);
  assert.deepEqual(broken.impacts, []);
});
