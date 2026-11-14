import assert from "node:assert/strict";
import { test } from "node:test";
import {
  clearPublicObservation,
  publicObservationAge,
  readPublicObservation,
  savePublicObservation,
} from "../../nabla/api/assets/api-public-observation-cache.js";

const NOW = Date.parse("2026-11-14T15:00:00Z");
const REVISION = "sha256:" + "a".repeat(64);
const example = () => ({
  schemaVersion: 2,
  model: "public-service-overview",
  boardState: "fresh",
  catalogSource: "backstage-v2",
  catalogRevision: REVISION,
  services: [
    {
      name: "Gatus",
      kind: "Component",
      state: "ok",
      serviceType: "monitoring",
      tags: ["observability"],
      owner: "private-owner",
      url: "http://172.17.0.24:8085",
      probes: [{ token: "PRIVATE_TOKEN" }],
    },
    { name: "PostgreSQL", kind: "Resource", state: "warn" },
  ],
  healthz: { checks: { secrets: "PRIVATE_TOKEN" } },
});

function storage() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
    dump: () => [...data.values()].join(""),
  };
}

test("last PUBLIC summary survives hours, but excludes private fields and raw probes", () => {
  const cache = storage();
  assert.equal(savePublicObservation(cache, example(), NOW), true);
  assert.doesNotMatch(
    cache.dump(),
    /PRIVATE_TOKEN|private-owner|172\.17\.|probes|healthz|url/,
  );
  const restored = readPublicObservation(cache, NOW + 6 * 3600000);
  assert.ok(restored);
  assert.equal(restored.receivedAt, NOW);
  assert.deepEqual(restored.directory.services.map(({ state }) => state), [
    "ok",
    "warn",
  ]);
  assert.equal(restored.directory.services[0].serviceType, "monitoring");
});

test("missing, expired, future or tampered cache fails closed", () => {
  const cache = storage();
  assert.equal(readPublicObservation(cache, NOW), null);
  savePublicObservation(cache, example(), NOW);
  assert.equal(
    readPublicObservation(cache, NOW + 24 * 3600000)?.receivedAt,
    NOW,
  );
  assert.equal(readPublicObservation(cache, NOW + 24 * 3600000 + 1), null);
  assert.equal(readPublicObservation(cache, NOW - 31000), null);
  const item = JSON.parse(cache.dump());
  item.directory.services[0].name = "http://172.17.0.24:8085";
  cache.setItem("nabla:api:public-last-observed:v1", JSON.stringify(item));
  assert.equal(readPublicObservation(cache, NOW + 1000), null);
});

test("only freshly verified canonical public responses can replace last known", () => {
  const cache = storage();
  const original = example();
  assert.equal(savePublicObservation(cache, original, NOW), true);
  const first = cache.dump();
  for (const invalid of [
    { ...original, boardState: "pending" },
    { ...original, boardState: "stale" },
    { ...original, catalogSource: "bootstrap-snapshot" },
    {
      ...original,
      services: [{ name: "<script>", kind: "Component", state: "ok" }],
    },
    {
      ...original,
      services: [{ name: "ok", kind: "Component", state: "FAIL" }],
    },
    {
      ...original,
      services: [{ name: "172.17.0.24", kind: "Resource", state: "ok" }],
    },
    { ...original, services: [] },
  ]) {
    assert.equal(savePublicObservation(cache, invalid, NOW + 1), false);
    assert.equal(cache.dump(), first);
  }
  clearPublicObservation(cache);
  assert.equal(readPublicObservation(cache, NOW + 10), null);
});

test("browser storage denial is not an application failure", () => {
  const denied = {
    getItem: () => {
      throw Error("SecurityError");
    },
    setItem: () => {
      throw Error("QuotaExceededError");
    },
    removeItem: () => {
      throw Error("SecurityError");
    },
  };
  assert.equal(savePublicObservation(denied, example(), NOW), false);
  assert.equal(readPublicObservation(denied, NOW), null);
  assert.doesNotThrow(() => clearPublicObservation(denied));
  assert.equal(publicObservationAge(NOW, NOW + 5 * 60000), "5 min");
  assert.equal(publicObservationAge(NOW, NOW + 3 * 3600000), "3 h");
});
