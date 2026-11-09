// Session-only cache for the already-public directory. Never store probe
// statuses, OWNER data, network topology, authorization or secrets.
const CACHE_KEY = "nabla:home:public-directory:v1";
const MAX_AGE_MS = 5 * 60 * 1000;
const MAX_ITEMS = 1000;
const PUBLIC_NAME = /^[A-Za-z0-9][A-Za-z0-9 ._()+&-]{0,127}$/;
const IP_LITERAL = /\b(?:\d{1,3}\.){3}\d{1,3}\b/;
const KINDS = new Set(["API", "Component", "Resource"]);
const SOURCES = new Set(["backstage-v2", "bootstrap-snapshot"]);

function sanitizedDirectory(input) {
  if (input?.schemaVersion !== 2 || input?.model !== "public-service-overview" ||
      !SOURCES.has(input.catalogSource) ||
      typeof input.catalogRevision !== "string" ||
      !/^sha256:[0-9a-f]{64}$/.test(input.catalogRevision) ||
      !Array.isArray(input.services) || !input.services.length ||
      input.services.length > MAX_ITEMS) return null;
  const services = [];
  for (const service of input.services) {
    if (typeof service?.name !== "string" ||
        !PUBLIC_NAME.test(service.name) || IP_LITERAL.test(service.name) ||
        !KINDS.has(service.kind)) return null;
    services.push({ name: service.name, kind: service.kind, state: "unknown" });
  }
  return {
    schemaVersion: 2,
    model: "public-service-overview",
    catalogSource: input.catalogSource,
    catalogRevision: input.catalogRevision,
    boardState: "stale",
    services,
  };
}

export function persistPublicDirectory(storage, payload, nowMs = Date.now()) {
  const directory = sanitizedDirectory(payload);
  if (!directory || !storage || !Number.isFinite(nowMs)) return false;
  try {
    storage.setItem(CACHE_KEY, JSON.stringify({
      version: 1, storedAt: nowMs, directory,
    }));
    return true;
  } catch {
    return false; // Session storage may be disabled or quota exhausted.
  }
}

export function restorePublicDirectory(storage, nowMs = Date.now()) {
  if (!storage || !Number.isFinite(nowMs)) return null;
  try {
    const entry = JSON.parse(storage.getItem(CACHE_KEY) || "null");
    if (entry?.version !== 1 || !Number.isFinite(entry.storedAt) ||
        entry.storedAt > nowMs + 30000 ||
        nowMs - entry.storedAt > MAX_AGE_MS) return null;
    return sanitizedDirectory(entry.directory);
  } catch {
    return null; // Never break the page because storage is unavailable.
  }
}

export function discardPublicDirectory(storage) {
  try {
    storage?.removeItem(CACHE_KEY);
  } catch {
    // Storage may be blocked by browser privacy policy.
  }
}
