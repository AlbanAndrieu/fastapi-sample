const HOMELAB_EVIDENCE_FIELDS = [
  "local_state",
  "dependency_state",
  "effective_state",
  "required_dependencies",
  "blocked_by",
  "degraded_by",
  "unconfirmed_dependencies",
  "dependency_evidence",
  "dependency_cycle",
  "observed_at",
  "observation_age_seconds",
  "observation_stale",
  "direct_state",
  "internal_state",
  "direct_probe_source",
  "direct_probe_observed_at",
  "direct_probe_age_seconds",
  "direct_probe_refresh_error",
  "internal_probe_source",
  "internal_probe_observed_at",
  "internal_probe_age_seconds",
  "internal_probe_refresh_error",
  "probe_interval_seconds",
  "next_probe_in_seconds",
  "runtime_state",
  "runtime_app",
  "runtime_reachable",
  "tunnel_status",
  "tunnel_name",
  "cloudflare_status_confirmed",
  "cloudflare_warning",
];

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function hostOf(value) {
  if (!value) return "";
  try {
    return new URL(String(value)).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function evidenceIndexes(rows) {
  const byId = new Map();
  const byHost = new Map();
  const byName = new Map();
  for (const row of rows) {
    if (row?.id) byId.set(String(row.id), row);
    const host = hostOf(row?.url);
    if (host && !byHost.has(host)) byHost.set(host, row);
    const name = normalize(row?.name);
    if (name && !byName.has(name)) byName.set(name, row);
  }
  return { byId, byHost, byName };
}

function candidateServiceIds(key, check) {
  const ids = [check?.service_id, check?.id, key];
  if (String(key).startsWith("albandrieu_"))
    ids.push(String(key).slice("albandrieu_".length));
  return ids.filter(Boolean).map((value) => String(value).replaceAll("_", "-"));
}

function evidenceForCheck(key, check, indexes) {
  for (const candidate of candidateServiceIds(key, check)) {
    if (indexes.byId.has(candidate)) return indexes.byId.get(candidate);
  }
  for (const value of [check?.url, check?.tunnel_url, check?.tunnelUrl, check?.href]) {
    const host = hostOf(value);
    if (host && indexes.byHost.has(host)) return indexes.byHost.get(host);
  }
  for (const value of [check?.name, check?.display_label]) {
    const name = normalize(value);
    if (name && indexes.byName.has(name)) return indexes.byName.get(name);
  }
  return null;
}

export function mergeHomelabEvidence(data, homelab) {
  const rows = Array.isArray(homelab?.services) ? homelab.services : [];
  const indexes = evidenceIndexes(rows);
  for (const [key, check] of Object.entries(data?.checks || {})) {
    const evidence = evidenceForCheck(key, check, indexes);
    if (!evidence) continue;
    for (const field of HOMELAB_EVIDENCE_FIELDS) {
      if (Object.prototype.hasOwnProperty.call(evidence, field)) check[field] = evidence[field];
    }
  }
  return data;
}

export function dependencyHealthClass(check) {
  if (!check?.effective_state) return null;
  if (check.effective_state === "ok") return "green";
  if (check.effective_state === "warn") return "yellow";
  if (check.effective_state === "fail") return "red";
  if (check.reachable === true) return null;
  return "gray";
}

function dependencyLabels(check, field) {
  const targets = new Set(Array.isArray(check?.[field]) ? check[field] : []);
  if (targets.size === 0) return [];
  const evidence = Array.isArray(check.dependency_evidence) ? check.dependency_evidence : [];
  return [...targets].map((target) => {
    const item = evidence.find((entry) => entry?.target === target);
    return String(item?.target_name || target);
  });
}

function probeEvidenceLabel(label, source, ageSeconds, refreshError) {
  if (!source) return label;
  const age = Number(ageSeconds);
  const suffix =
    source === "memory"
      ? `cached${Number.isFinite(age) ? ` ${Math.round(age)}s` : ""}`
      : source === "deadline"
        ? "deadline"
        : "fresh";
  return [
    `${label} (${suffix})`,
    refreshError ? `refresh: ${String(refreshError)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function evidenceSources(check) {
  const sources = [];
  if (check.direct_state)
    sources.push(
      probeEvidenceLabel(
        "HTTP",
        check.direct_probe_source,
        check.direct_probe_age_seconds,
        check.direct_probe_refresh_error,
      ),
    );
  if (check.internal_state)
    sources.push(
      probeEvidenceLabel(
        "internal probe",
        check.internal_probe_source,
        check.internal_probe_age_seconds,
        check.internal_probe_refresh_error,
      ),
    );
  if (check.runtime_state) sources.push("TrueNAS runtime");
  if (check.tunnel_status) sources.push("Cloudflare tunnel");
  return sources;
}

export function dependencyDetailText(check) {
  if (!check?.effective_state) return "";
  const parts = [];
  const runtimeRunning = String(check.runtime_state || "").toUpperCase() === "RUNNING";
  if (runtimeRunning && check.effective_state !== "ok") parts.push("RUNNING but degraded");
  if (check.local_state && check.local_state !== check.effective_state) {
    parts.push(`local ${check.local_state} → effective ${check.effective_state}`);
  }
  const blocked = dependencyLabels(check, "blocked_by");
  if (blocked.length > 0) parts.push(`blocked by ${blocked.join(", ")}`);
  const degraded = dependencyLabels(check, "degraded_by");
  if (degraded.length > 0) parts.push(`degraded by ${degraded.join(", ")}`);
  const unconfirmed = dependencyLabels(check, "unconfirmed_dependencies");
  if (unconfirmed.length > 0)
    parts.push(`dependency status unconfirmed: ${unconfirmed.join(", ")}`);
  const sources = evidenceSources(check);
  if (sources.length > 0) parts.push(`evidence: ${sources.join(" + ")}`);
  if (check.cloudflare_status_confirmed === false && check.cloudflare_warning) {
    parts.push(String(check.cloudflare_warning));
  }
  if (check.observation_stale === true) {
    const age = Number(check.observation_age_seconds);
    parts.push(
      Number.isFinite(age)
        ? `stale evidence (${Math.round(age)}s old)`
        : "stale evidence",
    );
  } else if (check.observation_age_seconds != null) {
    const age = Number(check.observation_age_seconds);
    if (Number.isFinite(age)) parts.push(`observed ${Math.round(age)}s ago`);
  }
  const cycle = Array.isArray(check.dependency_cycle) ? check.dependency_cycle : [];
  if (cycle.length > 1) parts.push(`dependency cycle: ${cycle.join(" ↔ ")}`);
  return parts.join(" · ");
}
