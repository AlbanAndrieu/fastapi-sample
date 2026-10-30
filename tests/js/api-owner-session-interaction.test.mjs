import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const ownerSource = readFileSync(
  fileURLToPath(new URL("../../nabla/api/assets/api-owner-session.js", import.meta.url)),
  "utf8",
).replace(/^import \{ withRequestDeadline \} from "\.\/api-request-deadline\.js";\s*/m, "")
  .replace(/^export /gm, "");

async function flush() {
  for (let i = 0; i < 12; i += 1) await Promise.resolve();
}

// Execute the real OWNER controller with a simulated DOM. No browser,
// credentials, network or npm dependencies. Only synthetic keys are used.
function makeOwnerSession({ postStatus = 200, postCode = null } = {}) {
  const calls = [];
  const events = [];
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) {
      const listeners = new Map();
      elements.set(id, {
        hidden: true, textContent: "", value: "", dataset: {},
        focus() { events.push("input-focused"); },
        addEventListener(name, callback) {
          listeners.set(name, [...(listeners.get(name) || []), callback]);
        },
        listeners,
        async fire(name, event = {}) {
          for (const handler of listeners.get(name) || []) await handler(event);
        },
      });
    }
    return elements.get(id);
  };
  const context = {
    document: { hidden: false, getElementById: element, addEventListener() {} },
    window: {
      location: { reload() { events.push("reload"); } },
      addEventListener() {},
    },
    fetch: async (path, options) => {
      calls.push({ path, method: options?.method || "GET" });
      if (path === "/api/ui/session" && options?.method === "POST") {
        return {
          ok: postStatus === 200, status: postStatus,
          json: async () => postCode ? { code: postCode } : {},
        };
      }
      return {
        ok: true, status: 200,
        json: async () => ({ authenticated: false, readOnlyDiagnostics: true }),
      };
    },
    withRequestDeadline: async (callback) => callback(undefined),
  };
  const compiled = "(() => { " + ownerSource
    + "\nreturn { installOwnerSessionControls, ownerSessionAvailable }; })()";
  const api = runInNewContext(compiled, context, { timeout: 1000 });
  return { api, element, events, calls };
}

test("OWNER control installs one click handler and opens the form", async () => {
  const f = makeOwnerSession();
  f.api.installOwnerSessionControls(() => f.events.push("authorized"));
  f.api.installOwnerSessionControls(() => f.events.push("duplicate"));
  await flush();
  assert.equal(f.element("owner-session-login").listeners.get("click").length, 1);
  await f.element("owner-session-login").fire("click");
  assert.equal(f.element("owner-session-form").hidden, false);
  assert.ok(f.events.includes("input-focused"));
});

test("OWNER POST success clears the synthetic key and triggers callback once", async () => {
  const f = makeOwnerSession();
  f.api.installOwnerSessionControls(() => f.events.push("authorized"));
  await flush();
  await f.element("owner-session-login").fire("click");
  f.element("owner-session-key").value = "synthetic-fixture-not-a-real-key";
  await f.element("owner-session-form").fire("submit", { preventDefault() {} });
  assert.equal(f.element("owner-session-key").value, "");
  assert.equal(f.calls.filter((c) =>
    c.path === "/api/ui/session" && c.method === "POST").length, 1);
  assert.deepEqual(f.events.filter((event) => event === "authorized"), ["authorized"]);
});

for (const { status, code, expected } of [
  { status: 401, code: null, expected: "Incorrect diagnostics key" },
  { status: 403, code: "source_unverified", expected: "Home IP could not be verified" },
  { status: 403, code: "origin_unverified", expected: "same-origin verification failed" },
  { status: 503, code: "unconfigured", expected: "not configured" },
]) {
  test("OWNER response " + status + "/" + (code || "default") + " does not authenticate", async () => {
    const f = makeOwnerSession({ postStatus: status, postCode: code });
    f.api.installOwnerSessionControls(() => f.events.push("authorized"));
    await flush();
    await f.element("owner-session-login").fire("click");
    f.element("owner-session-key").value = "synthetic-fixture-not-a-real-key";
    await f.element("owner-session-form").fire("submit", { preventDefault() {} });
    assert.ok(!f.events.includes("authorized"));
    assert.equal(f.element("owner-session-key").value, "");
    assert.match(f.element("owner-session-state").textContent, new RegExp(expected, "i"));
  });
}
