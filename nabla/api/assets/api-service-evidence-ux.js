// Pure presentation helpers for the existing bounded /api/health-board snapshot.
// These functions never fetch endpoints or infer health from a missing sample.
export const EVIDENCE_GROUPS = Object.freeze([
  "Access / tokens", "DNS", "TCP / TLS", "HTTP", "Metrics / exporters",
  "Gatus checks", "Other signals",
]);

export function evidenceGroup(probe = {}) {
  const text = [probe.kind, probe.label, probe.detail].join(" ").toLowerCase();
  if (/cloudflare access|service token|access token|\btoken\b|\bauth(?:entication|orization)?\b|\b401\b|\b403\b/.test(text))
    return "Access / tokens";
  if (/\bgatus\b|synthetic|monitor check/.test(text)) return "Gatus checks";
  if (/prometheus|exporter|scrape|\bmetrics?\b|pg_up|redis_up/.test(text))
    return "Metrics / exporters";
  if (/\bdns\b|resolver|unbound|lookup|nxdomain/.test(text)) return "DNS";
  if (/\btls\b|ssl|certificate|\btcp\b|socket|connect|port /.test(text))
    return "TCP / TLS";
  if (/\bhttps?\b|\bhttp\b|status code|websocket|endpoint/.test(text))
    return "HTTP";
  return "Other signals";
}

export function sanitizedEvidence(value) {
  return String(value ?? "")
    .replace(/(bearer\s+)[a-z0-9._~+/-]+/gi, "$1[redacted]")
    .replace(/((?:cf-access-client-secret|authorization|api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*)[^\s,;&]+/gi, "$1[redacted]")
    .replace(/([?&](?:token|key|secret|password|access_token)=)[^&#\s]+/gi, "$1[redacted]")
    .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, "$1[credentials-redacted]@")
    .slice(0, 700);
}

export function evidenceAdvice(probe = {}) {
  const group = evidenceGroup(probe);
  const detail = String(probe.detail || "").toLowerCase();
  const unhealthy = ["fail", "warn"].includes(probe.tone);
  if (!unhealthy) return {
    group, reason: "No confirmed failure in this signal.",
    action: "Check source and observation age before interpreting availability.",
  };
  if (/\b401\b/.test(detail)) return {
    group, reason: "HTTP 401 — authentication rejected.",
    action: "Check the configured identity and token validity at the observing origin; never paste token values here.",
  };
  if (/\b403\b/.test(detail)) return {
    group, reason: "HTTP 403 — access denied. This is not proof the service is offline.",
    action: "Review Cloudflare Access policy, observer identity, IP allowlist and route authorization.",
  };
  if (/nxdomain|no such host|name or service not known|dns timeout|resolver/.test(detail))
    return {
      group, reason: "DNS resolution failure or unavailable resolver evidence.",
      action: "Compare the resolver and DNS answers from the LAN observer and cloud runtime.",
    };
  if (/timeout|timed out/.test(detail)) return {
    group, reason: "Probe timed out; the cause is not established.",
    action: "Check source vantage, DNS, TCP connectivity and the relevant endpoint latency.",
  };
  if (group === "Metrics / exporters") return {
    group, reason: "Metrics or exporter evidence is degraded.",
    action: "Compare target scrape UP with application metrics (for example pg_up); verify freshness.",
  };
  if (group === "Gatus checks") return {
    group, reason: "A Gatus check failed; scrape status alone cannot explain the target result.",
    action: "Inspect the configured monitor, its origin, target protocol and latest check result.",
  };
  return {
    group, reason: "This probe reports a degraded or failed observation.",
    action: "Inspect its source, transport and last confirmed timestamp before remediation.",
  };
}

export function evidenceCounts(probes = []) {
  const totals = { failed: 0, warning: 0, info: 0, unknown: 0, notRun: 0, up: 0 };
  for (const probe of probes) {
    if (probe.disabled) totals.notRun++;
    else if (probe.tone === "fail") totals.failed++;
    else if (probe.tone === "warn") totals.warning++;
    else if (probe.tone === "ok") totals.up++;
    else if (probe.tone === "info") totals.info++;
    else totals.unknown++;
  }
  return totals;
}

export function validServiceId(value) {
  return typeof value === "string" &&
    /^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}$/.test(value) &&
    !value.includes("://") && !value.includes("//") &&
    !/(^|\/)\.\.?(\/|$)/.test(value);
}

export function requestedServiceId(search) {
  const id = new URLSearchParams(String(search || "").replace(/^\?/, "")).get("service");
  return validServiceId(id) ? id : null;
}
