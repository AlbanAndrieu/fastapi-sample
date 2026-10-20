/** Render Garage members observed by the homelab without inventing healthz checks. */
const GARAGE_LABELS = new Map([
  ["garage", "Garage S3 API"],
  ["garage-admin", "Garage Admin API"],
  ["garage-webui", "Garage Web UI"],
]);
const HEALTH_STATES = new Set(["ok", "warn", "fail"]);
const PUBLIC_DISCOVERY_LABELS = new Map([
  ["gatus", "Gatus"],
  ["garage-webui", "Garage Web UI"],
]);

function rows(value) {
  return Array.isArray(value)
    ? value.filter((item) => item && typeof item === "object")
    : [];
}

function observedState(value) {
  return HEALTH_STATES.has(value) ? value : null;
}

function approvedWebUiUrl(source) {
  if (source?.exposure_intent !== "public") return "";
  const raw = source?.url;
  if (typeof raw !== "string") return "";
  try {
    const parsed = new URL(raw);
    if (
      parsed.protocol === "https:" &&
      parsed.hostname === "garage.albandrieu.com" &&
      !parsed.username &&
      !parsed.password
    ) {
      return parsed.origin;
    }
  } catch {
    // Unparseable URLs are not clickable.
  }
  return "";
}

function existingIds(checks) {
  const found = new Set();
  for (const [key, check] of Object.entries(checks)) {
    for (const id of GARAGE_LABELS.keys()) {
      if (
        key === id ||
        key === `albandrieu_${id.replaceAll("-", "_")}` ||
        check?.id === id ||
        check?.service_id === id
      ) {
        found.add(id);
      }
    }
  }
  return found;
}

function garageCheck(id, publicRow, internalRow, freshSnapshot) {
  const privateIntent = publicRow?.exposure_intent === "internal";
  const drift = privateIntent && publicRow?.unexpected_tunnel_route === true;
  const eligibleLan = Boolean(
    freshSnapshot &&
      internalRow &&
      internalRow.probe_stale !== true &&
      internalRow.probe_source !== "deadline" &&
      internalRow.timed_out !== true,
  );
  const lanState = eligibleLan
    ? observedState(internalRow.state || internalRow.internal_state)
    : null;
  const publicWarn = id === "garage-webui" && publicRow?.state === "warn";
  const risks = [];
  if (drift) risks.push("Unexpected public tunnel for internal-only Admin API");
  if (publicWarn) risks.push("Public origin status unconfirmed");
  const effective = lanState || "unknown";
  const warning = !freshSnapshot
    ? "Cached health-board snapshot: no current Garage probe attestation"
    : !lanState
      ? "Garage LAN evidence missing or stale; current health unconfirmed"
      : drift
        ? "LAN operational; unexpected public Admin route requires review"
        : publicWarn
          ? "LAN operational; public origin verification incomplete"
          : `LAN ${lanState}; external exposure not inferred from TCP`;
  const check = {
    id,
    service_id: id,
    name: GARAGE_LABELS.get(id),
    reachable: null,
    state: effective,
    local_state: effective,
    effective_state: effective,
    internal_state: lanState,
    risk_state: risks.length > 0 ? "at_risk" : "unknown",
    risk_reasons: risks,
    warning,
    exposure_intent: publicRow?.exposure_intent || null,
    unexpected_tunnel_route: drift,
  };
  if (id === "garage-webui") {
    const url = approvedWebUiUrl(publicRow);
    if (url) check.url = url;
  }
  return check;
}

export function includeObservedGarageChecks(
  data,
  homelab,
  snapshotState = "unknown",
) {
  const checks = data?.checks;
  if (!checks || typeof checks !== "object" || Array.isArray(checks))
    return data;
  const services = new Map(
    rows(homelab?.services)
      .filter((row) => GARAGE_LABELS.has(row.id))
      .map((row) => [row.id, row]),
  );
  const internal = new Map(
    rows(homelab?.internal_services)
      .filter((row) => GARAGE_LABELS.has(row.id))
      .map((row) => [row.id, row]),
  );
  const present = existingIds(checks);
  const projected = { ...checks };
  const fresh =
    snapshotState === "fresh" && homelab?.probe_cache?.stale !== true;
  for (const id of GARAGE_LABELS.keys()) {
    if (present.has(id) || (!services.has(id) && !internal.has(id))) continue;
    projected[id] = garageCheck(id, services.get(id), internal.get(id), fresh);
  }
  // The bounded 12-per-wave scheduler cannot be a service-discovery engine.
  // A curated public label may be visible even when no probe was sampled.
  // Do not synthesize successful health, URLs, or LAN infrastructure details.
  const candidates = rows(homelab?.public_card_candidates);
  for (const candidate of candidates) {
    const id = candidate.id;
    if (
      !PUBLIC_DISCOVERY_LABELS.has(id) ||
      candidate.name !== PUBLIC_DISCOVERY_LABELS.get(id) ||
      present.has(id) ||
      Object.hasOwn(projected, id)
    ) {
      continue;
    }
    projected[id] = {
      id,
      service_id: id,
      name: PUBLIC_DISCOVERY_LABELS.get(id),
      reachable: null,
      state: "unknown",
      local_state: "unknown",
      effective_state: "unknown",
      risk_state: "unknown",
      warning:
        "Declared public-facing service; no current independent probe evidence. Not confirmed DOWN.",
    };
  }
  return { ...data, checks: projected };
}
