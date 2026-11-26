// Retain ONLY the allowlisted PUBLIC service summary, never raw probes or OWNER
// telemetry. The restored values are always historical until revalidated.
const KEY = "nabla:api:public-last-observed:v1";
// Historical PUBLIC-only summary; never treated as live or used for probe verdicts.
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_BYTES = 160000;
const MAX_SERVICES = 1000;
const STATES = new Set(["ok", "warn", "fail", "unknown", "scheduled"]);
const KINDS = new Set(["API", "Component", "Resource"]);
const SAFE_NAME = /^[\p{L}\p{N}][\p{L}\p{N} ._()+&-]{0,127}$/u;
const SAFE_SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/;
const IP_LITERAL = /\b(?:\d{1,3}\.){3}\d{1,3}\b/;

function sanitize(payload) {
  if (
    payload?.schemaVersion !== 2 ||
    payload.model !== "public-service-overview" ||
    payload.catalogSource !== "backstage-v2" ||
    payload.boardState !== "fresh" ||
    !/^sha256:[a-f0-9]{64}$/.test(payload.catalogRevision || "") ||
    !Array.isArray(payload.services) ||
    !payload.services.length ||
    payload.services.length > MAX_SERVICES
  )
    return null;

  const services = [];
  for (const item of payload.services) {
    if (
      !item ||
      typeof item.name !== "string" ||
      !SAFE_NAME.test(item.name) ||
      IP_LITERAL.test(item.name) ||
      !KINDS.has(item.kind) ||
      !STATES.has(item.state)
    )
      return null;
    if (item.serviceType != null && !SAFE_SLUG.test(item.serviceType))
      return null;
    if (
      item.tags != null &&
      (!Array.isArray(item.tags) ||
        item.tags.length > 3 ||
        !item.tags.every(
          (tag) => typeof tag === "string" && SAFE_SLUG.test(tag),
        ))
    )
      return null;
    services.push({
      name: item.name,
      kind: item.kind,
      state: item.state,
      ...(item.serviceType ? { serviceType: item.serviceType } : {}),
      ...(item.tags?.length ? { tags: item.tags.slice() } : {}),
    });
  }
  return {
    schemaVersion: 2,
    model: "public-service-overview",
    catalogSource: "backstage-v2",
    boardState: "fresh",
    catalogRevision: payload.catalogRevision,
    services,
  };
}

export function publicObservationStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function savePublicObservation(storage, payload, now = Date.now()) {
  const directory = sanitize(payload);
  if (!directory || !storage || !Number.isSafeInteger(now) || now < 0)
    return false;
  const encoded = JSON.stringify({ version: 1, receivedAt: now, directory });
  if (encoded.length > MAX_BYTES) return false;
  try {
    storage.setItem(KEY, encoded);
    return true;
  } catch {
    return false;
  }
}

export function readPublicObservation(storage, now = Date.now()) {
  if (!storage || !Number.isSafeInteger(now) || now < 0) return null;
  try {
    const raw = storage.getItem(KEY);
    if (typeof raw !== "string" || raw.length > MAX_BYTES) return null;
    const saved = JSON.parse(raw);
    if (
      saved?.version !== 1 ||
      !Number.isSafeInteger(saved.receivedAt) ||
      saved.receivedAt < 0 ||
      saved.receivedAt > now + 30000 ||
      now - saved.receivedAt > MAX_AGE_MS
    )
      return null;
    const directory = sanitize(saved.directory);
    if (!directory) return null;
    return { receivedAt: saved.receivedAt, directory };
  } catch {
    return null;
  }
}

export function clearPublicObservation(storage) {
  try {
    storage?.removeItem(KEY);
  } catch {
    // Storage is optional; browser privacy settings never block the page.
  }
}

export function publicObservationAge(receivedAt, now = Date.now()) {
  const age = Math.max(0, now - receivedAt);
  if (age < 60000) return "less than 1 min";
  if (age < 3600000) return Math.floor(age / 60000) + " min";
  if (age < 86400000) return Math.floor(age / 3600000) + " h";
  const days = Math.floor(age / 86400000);
  return days + (days === 1 ? " day" : " days");
}
