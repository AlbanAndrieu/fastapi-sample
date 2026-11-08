// Pure data projection for the / operations dashboard.
// These helpers neither fetch network data nor synthesize samples.

const STATES = Object.freeze(["ok", "warn", "fail", "unknown"]);
const SAMPLE_IDS = new Set(["sample", "fastapi-sample", "fastapi_sample", "albandrieu_sample"]);
const OBSERVED_SOURCES = new Set(["origin", "memory"]);
const MAX_HISTORY = 24;
const MAX_AGE_SECONDS = 180;

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
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
  return Number.isFinite(time) && age >= -30000 && age <= MAX_AGE_SECONDS * 1000;
}

export function projectFleet(payload) {
  if (payload?.schemaVersion !== 2 ||
      payload?.model !== "public-service-overview" ||
      !Array.isArray(payload?.services) ||
      payload.services.length > 2000 ||
      !["fresh", "stale", "pending"].includes(payload.boardState)) return null;
  const counts = { ok: 0, warn: 0, fail: 0, unknown: 0 };
  for (const row of payload.services) {
    if (typeof row?.name !== "string" || row.name.length > 128 ||
        !["API", "Component", "Resource"].includes(row.kind) ||
        !STATES.includes(row.state)) return null;
    counts[payload.boardState === "fresh" ? row.state : "unknown"] += 1;
  }
  return {
    total: payload.services.length,
    counts,
    verified: payload.boardState === "fresh",
    source: payload.catalogSource === "backstage-v2" ? "Backstage v2" : "Inventaire de secours",
    boardState: payload.boardState,
  };
}

function freshBoard(board, nowMs = Date.now()) {
  return board?.state === "fresh" &&
    (finite(board.age_seconds) === null || board.age_seconds <= MAX_AGE_SECONDS) &&
    hasFreshTimestamp(board.generated_at, nowMs);
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
    ["public", "public_probe_results"], ["internal", "internal_services"],
  ]) {
    if (scope === "internal" && summary.internal?.enabled === false) continue;
    const rows = homelab[field];
    if (!Array.isArray(rows)) continue;
    for (const row of rows) {
      if (!row || typeof row.id !== "string" ||
          !OBSERVED_SOURCES.has(row.probe_source) || row.probe_stale === true) continue;
      if (row.state === "ok") observed.add(scope + ":" + row.id);
    }
  }
  const healthy = Math.min(known, observed.size);
  return {
    eligible, known, healthy,
    coverage: 100 * known / eligible,
    healthyCoverage: 100 * healthy / eligible,
    unobserved: Math.max(0, eligible - known),
    observedAt: board.generated_at,
  };
}

