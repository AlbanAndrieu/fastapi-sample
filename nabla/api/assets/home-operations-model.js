// Pure data projection for the / operations dashboard.
// These helpers neither fetch network data nor synthesize samples.

const STATES = Object.freeze(["ok", "warn", "fail", "unknown"]);
const SAMPLE_IDS = new Set([
  "sample",
  "fastapi-sample",
  "fastapi_sample",
  "albandrieu_sample",
]);
const OBSERVED_SOURCES = new Set(["origin", "memory"]);
const MAX_HISTORY = 24;
const MAX_AGE_SECONDS = 180;

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function finite(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function validState(value) {
  return STATES.includes(value) ? value : "unknown";
}

function hasFreshTimestamp(value, nowMs) {
  if (typeof value !== "string") return false;
  const time = Date.parse(value);
  const age = nowMs - time;
  return (
    Number.isFinite(time) && age >= -30000 && age <= MAX_AGE_SECONDS * 1000
  );
}

export function projectFleet(payload) {
  if (
    payload?.schemaVersion !== 2 ||
    payload?.model !== "public-service-overview" ||
    !Array.isArray(payload?.services) ||
    payload.services.length > 2000 ||
    !["fresh", "stale", "pending"].includes(payload.boardState)
  )
    return null;
  const counts = { ok: 0, warn: 0, fail: 0, unknown: 0 };
  for (const row of payload.services) {
    if (
      typeof row?.name !== "string" ||
      row.name.length > 128 ||
      !["API", "Component", "Resource"].includes(row.kind) ||
      !STATES.includes(row.state)
    )
      return null;
    counts[payload.boardState === "fresh" ? row.state : "unknown"] += 1;
  }
  return {
    total: payload.services.length,
    counts,
    verified: payload.boardState === "fresh",
    source:
      payload.catalogSource === "backstage-v2"
        ? "Backstage v2"
        : "Inventaire de secours",
    boardState: payload.boardState,
  };
}

function freshBoard(board, nowMs = Date.now()) {
  return (
    board?.state === "fresh" &&
    (finite(board.age_seconds) === null ||
      board.age_seconds <= MAX_AGE_SECONDS) &&
    hasFreshTimestamp(board.generated_at, nowMs)
  );
}

export function projectProbes(board, nowMs = Date.now()) {
  if (!freshBoard(board, nowMs)) return null;
  const homelab = record(board.homelab);
  const summary = record(homelab.probe_summary);
  let eligible = 0;
  let known = 0;
  let hasScope = false;
  for (const scope of ["public", "internal"]) {
    const group = record(summary[scope]);
    if (group.enabled === false) continue;
    const total = count(group.eligible);
    const seen = count(record(group.evidence).known);
    if (total === null || seen === null) continue;
    hasScope = true;
    eligible += total;
    known += Math.min(total, seen);
  }
  if (!hasScope || eligible === 0) return null;
  // Health is counted from real recent per-slot evidence, never from eligible
  // catalog entries or the unrelated Backstage status.
  const observed = new Set();
  for (const [scope, field] of [
    ["public", "public_probe_results"],
    ["internal", "internal_services"],
  ]) {
    if (scope === "internal" && summary.internal?.enabled === false) continue;
    const rows = homelab[field];
    if (!Array.isArray(rows)) continue;
    for (const row of rows) {
      if (
        !row ||
        typeof row.id !== "string" ||
        !OBSERVED_SOURCES.has(row.probe_source) ||
        row.probe_stale === true
      )
        continue;
      if (row.state === "ok") observed.add(scope + ":" + row.id);
    }
  }
  const healthy = Math.min(known, observed.size);
  return {
    eligible,
    known,
    healthy,
    coverage: (100 * known) / eligible,
    healthyCoverage: (100 * healthy) / eligible,
    unobserved: Math.max(0, eligible - known),
    observedAt: board.generated_at,
  };
}

/** A compact OWNER-only probe mosaic, never a synthetic health census. */
export function projectProbeMatrix(board, nowMs = Date.now()) {
  if (!freshBoard(board, nowMs)) return null;
  const homelab = record(board.homelab);
  const summary = record(homelab.probe_summary);
  const rows = [];
  for (const [scope, field] of [
    ["public", "public_probe_results"],
    ["internal", "internal_services"],
  ]) {
    if (record(summary[scope]).enabled === false) continue;
    const candidates = homelab[field];
    if (!Array.isArray(candidates)) continue;
    for (const probe of candidates) {
      if (
        !probe ||
        typeof probe.id !== "string" ||
        probe.id.length === 0 ||
        probe.id.length > 100
      )
        continue;
      const evidenced =
        OBSERVED_SOURCES.has(probe.probe_source) && probe.probe_stale !== true;
      rows.push({
        id: probe.id,
        scope,
        state: evidenced ? validState(probe.state) : "unknown",
        evidence: evidenced
          ? "observed"
          : probe.probe_stale === true
            ? "stale"
            : "unobserved",
      });
    }
  }
  // Render at most 80 tiles; do not materialize nonexistent catalog slots.
  const order = { fail: 0, warn: 1, unknown: 2, ok: 3 };
  rows.sort(
    (a, b) =>
      order[a.state] - order[b.state] ||
      a.scope.localeCompare(b.scope) ||
      a.id.localeCompare(b.id),
  );
  return {
    observedAt: board.generated_at,
    count: rows.length,
    tiles: rows.slice(0, 80),
    truncated: Math.max(0, rows.length - 80),
  };
}

export function projectResources(payload, nowMs = Date.now()) {
  const telemetry = record(payload);
  if (
    !["healthy", "partial"].includes(telemetry.state) ||
    !hasFreshTimestamp(telemetry.generated_at, nowMs)
  )
    return null;
  const services = record(telemetry.resources);
  const matches = Object.entries(services).filter(
    ([name, data]) => SAMPLE_IDS.has(name) && data && typeof data === "object",
  );
  // Do not guess from display names and never merge contradictory containers.
  if (matches.length !== 1) return null;
  const raw = record(matches[0][1]);
  const cpu = finite(raw.cpu_cores);
  const memory = finite(raw.memory_bytes);
  const network = finite(raw.network_bytes_per_second);
  return {
    observedAt: telemetry.generated_at,
    cpuCores: cpu !== null && cpu >= 0 ? cpu : null,
    memoryMiB: memory !== null && memory >= 0 ? memory / 1048576 : null,
    networkKiBs: network !== null && network >= 0 ? network / 1024 : null,
    source: "Prometheus / TrueNAS cAdvisor",
  };
}

/**
 * Rank measured container resources without inventing missing capacity or
 * interpreting byte counters as ZFS datasets. Caller MUST be OWNER-gated.
 * Ratios are relative to the largest observed row, never CPU utilization %.
 */
export function projectServiceFootprint(
  payload,
  dimension = "memory_bytes",
  nowMs = Date.now(),
) {
  const dimensions = {
    cpu_cores: { label: "CPU", unit: "c" },
    memory_bytes: { label: "Mémoire", unit: "MiB", divisor: 1048576 },
    fs_bytes: { label: "FS conteneur", unit: "MiB", divisor: 1048576 },
    network_bytes_per_second: {
      label: "Réseau RX + TX",
      unit: "KiB/s",
      divisor: 1024,
    },
  };
  if (!Object.hasOwn(dimensions, dimension)) return null;
  const telemetry = record(payload);
  if (
    telemetry.schema_version !== 1 ||
    !["healthy", "partial"].includes(telemetry.state) ||
    telemetry.resource_source !== "truenas_cadvisor" ||
    !hasFreshTimestamp(telemetry.generated_at, nowMs)
  )
    return null;
  const services = record(telemetry.resources);
  const names = Object.keys(services);
  if (names.length > 2000) return null;
  const spec = dimensions[dimension];
  const observed = [];
  for (const name of names) {
    if (!/^[a-zA-Z0-9_.-]{1,80}$/.test(name)) continue;
    const value = finite(record(services[name])[dimension]);
    if (value === null || value < 0) continue;
    observed.push({ name, value: value / (spec.divisor || 1) });
  }
  observed.sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
  const max = observed[0]?.value || 0;
  return {
    dimension,
    label: spec.label,
    unit: spec.unit,
    observedAt: telemetry.generated_at,
    measured: observed.length,
    declared: names.length,
    rows: observed.slice(0, 8).map((entry) => ({
      ...entry,
      relativePercent: max > 0 ? (100 * entry.value) / max : 0,
    })),
    storageScope:
      dimension === "fs_bytes"
        ? "Système de fichiers du conteneur (cAdvisor) ; hors datasets ZFS / PVC."
        : null,
  };
}

/**
 * OWNER-only compact resource matrix. Every column is scaled independently
 * to its measured maximum; no cell represents capacity utilisation.
 * Missing measurement is distinct from a measured zero.
 */
export function projectResourceHeatmap(payload, nowMs = Date.now()) {
  const dimensions = [
    ["cpu_cores", "CPU", "c", 1],
    ["memory_bytes", "RAM", "MiB", 1048576],
    ["fs_bytes", "FS", "MiB", 1048576],
    ["network_bytes_per_second", "RX+TX", "KiB/s", 1024],
  ];
  const telemetry = record(payload);
  if (
    telemetry.schema_version !== 1 ||
    !["healthy", "partial"].includes(telemetry.state) ||
    telemetry.resource_source !== "truenas_cadvisor" ||
    !hasFreshTimestamp(telemetry.generated_at, nowMs)
  )
    return null;
  const services = record(telemetry.resources);
  const names = Object.keys(services);
  if (names.length > 2000) return null;
  const maxima = Object.fromEntries(dimensions.map(([key]) => [key, 0]));
  const rows = [];
  for (const name of names) {
    if (!/^[a-zA-Z0-9_.-]{1,80}$/.test(name)) continue;
    const raw = record(services[name]);
    const values = {};
    let measured = 0;
    for (const [key] of dimensions) {
      const value = finite(raw[key]);
      values[key] = value !== null && value >= 0 ? value : null;
      if (values[key] !== null) {
        measured += 1;
        maxima[key] = Math.max(maxima[key], values[key]);
      }
    }
    if (measured > 0) rows.push({ name, measured, values });
  }
  rows.sort(
    (a, b) =>
      b.measured - a.measured ||
      (b.values.memory_bytes ?? -1) - (a.values.memory_bytes ?? -1) ||
      a.name.localeCompare(b.name),
  );
  return {
    observedAt: telemetry.generated_at,
    measuredServices: rows.length,
    declaredServices: names.length,
    truncated: Math.max(0, rows.length - 12),
    dimensions: dimensions.map(([key, label, unit, divisor]) => ({
      key, label, unit, divisor,
    })),
    rows: rows.slice(0, 12).map((row) => ({
      name: row.name,
      cells: dimensions.map(([key, label, unit, divisor]) => ({
        key,
        label,
        unit,
        value: row.values[key] === null ? null : row.values[key] / divisor,
        relativePercent:
          row.values[key] === null || maxima[key] === 0
            ? null
            : (100 * row.values[key]) / maxima[key],
      })),
    })),
  };
}

/** pfSense flow is aggregate evidence; no per-service/edge attribution exists. */
export function projectAggregateNetworkFlow(payload, nowMs = Date.now()) {
  if (
    payload?.schema_version !== 1 ||
    !["healthy", "partial"].includes(payload.state) ||
    !hasFreshTimestamp(payload.generated_at, nowMs)
  )
    return null;
  const flow = record(payload.network_flow);
  const rate = finite(flow.pfsense_bytes_per_second);
  return {
    observedAt: payload.generated_at,
    kiBs: rate !== null && rate >= 0 ? rate / 1024 : null,
    collectorConfirmed:
      flow.akvorado_inlet_up === 1 && flow.akvorado_outlet_up === 1,
    attributed: false,
  };
}

export function projectLatency(board, nowMs = Date.now()) {
  if (!freshBoard(board, nowMs)) return null;
  const rows = record(board.homelab).public_probe_results;
  if (!Array.isArray(rows)) return null;
  const candidates = rows.filter(
    (row) =>
      row &&
      SAMPLE_IDS.has(row.id) &&
      OBSERVED_SOURCES.has(row.probe_source) &&
      row.probe_stale !== true &&
      finite(row.latency_ms) !== null &&
      row.latency_ms >= 0,
  );
  if (candidates.length !== 1) return null;
  return {
    valueMs: candidates[0].latency_ms,
    observedAt: candidates[0].probe_observed_at || board.generated_at,
    source: "HTTP probe (not ICMP RTT)",
  };
}

export function projectSecurity(board, nowMs = Date.now()) {
  if (!freshBoard(board, nowMs)) return null;
  const homelab = record(board.homelab);
  const connections = record(homelab.connection_matrix).rows;
  const byId = new Map(
    Array.isArray(connections)
      ? connections
          .filter((row) => typeof row?.id === "string")
          .map((row) => [row.id, row])
      : [],
  );
  const selected = [
    [
      "cloudflare_access",
      "Cloudflare Access",
      "Inventaire de politiques ; pas un test d'autorisation",
    ],
    [
      "cloudflare_tunnel_runtime",
      "Cloudflare Tunnel",
      "État du cycle de vie déclaré, pas du service",
    ],
    [
      "dns_sample",
      "DNS public",
      "Résolveur Cloudflare récursif, pas zone autoritaire",
    ],
    [
      "prometheus_query",
      "Prometheus",
      "Lecture des métriques, pas disponibilité applicative",
    ],
    ["truenas_api", "API TrueNAS", "API authentifiée, différente du port TCP"],
    [
      "fastapi_cloud",
      "FastAPI Cloud",
      "Session anonyme ; pas de droits propriétaire",
    ],
  ];
  const checks = selected.map(([id, label, description]) => {
    const row = record(byId.get(id));
    return {
      id,
      label,
      description,
      state: validState(row.state),
      category:
        typeof row.diagnostic_category === "string"
          ? row.diagnostic_category
          : "",
    };
  });
  const dnsPolicy = record(record(homelab.pfsense).dns);
  const policyState = validState(dnsPolicy.policy_state);
  checks.push({
    id: "pfsense_dns",
    label: "pfSense DNS / Unbound",
    state: policyState,
    category: "",
    description: "Posture du résolveur et des règles réseau ; lecture seule",
  });
  const sickz = record(board.sickz);
  const policies = Object.values(record(sickz.checks)).filter(
    (row) => row && ["ok", "warn", "fail"].includes(row.security_policy_status),
  );
  const policyCounts = { ok: 0, warn: 0, fail: 0 };
  for (const row of policies) policyCounts[row.security_policy_status] += 1;
  return {
    checks,
    policyCounts,
    policyObserved: policies.length,
    issues: policyCounts.warn + policyCounts.fail,
  };
}

export function appendObservation(
  history,
  timestamp,
  value,
  limit = MAX_HISTORY,
) {
  const number = finite(value);
  if (
    number === null ||
    number < 0 ||
    typeof timestamp !== "string" ||
    !Number.isFinite(Date.parse(timestamp))
  ) {
    return history.slice(-limit);
  }
  const next = history.filter((item) => item?.at !== timestamp);
  next.push({ at: timestamp, value: number });
  next.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  return next.slice(-Math.max(2, Math.min(limit, MAX_HISTORY)));
}

export function sparklinePath(history, width = 420, height = 108) {
  const values = history.map((item) => finite(item?.value));
  if (values.length < 2 || values.some((v) => v === null)) return null;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const range = high === low ? 1 : high - low;
  const pad = 7;
  return values
    .map((value, i) => {
      const x = pad + (i * (width - 2 * pad)) / (values.length - 1);
      const y =
        high === low
          ? height / 2
          : height - pad - ((value - low) / range) * (height - 2 * pad);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

export function pearsonCorrelation(pairs, minSamples = 6) {
  if (!Array.isArray(pairs) || pairs.length < minSamples) return null;
  const n = pairs.length;
  const xs = pairs.map((item) => finite(item.cpu));
  const ys = pairs.map((item) => finite(item.httpMs));
  if (xs.some((item) => item === null) || ys.some((item) => item === null))
    return null;
  const avgX = xs.reduce((sum, item) => sum + item, 0) / n;
  const avgY = ys.reduce((sum, item) => sum + item, 0) / n;
  const cov = xs.reduce(
    (sum, item, i) => sum + (item - avgX) * (ys[i] - avgY),
    0,
  );
  const varX = xs.reduce((sum, item) => sum + (item - avgX) ** 2, 0);
  const varY = ys.reduce((sum, item) => sum + (item - avgY) ** 2, 0);
  if (
    !Number.isFinite(cov) ||
    !Number.isFinite(varX) ||
    !Number.isFinite(varY) ||
    varX <= 0 ||
    varY <= 0
  )
    return null;
  const coefficient = cov / Math.sqrt(varX * varY);
  return Number.isFinite(coefficient)
    ? Math.max(-1, Math.min(1, coefficient))
    : null;
}

// The history contract is deliberately smaller than the Prometheus API.
const HISTORY_FIELDS = Object.freeze([
  "cpu_cores",
  "memory_bytes",
  "network_bytes_per_second",
  "http_p95_ms",
  "gatus_availability_percent",
]);
const HISTORY_WINDOWS = Object.freeze({
  "1h": { seconds: 3600, step: 60 },
  "24h": { seconds: 86400, step: 300 },
  "7d": { seconds: 604800, step: 1800 },
});

export function projectPrometheusHistory(payload, nowMs = Date.now()) {
  const window = HISTORY_WINDOWS[payload?.window];
  if (
    payload?.schema_version !== 1 ||
    payload?.model !== "owner-operations-history" ||
    !window ||
    !["observed", "partial"].includes(payload?.state) ||
    payload?.synthetic !== false ||
    payload?.source !== "prometheus_query_range" ||
    payload.step_seconds !== window.step ||
    !Number.isSafeInteger(payload.start) ||
    !Number.isSafeInteger(payload.end) ||
    payload.end - payload.start !== window.seconds ||
    payload.end * 1000 > nowMs + 30000 ||
    payload.end * 1000 < nowMs - window.step * 2000 ||
    !payload.series ||
    typeof payload.series !== "object" ||
    Array.isArray(payload.series)
  )
    return null;
  const fields = {};
  let known = 0;
  for (const key of HISTORY_FIELDS) {
    const rows = payload.series[key];
    if (!Array.isArray(rows) || rows.length > 350) return null;
    let previous = -1;
    const points = [];
    for (const row of rows) {
      if (
        !Array.isArray(row) ||
        row.length !== 2 ||
        !Number.isSafeInteger(row[0]) ||
        row[0] < payload.start ||
        row[0] > payload.end ||
        (row[0] - payload.start) % window.step !== 0 ||
        row[0] <= previous ||
        finite(row[1]) === null ||
        row[1] < 0
      )
        return null;
      if (key === "gatus_availability_percent" && row[1] > 100) return null;
      previous = row[0];
      points.push({ at: new Date(row[0] * 1000).toISOString(), value: row[1] });
    }
    fields[key] = points;
    known += Number(points.length > 0);
  }
  if (!known) return null;
  return {
    window: payload.window,
    start: payload.start,
    end: payload.end,
    step: window.step,
    source: "Prometheus · query_range",
    fields,
    availableSeries: known,
    partial: payload.state === "partial",
  };
}

export function alignedHistoryCorrelation(history, minPairs = 6) {
  if (!history?.fields) return { pairs: [], coefficient: null };
  const cpu = history.fields.cpu_cores || [];
  const http = new Map(
    (history.fields.http_p95_ms || []).map((row) => [row.at, row.value]),
  );
  const pairs = cpu
    .filter((row) => http.has(row.at))
    .map((row) => ({
      at: Date.parse(row.at),
      key: row.at,
      cpu: row.value,
      httpMs: http.get(row.at),
    }));
  return { pairs, coefficient: pearsonCorrelation(pairs, minPairs) };
}

export function temporalSparklinePath(
  points,
  { startMs, endMs, maxGapMs, width = 420, height = 108 } = {},
) {
  if (
    !Array.isArray(points) ||
    points.length < 2 ||
    !Number.isFinite(startMs) ||
    !Number.isFinite(endMs) ||
    endMs <= startMs ||
    !Number.isFinite(maxGapMs) ||
    maxGapMs <= 0
  )
    return null;
  const sorted = points.map((point) => ({
    timestamp: Date.parse(point?.at),
    value: finite(point?.value),
  }));
  if (
    sorted.some(
      (point) =>
        !Number.isFinite(point.timestamp) ||
        point.value === null ||
        point.timestamp < startMs ||
        point.timestamp > endMs ||
        point.value < 0,
    )
  )
    return null;
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].timestamp <= sorted[i - 1].timestamp) return null;
  }
  const minimum = Math.min(...sorted.map((point) => point.value));
  const maximum = Math.max(...sorted.map((point) => point.value));
  const pad = 7;
  const range = Math.max(maximum - minimum, Number.EPSILON);
  return sorted
    .map((point, index) => {
      const x =
        pad +
        ((point.timestamp - startMs) / (endMs - startMs)) * (width - 2 * pad);
      const y =
        maximum === minimum
          ? height / 2
          : height -
            pad -
            ((point.value - minimum) / range) * (height - 2 * pad);
      const disconnected =
        index === 0 || point.timestamp - sorted[index - 1].timestamp > maxGapMs;
      return `${disconnected ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

// Live TrueNAS appliance pulse (OWNER only). Every value is validated; a
// section that the server marked unavailable stays unknown in the UI.
const PULSE_SECTIONS = Object.freeze([
  "appliance",
  "cpu",
  "memory",
  "network",
  "storage",
  "alerts",
  "apps",
]);
const PULSE_MAX_POINTS = 400;

function pulseSeries(rows, maximum) {
  if (!Array.isArray(rows) || rows.length > PULSE_MAX_POINTS) return [];
  const points = [];
  let previous = -1;
  for (const row of rows) {
    if (
      !Array.isArray(row) ||
      row.length !== 2 ||
      !Number.isSafeInteger(row[0]) ||
      row[0] <= previous
    )
      return [];
    const value = finite(row[1]);
    if (value === null || value < 0 || (maximum !== null && value > maximum))
      return [];
    previous = row[0];
    points.push({ at: new Date(row[0] * 1000).toISOString(), value });
  }
  return points;
}

function percent(value) {
  const number = finite(value);
  return number !== null && number >= 0 && number <= 100 ? number : null;
}

function nonNegative(value) {
  const number = finite(value);
  return number !== null && number >= 0 ? number : null;
}

function text(value, limit = 160) {
  return typeof value === "string" ? value.slice(0, limit) : "";
}

export function projectAppliancePulse(payload, nowMs = Date.now()) {
  if (
    payload?.schema_version !== 1 ||
    payload?.model !== "owner-appliance-pulse" ||
    payload?.source !== "truenas_middleware" ||
    payload?.synthetic !== false ||
    !["observed", "partial"].includes(payload?.state) ||
    !hasFreshTimestamp(payload.observed_at, nowMs)
  )
    return null;
  const section = {};
  for (const key of PULSE_SECTIONS) section[key] = record(payload[key]);
  const observed = (key) => section[key].state === "observed";
  const load = record(section.appliance.load);
  const impacts = (Array.isArray(payload.impacts) ? payload.impacts : [])
    .filter(
      (item) =>
        item &&
        typeof item.id === "string" &&
        STATES.includes(item.state) &&
        typeof item.evidence === "string",
    )
    .slice(0, 20)
    .map((item) => ({
      id: item.id,
      from: text(item.from, 32),
      to: text(item.to, 32),
      state: item.state,
      evidence: text(item.evidence),
      linked: Array.isArray(item.linked)
        ? item.linked.filter((entry) => typeof entry === "string").slice(0, 20)
        : [],
    }));
  const alertLevels = {};
  for (const [level, value] of Object.entries(
    record(section.alerts.by_level),
  )) {
    if (/^[A-Z_]{1,16}$/.test(level) && count(value) !== null)
      alertLevels[level] = value;
  }
  const appCounts = {};
  for (const [state, value] of Object.entries(record(section.apps.counts))) {
    if (/^[A-Z_]{1,16}$/.test(state) && count(value) !== null)
      appCounts[state] = value;
  }
  return {
    observedAt: payload.observed_at,
    partial: payload.state === "partial",
    pressure: validState(payload.pressure_state),
    appliance: {
      observed: observed("appliance"),
      version: text(section.appliance.version, 64) || null,
      cores: count(section.appliance.cores),
      load1: nonNegative(load["1m"]),
      loadPerCore: nonNegative(section.appliance.load_per_core_1m),
      uptimeSeconds: nonNegative(section.appliance.uptime_seconds),
    },
    cpu: {
      state: text(section.cpu.state, 32) || "unavailable",
      busyPercent: percent(section.cpu.busy_percent),
      series: pulseSeries(section.cpu.series, 100),
    },
    memory: {
      state: text(section.memory.state, 32) || "unavailable",
      usedPercent: percent(section.memory.used_percent),
      series: pulseSeries(section.memory.series, 100),
    },
    network: {
      observed: observed("network"),
      throughput: nonNegative(section.network.throughput),
      label: text(section.network.vertical_label, 48) || null,
      interfaces: (Array.isArray(section.network.physical)
        ? section.network.physical
        : []
      )
        .filter((row) => row && typeof row.name === "string")
        .map((row) => ({
          name: row.name.slice(0, 32),
          linkUp: row.link_up === true,
        })),
      series: pulseSeries(section.network.series, null),
    },
    storage: {
      observed: observed("storage"),
      worstUsedPercent: percent(section.storage.worst_used_percent),
      pools: (Array.isArray(section.storage.pools) ? section.storage.pools : [])
        .filter((row) => row && typeof row.name === "string")
        .map((row) => ({
          name: row.name.slice(0, 64),
          status: text(row.status, 32),
          healthy: row.healthy === true,
          usedPercent: percent(row.used_percent),
        })),
    },
    alerts: {
      observed: observed("alerts"),
      active: count(section.alerts.active),
      byLevel: alertLevels,
      items: (Array.isArray(section.alerts.items) ? section.alerts.items : [])
        .filter((row) => row && typeof row.klass === "string")
        .slice(0, 20)
        .map((row) => ({
          klass: row.klass.slice(0, 64),
          level: text(row.level, 16),
          dismissed: row.dismissed === true,
          text: text(row.text),
        })),
    },
    apps: {
      observed: observed("apps"),
      total: count(section.apps.total),
      counts: appCounts,
      crashed: (Array.isArray(section.apps.crashed) ? section.apps.crashed : [])
        .filter((entry) => typeof entry === "string")
        .slice(0, 20),
    },
    impacts,
    errors: Object.keys(record(payload.errors)).slice(0, 20),
  };
}
