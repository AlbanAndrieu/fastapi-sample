import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  readPublicObservation,
  savePublicObservation,
} from "../../nabla/api/assets/api-public-observation-cache.js";
import { reconcilePublicObservation } from "../../nabla/api/assets/api-public-services.js";

const REVISION = "sha256:" + "a".repeat(64);
const OTHER = "sha256:" + "b".repeat(64);
const service = { name: "Gatus", kind: "Component", state: "ok" };
const snapshot = (state, revision = REVISION, source = "backstage-v2") => ({
  schemaVersion: 2,
  model: "public-service-overview",
  boardState: state,
  catalogRevision: revision,
  catalogSource: source,
  services: [service],
});

test("historical last known survives a pending response on the same catalog", () => {
  const result = reconcilePublicObservation(snapshot("pending"), {
    catalogRevision: REVISION,
    services: [service],
  });
  assert.equal(result.historical, true);
  assert.equal(result.rows[0].state, "ok");
});

test("fresh evidence supersedes history; revision drift and bootstrap never claim live health", () => {
  const old = { catalogRevision: REVISION, services: [service] };
  assert.deepEqual(reconcilePublicObservation(snapshot("fresh"), old), {
    historical: false,
    rows: [service],
  });
  for (const result of [
    reconcilePublicObservation(snapshot("pending", OTHER), old),
    reconcilePublicObservation(
      snapshot("fresh", OTHER, "bootstrap-snapshot"),
      old,
    ),
  ]) {
    assert.equal(result.historical, false);
    assert.equal(result.rows[0].state, "unknown");
  }
});

test("a six-hour revisit retains only the historical public summary", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key),
    setItem: (key, value) => values.set(key, value),
  };
  const start = Date.parse("2026-11-14T12:00:00Z");
  assert.equal(savePublicObservation(storage, snapshot("fresh"), start), true);
  const cached = readPublicObservation(storage, start + 6 * 3600000);
  assert.ok(cached);
  const view = reconcilePublicObservation(snapshot("pending"), {
    catalogRevision: cached.directory.catalogRevision,
    services: cached.directory.services,
  });
  assert.equal(view.historical, true);
  assert.equal(view.rows[0].state, "ok");
});

test("UI paints dated neutral history before network and rechecks on resume", () => {
  const source = readFileSync(
    new URL("../../nabla/api/assets/api-public-services.js", import.meta.url),
    "utf8",
  );
  assert.ok(
    source.indexOf("const cached = readPublicObservation(storage)") <
      source.indexOf("if (!document.hidden) await load()"),
  );
  assert.match(source, /state\.textContent = historical/);
  assert.match(source, /publicObservationAge\(receivedAt\)/);
  assert.match(source, /lastReceivedAt/);
  for (const event of ["visibilitychange", "pageshow", "online"]) {
    assert.ok(source.includes(event));
  }
  assert.match(source, /clearPublicObservation\(storage\)/);
  assert.match(source, /CLOUD_RECHECK_MS = 180000/);
  assert.match(source, /LOCAL_RECHECK_MS = 30000/);
  assert.doesNotMatch(
    source,
    /health-board\/refresh|localStorage|sessionStorage|DIAGNOSTICS_ACCESS_KEY/,
  );
});

test("home retains its isolated inventory cache but labels and greys last-known counts", () => {
  const source = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  const styles = readFileSync(
    new URL("../../nabla/api/assets/home-operations.css", import.meta.url),
    "utf8",
  );
  assert.match(source, /function paintLastObservedFleet/);
  assert.match(source, /boardState: "historical"/);
  assert.match(
    source,
    /paintLastObservedFleet\(publicResult\.value\.catalogRevision\)/,
  );
  assert.match(source, /savePublicObservation/);
  assert.match(styles, /\[data-historical="true"\] \.op-meter-segment/);
  assert.doesNotMatch(source, /localStorage|DIAGNOSTICS_ACCESS_KEY/);
});