export function projectResources(payload, nowMs = Date.now()) {
  const telemetry = record(payload);
  if (!["healthy", "partial"].includes(telemetry.state) ||
      !hasFreshTimestamp(telemetry.generated_at, nowMs)) return null;
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

export function projectLatency(board, nowMs = Date.now()) {
  if (!freshBoard(board, nowMs)) return null;
  const rows = record(board.homelab).public_probe_results;
  if (!Array.isArray(rows)) return null;
  const candidates = rows.filter((row) =>
    row && SAMPLE_IDS.has(row.id) && OBSERVED_SOURCES.has(row.probe_source) &&
    row.probe_stale !== true && finite(row.latency_ms) !== null &&
    row.latency_ms >= 0
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
      ? connections.filter((row) => typeof row?.id === "string").map((row) => [row.id, row])
      : []
  );
  const selected = [
    ["cloudflare_access", "Cloudflare Access", "Inventaire de politiques ; pas un test d'autorisation"],
    ["cloudflare_tunnel_runtime", "Cloudflare Tunnel", "État du cycle de vie déclaré, pas du service"],
    ["dns_sample", "DNS public", "Résolveur Cloudflare récursif, pas zone autoritaire"],
    ["prometheus_query", "Prometheus", "Lecture des métriques, pas disponibilité applicative"],
    ["truenas_api", "API TrueNAS", "API authentifiée, différente du port TCP"],
    ["fastapi_cloud", "FastAPI Cloud", "Session anonyme ; pas de droits propriétaire"],
  ];
  const checks = selected.map(([id, label, description]) => {
    const row = record(byId.get(id));
    return {
      id, label, description,
      state: validState(row.state),
      category: typeof row.diagnostic_category === "string" ? row.diagnostic_category : "",
    };
  });
  const dnsPolicy = record(record(homelab.pfsense).dns);
  const policyState = validState(dnsPolicy.policy_state);
  checks.push({
    id: "pfsense_dns", label: "pfSense DNS / Unbound",
    state: policyState, category: "",
    description: "Posture du résolveur et des règles réseau ; lecture seule",
  });
  const sickz = record(board.sickz);
  const policies = Object.values(record(sickz.checks)).filter(
    (row) => row && ["ok", "warn", "fail"].includes(row.security_policy_status)
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

export function appendObservation(history, timestamp, value, limit = MAX_HISTORY) {
  const number = finite(value);
  if (number === null || number < 0 ||
      typeof timestamp !== "string" || !Number.isFinite(Date.parse(timestamp))) {
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
  return values.map((value, i) => {
    const x = pad + i * (width - 2 * pad) / (values.length - 1);
    const y = high === low ? height / 2 : height - pad -
      ((value - low) / range) * (height - 2 * pad);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}

export function pearsonCorrelation(pairs, minSamples = 6) {
  if (!Array.isArray(pairs) || pairs.length < minSamples) return null;
  const n = pairs.length;
  const xs = pairs.map((item) => finite(item.cpu));
  const ys = pairs.map((item) => finite(item.httpMs));
  if (xs.some((item) => item === null) || ys.some((item) => item === null)) return null;
  const avgX = xs.reduce((sum, item) => sum + item, 0) / n;
  const avgY = ys.reduce((sum, item) => sum + item, 0) / n;
  const cov = xs.reduce((sum, item, i) => sum + (item - avgX) * (ys[i] - avgY), 0);
  const varX = xs.reduce((sum, item) => sum + (item - avgX) ** 2, 0);
  const varY = ys.reduce((sum, item) => sum + (item - avgY) ** 2, 0);
  if (!Number.isFinite(cov) || !Number.isFinite(varX) ||
      !Number.isFinite(varY) || varX <= 0 || varY <= 0) return null;
  const coefficient = cov / Math.sqrt(varX * varY);
  return Number.isFinite(coefficient)
    ? Math.max(-1, Math.min(1, coefficient)) : null;
}

// The history contract is deliberately smaller than the Prometheus API.
const HISTORY_FIELDS = Object.freeze([
  "cpu_cores", "memory_bytes", "network_bytes_per_second",
  "http_p95_ms", "gatus_availability_percent",
]);
const HISTORY_WINDOWS = Object.freeze({
  "1h": { seconds: 3600, step: 60 },
  "24h": { seconds: 86400, step: 300 },
  "7d": { seconds: 604800, step: 1800 },
});

export function projectPrometheusHistory(payload, nowMs = Date.now()) {
  const window = HISTORY_WINDOWS[payload?.window];
  if (payload?.schema_version !== 1 ||
      payload?.model !== "owner-operations-history" ||
      !window || !["observed", "partial"].includes(payload?.state) ||
      payload?.synthetic !== false ||
      payload?.source !== "prometheus_query_range" ||
      payload.step_seconds !== window.step ||
      !Number.isSafeInteger(payload.start) || !Number.isSafeInteger(payload.end) ||
      payload.end - payload.start !== window.seconds ||
      payload.end * 1000 > nowMs + 30000 ||
      payload.end * 1000 < nowMs - window.step * 2000 ||
      !payload.series || typeof payload.series !== "object" ||
      Array.isArray(payload.series)) return null;
  const fields = {};
  let known = 0;
  for (const key of HISTORY_FIELDS) {
    const rows = payload.series[key];
    if (!Array.isArray(rows) || rows.length > 350) return null;
    let previous = -1;
    const points = [];
    for (const row of rows) {
      if (!Array.isArray(row) || row.length !== 2 ||
          !Number.isSafeInteger(row[0]) ||
          row[0] < payload.start || row[0] > payload.end ||
          (row[0] - payload.start) % window.step !== 0 ||
          row[0] <= previous || finite(row[1]) === null ||
          row[1] < 0) return null;
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
  const http = new Map((history.fields.http_p95_ms || []).map(
    (row) => [row.at, row.value],
  ));
  const pairs = cpu.filter((row) => http.has(row.at)).map((row) => ({
    at: Date.parse(row.at),
    key: row.at,
    cpu: row.value,
    httpMs: http.get(row.at),
  }));
  return { pairs, coefficient: pearsonCorrelation(pairs, minPairs) };
}


export function temporalSparklinePath(points, {
  startMs, endMs, maxGapMs, width = 420, height = 108,
} = {}) {
  if (!Array.isArray(points) || points.length < 2 ||
      !Number.isFinite(startMs) || !Number.isFinite(endMs) ||
      endMs <= startMs || !Number.isFinite(maxGapMs) || maxGapMs <= 0) return null;
  const sorted = points.map((point) => ({
    timestamp: Date.parse(point?.at),
    value: finite(point?.value),
  }));
  if (sorted.some((point) =>
    !Number.isFinite(point.timestamp) || point.value === null ||
    point.timestamp < startMs || point.timestamp > endMs ||
    point.value < 0
  )) return null;
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].timestamp <= sorted[i - 1].timestamp) return null;
  }
  const minimum = Math.min(...sorted.map((point) => point.value));
  const maximum = Math.max(...sorted.map((point) => point.value));
  const pad = 7;
  const range = Math.max(maximum - minimum, Number.EPSILON);
  return sorted.map((point, index) => {
    const x = pad + (point.timestamp - startMs) / (endMs - startMs) *
      (width - 2 * pad);
    const y = maximum === minimum ? height / 2 :
      height - pad - (point.value - minimum) / range * (height - 2 * pad);
    const disconnected = index === 0 ||
      point.timestamp - sorted[index - 1].timestamp > maxGapMs;
    return `${disconnected ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}
