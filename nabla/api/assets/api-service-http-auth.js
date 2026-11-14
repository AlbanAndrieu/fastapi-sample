// Transport evidence is not application readiness. These are explicitly
// documented anonymous responses on selected private application surfaces.
// Do not generalize a 401/403 into "healthy" or suppress a failed authenticated
// request, an untrusted/stale sample or a security exposure violation.
const EXPECTED_ANONYMOUS = Object.freeze({
  garage: { statuses: [401, 403], paths: ["/"] },
  litellm: { statuses: [401], paths: ["/", "/health"] },
  "litellm-albandrieu": { statuses: [401], paths: ["/", "/health"] },
});

function normalizedId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^albandrieu_/, "")
    .replaceAll("_", "-");
}

function requestPath(check) {
  if (typeof check?.path === "string" && check.path.startsWith("/")) {
    return check.path.split(/[?#]/, 1)[0];
  }
  const raw = check?.url || check?.tunnel_url || "";
  try {
    return new URL(raw).pathname;
  } catch {
    return "";
  }
}

export function expectedAnonymousAuth(serviceId, check) {
  const profile = EXPECTED_ANONYMOUS[normalizedId(serviceId)];
  if (
    !profile ||
    !check ||
    check.skipped === true ||
    check.stale === true ||
    check.probe_stale === true ||
    check.observation_stale === true
  )
    return null;
  const status = Number(check.http_status);
  if (!profile.statuses.includes(status)) return null;
  const path = requestPath(check);
  if (path && !profile.paths.includes(path)) return null;
  // A refused submitted credential is NOT an expected anonymous challenge.
  if (
    check.authenticated_http_status != null ||
    check.cloudflare_service_auth_attempted === true ||
    check.auth_attempted === true ||
    check.credentials_present === true
  )
    return null;
  const mode = String(check.public_probe_auth_mode || "").toLowerCase();
  if (/^authenticated|token_submitted|service_token_sent/.test(mode))
    return null;
  const stage = String(check.failure_stage || "").toLowerCase();
  if (/dns|tcp|tls|connect|certificate/.test(stage)) return null;
  return {
    tone: "info",
    status,
    label: `Auth ${status} · expected`,
    detail: `HTTP ${status} · authentication required (expected for unauthenticated request). An HTTP server responded; application readiness, successful login and exposure policy are not proven. Verify the separate Docker healthcheck or authorized functional probe.`,
  };
}

// A skipped check or a catalogue placeholder (reachable=false with no error,
// status or timestamp) is not an observation.
function observedHttp(check) {
  if (!check || check.skipped === true) return false;
  return (
    check.reachable === true ||
    Number(check.http_status) > 0 ||
    Boolean(
      check.error ||
        check.failure_stage ||
        check.alias_results ||
        check.observed_at ||
        check.probe_observed_at ||
        check.direct_probe_observed_at ||
        check.checked_at,
    )
  );
}

// Every module that tones the HTTP badge must pick the same evidence, or the
// badge flips between them on each refresh.
export function firstObservedCheck(...candidates) {
  return (
    candidates.find(observedHttp) ||
    candidates.find((check) => check && check.skipped !== true) ||
    candidates.find(Boolean) ||
    null
  );
}

// An internal-only service has no public route: an unanswered public HTTP
// probe is the intended outcome. Any HTTP answer stays an exposure finding.
export function expectedHttpFailure(check) {
  if (!observedHttp(check) || check.reachable !== false) return null;
  const status = Number(check.http_status);
  if (Number.isFinite(status) && status > 0) return null;
  const internal =
    check.external === false || check.exposure_intent === "internal";
  if (!internal) return null;
  return {
    tone: "expected",
    detail:
      "HTTP failure expected by design: the service is internal-only, so its public hostname must not answer. LAN TCP/runtime evidence is the health signal.",
  };
}

export function httpObservationTone(check, serviceId) {
  if (!check) return "unknown";
  if (check.skipped === true) return "neutral";
  if (expectedAnonymousAuth(serviceId, check)) return "info";
  const status = Number(check.http_status);
  if (Number.isFinite(status) && status > 0) {
    if (status >= 200 && status < 400) return "ok";
    if (status >= 500) return "fail";
    return "warn";
  }
  if (check.reachable === true) return "ok";
  if (expectedHttpFailure(check)) return "expected";
  if (check.reachable === false) return "fail";
  return "unknown";
}
