import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  discardPublicDirectory,
  persistPublicDirectory,
  restorePublicDirectory,
} from "../../nabla/api/assets/home-public-cache.js";
import { projectFleet } from "../../nabla/api/assets/home-operations-model.js";

const NOW = Date.parse("2026-11-09T12:00:00Z");
function source() {
  return {
    schemaVersion: 2,
    model: "public-service-overview",
    catalogRevision: "sha256:" + "a".repeat(64),
    catalogSource: "backstage-v2",
    boardState: "fresh",
    services: [
      { name: "Gatus", kind: "Component", state: "ok" },
      { name: "TrueNAS", kind: "Resource", state: "fail" },
    ],
  };
}

function memoryStorage() {
  const items = new Map();
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => { items.set(key, value); },
    removeItem: (key) => { items.delete(key); },
    snapshot: () => Array.from(items.values()).join(""),
  };
}

test("session cache stores public names/kinds but NEVER status or secrets", () => {
  const storage = memoryStorage();
  const payload = source();
  assert.equal(persistPublicDirectory(storage, payload, NOW), true);
  const raw = JSON.parse(storage.snapshot());
  assert.deepEqual(
    raw.directory.services.map((row) => Object.keys(row).sort()),
    [["kind", "name", "state"], ["kind", "name", "state"]],
  );
  assert.deepEqual(raw.directory.services.map((row) => row.state), [
    "unknown", "unknown",
  ]);
  assert.equal(raw.directory.boardState, "stale");
  assert.doesNotMatch(storage.snapshot(), /"ok"|"fail"|"warn"|secret|token|172\.17\./i);
  const restored = restorePublicDirectory(storage, NOW + 1000);
  const fleet = projectFleet(restored);
  assert.deepEqual(fleet.counts, { ok: 0, warn: 0, fail: 0, unknown: 2 });
});

test("expired and future cache entries cannot be restored", () => {
  const storage = memoryStorage();
  persistPublicDirectory(storage, source(), NOW);
  assert.ok(restorePublicDirectory(storage, NOW + 5 * 60000));
  assert.equal(restorePublicDirectory(storage, NOW + 5 * 60000 + 1), null);
  assert.equal(restorePublicDirectory(storage, NOW - 31000), null);
  discardPublicDirectory(storage);
  assert.equal(restorePublicDirectory(storage, NOW), null);
});

test("invalid labels, private network addresses and malformed revision never persist", () => {
  const storage = memoryStorage();
  for (const mutation of [
    { services: [{ name: "172.17.0.24", kind: "Resource", state: "ok" }] },
    { services: [{ name: "https://private.example", kind: "Resource", state: "ok" }] },
    { catalogRevision: "unverified" },
    { services: [{ name: "<script>", kind: "Resource", state: "ok" }] },
    { services: [{ name: "X", kind: "Invalid", state: "ok" }] },
    { services: [] },
  ]) {
    assert.equal(persistPublicDirectory(storage, { ...source(), ...mutation }, NOW), false);
    assert.equal(storage.snapshot(), "");
  }
});

test("storage denied or corrupted cache never prevents rendering", () => {
  const blocked = {
    getItem: () => { throw Error("SecurityError"); },
    setItem: () => { throw Error("QuotaExceededError"); },
    removeItem: () => { throw Error("SecurityError"); },
  };
  assert.equal(restorePublicDirectory(blocked, NOW), null);
  assert.equal(persistPublicDirectory(blocked, source(), NOW), false);
  assert.doesNotThrow(() => discardPublicDirectory(blocked));
  const storage = memoryStorage();
  storage.setItem("nabla:home:public-directory:v1", "{ broken");
  assert.equal(restorePublicDirectory(storage, NOW), null);
});

test("cold start auto-retries without manual refresh or persisting OWNER data", () => {
  const script = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  assert.match(script, /WARMUP_DELAYS_MS = \[2000, 4000, 8000, 15000, 30000\]/);
  assert.match(script, /scheduleWarmupRetry\(\)/);
  assert.match(script, /setTimeout\(\(\) =>/);
  assert.match(script, /paintSessionDirectory\(\);/);
  assert.match(script, /const publicResult = await publicRequest/);
  assert.match(script, /const sessionResult = await sessionRequest/);
  assert.match(script, /fetchJSON\("\/api\/ui\/services"\)/);
  assert.match(script, /cache: "no-store"/);
  assert.doesNotMatch(script, /localStorage|DIAGNOSTICS_ACCESS_KEY|REDIS_URL/);
});
