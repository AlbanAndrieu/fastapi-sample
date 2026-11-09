import assert from "node:assert/strict";
import { test } from "node:test";

const REVISION = "sha256:" + "a".repeat(64);

function publicServices(state) {
  return {
    schemaVersion: 2,
    model: "public-service-overview",
    catalogRevision: REVISION,
    catalogSource: "backstage-v2",
    boardState: state,
    services: [
      { name: "Gatus", kind: "Component", state: state === "fresh" ? "ok" : "unknown" },
      { name: "TrueNAS", kind: "Resource", state: state === "fresh" ? "fail" : "unknown" },
    ],
  };
}

function browserNode(id) {
  return {
    id,
    hidden: false,
    disabled: false,
    dataset: {},
    style: {},
    textContent: "",
    classList: { contains: () => false },
    replaceChildren() {},
    append() {},
    setAttribute() {},
    addEventListener() {},
  };
}

test("cold Cloud page retries pending automatically without clicking Actualiser", async () => {
  const previous = Object.fromEntries(
    ["document", "window", "fetch", "setInterval", "setTimeout", "clearTimeout"]
      .map((name) => [name, globalThis[name]]),
  );
  const nodes = new Map();
  const timers = [];
  const calls = [];
  const session = new Map();
  let reads = 0;
  const get = (id) => {
    if (!nodes.has(id)) nodes.set(id, browserNode(id));
    return nodes.get(id);
  };
  try {
    globalThis.document = {
      hidden: false,
      getElementById: get,
      createElement: () => browserNode("span"),
      createElementNS: (_namespace, tag) => browserNode(tag),
      addEventListener() {},
    };
    globalThis.window = {
      sessionStorage: {
        getItem: (key) => session.get(key) || null,
        setItem: (key, value) => session.set(key, value),
        removeItem: (key) => session.delete(key),
      },
    };
    globalThis.setInterval = () => 1;
    globalThis.setTimeout = (fn, ms) => {
      const timer = { fn, ms, cleared: false };
      timers.push(timer);
      return timer;
    };
    globalThis.clearTimeout = (timer) => { timer.cleared = true; };
    globalThis.fetch = async (url) => {
      calls.push(url);
      if (url === "/api/ui/session") {
        return { ok: true, json: async () => ({ authenticated: false }) };
      }
      if (url !== "/api/ui/services") {
        throw Error("Unexpected private request " + url);
      }
      const data = publicServices(++reads === 1 ? "pending" : "fresh");
      return { ok: true, json: async () => data };
    };

    await import(
      new URL("../../nabla/api/assets/home-operations.js?auto-warmup", import.meta.url)
    );
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(get("home-services").textContent, "2");
    assert.equal(get("home-unknown").textContent, "2");
    assert.equal(get("home-ok").textContent, "0");
    const retry = timers.find((timer) => !timer.cleared && timer.ms === 2000);
    assert.ok(retry, "Pending response must schedule another read in two seconds");
    const cached = Array.from(session.values()).join("");
    assert.match(cached, /"unknown"/);
    assert.doesNotMatch(cached, /"ok"|"fail"|"warn"|token/i);

    retry.cleared = true;
    retry.fn();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(get("home-ok").textContent, "1");
    assert.equal(get("home-fail").textContent, "1");
    assert.equal(get("home-unknown").textContent, "0");
    assert.deepEqual(calls, [
      "/api/ui/services", "/api/ui/session",
      "/api/ui/services", "/api/ui/session",
    ]);
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});
