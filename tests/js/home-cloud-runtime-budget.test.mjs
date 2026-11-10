import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

function el(id) {
  return {
    id,
    hidden: false,
    disabled: false,
    textContent: "",
    dataset: {},
    style: {},
    classList: { contains: () => false },
    replaceChildren() {},
    setAttribute() {},
    append() {},
    addEventListener() {},
  };
}

test("FastAPI Cloud idle tab does not repeatedly wake an autoscaled instance", async () => {
  const previous = Object.fromEntries(
    [
      "document",
      "window",
      "fetch",
      "setInterval",
      "setTimeout",
      "clearTimeout",
    ].map((name) => [name, globalThis[name]]),
  );
  const realNow = Date.now;
  const nodes = new Map();
  const events = new Map();
  const intervals = [];
  const calls = [];
  const session = new Map();
  let clock = 1800000000000;
  const get = (id) => {
    if (!nodes.has(id)) nodes.set(id, el(id));
    return nodes.get(id);
  };
  try {
    Date.now = () => clock;
    globalThis.document = {
      hidden: false,
      getElementById: get,
      createElement: () => el("span"),
      createElementNS: (_, kind) => el(kind),
      addEventListener: (name, fn) => events.set(name, fn),
    };
    globalThis.window = {
      location: { hostname: "fastapi-sample.fastapicloud.dev" },
      sessionStorage: {
        getItem: (key) => session.get(key) || null,
        setItem: (key, value) => session.set(key, value),
        removeItem: (key) => session.delete(key),
      },
    };
    globalThis.setInterval = (fn, ms) => {
      intervals.push({ fn, ms });
    };
    globalThis.setTimeout = () => 1;
    globalThis.clearTimeout = () => {};
    globalThis.fetch = async (url) => {
      calls.push(url);
      if (url === "/api/ui/session") {
        return { ok: true, json: async () => ({ authenticated: false }) };
      }
      if (url !== "/api/ui/services")
        throw Error("Unexpected protected request");
      return {
        ok: true,
        json: async () => ({
          schemaVersion: 2,
          model: "public-service-overview",
          catalogRevision: "sha256:" + "a".repeat(64),
          catalogSource: "backstage-v2",
          boardState: "fresh",
          services: [{ name: "Gatus", kind: "Component", state: "ok" }],
        }),
      };
    };

    await import(
      new URL(
        "../../nabla/api/assets/home-operations.js?cloud-budget",
        import.meta.url,
      )
    );
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(intervals.length, 1);
    assert.equal(intervals[0].ms, 60000);
    assert.deepEqual(calls, ["/api/ui/services", "/api/ui/session"]);

    clock += 6 * 60 * 1000;
    intervals[0].fn();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(calls.length, 2, "No background requests during idle");
    assert.match(get("home-retry-status").textContent, /pause/i);

    assert.ok(events.has("pointerdown"));
    events.get("pointerdown")();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(calls.length, 4, "One resumed refresh, not a poll storm");
    assert.deepEqual(calls.slice(-2), ["/api/ui/services", "/api/ui/session"]);
  } finally {
    Date.now = realNow;
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test("Cloud budget neither changes LAN polling nor permits browser cron", () => {
  const code = readFileSync(
    new URL("../../nabla/api/assets/home-operations.js", import.meta.url),
    "utf8",
  );
  assert.match(code, /CLOUD_IDLE_POLL_PAUSE_MS = 5 \* 60 \* 1000/);
  assert.match(code, /const INTERVAL_MS = CLOUD_RUNTIME \? 60000 : 30000/);
  assert.match(code, /if \(cloudPollingIdle\(\)\)/);
  assert.match(code, /document\.addEventListener\("pointerdown"/);
  assert.doesNotMatch(code, /localStorage\./);
});
