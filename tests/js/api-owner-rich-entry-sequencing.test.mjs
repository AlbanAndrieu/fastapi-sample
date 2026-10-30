import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";

// Run the real entry source with two dynamic imports mocked. No network,
// Playwright, Python packages, browser credentials or Github Actions.
const entry = readFileSync(
  fileURLToPath(new URL("../../nabla/api/assets/api-health-entry.js", import.meta.url)),
  "utf8",
);
const script = entry
  .replace(/^import \{ installPublicServiceOverview \} from "\.\/api-public-services\.js";\s*/m, "")
  .replaceAll('import("./api-owner-session.js")', 'importModule("./api-owner-session.js")')
  .replaceAll('import("./api-health.js")', 'importModule("./api-health.js")');

function boot(query, { authenticated = false, readable = false } = {}) {
  const events = [];
  const timers = [];
  const listeners = new Map();
  const url = "https://example.test/api" + query;
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) {
      elements.set(id, {
        id, hidden: true, disabled: false, textContent: "",
        parentElement: { appendChild: () => {} },
      });
    }
    return elements.get(id);
  };
  const context = {
    URL,
    URLSearchParams,
    window: {
      location: { search: query, href: url, reload: () => events.push("reload") },
      setTimeout: (callback) => { timers.push(callback); return timers.length; },
    },
    document: {
      getElementById: (id) => element(id),
      querySelectorAll: () => [],
      createElement: () => ({ href: "", textContent: "", className: "", id: "" }),
      addEventListener: (name, listener) => listeners.set(name, listener),
    },
    installPublicServiceOverview: () => {
      events.push("directory");
      element("public-services-panel").hidden = false;
      return Promise.resolve();
    },
    importModule: (name) => {
      events.push(name);
      if (name === "./api-owner-session.js") {
        return Promise.resolve({
          installOwnerSessionControls: () => events.push("owner-installed"),
          ownerSessionAvailable: () => Promise.resolve(authenticated),
          diagnosticsReadAvailable: () => Promise.resolve(readable),
        });
      }
      if (name === "./api-health.js") {
        return Promise.resolve({});
      }
      throw Error("Unexpected module " + name);
    },
  };
  runInNewContext(script, context, { timeout: 1000 });
  return { events, timers, element,
    emit: (name) => listeners.get(name)?.(),
  };
}

async function flush() {
  for (let i = 0; i < 8; i += 1) await Promise.resolve();
}

test("operator+full without authenticated OWNER remains clickable and public", async () => {
  const page = boot("?operator=1&ui_full=1");
  await flush();
  assert.equal(page.element("owner-session-panel").hidden, false);
  assert.ok(page.events.indexOf("owner-installed") > page.events.indexOf("./api-owner-session.js"));
  assert.ok(page.events.includes("directory"));
  assert.ok(!page.events.includes("./api-health.js"));
  assert.equal(page.timers.length, 0);
  assert.match(page.element("health-summary-text").textContent, /Unlock diagnostics/);
});

test("operator+full with signed session installs OWNER first and defers rich import", async () => {
  const page = boot("?operator=1&ui_full=1", { authenticated: true });
  await flush();
  assert.deepEqual(page.events.filter((x) => x.includes("api-health.js")), []);
  assert.ok(page.events.includes("owner-installed"));
  assert.equal(page.timers.length, 1);
  page.timers.shift()();
  await flush();
  assert.equal(page.events.at(-1), "./api-health.js");
});

test("rich readonly without verified read capability remains a public directory", async () => {
  const page = boot("?ui_full=1");
  await flush();
  assert.ok(page.events.includes("directory"));
  assert.equal(page.events.includes("./api-health.js"), false);
  assert.equal(page.timers.length, 0);
  assert.match(page.element("health-summary-text").textContent, /not authorized/);
});

test("rich readonly with verified read capability defers the advanced import", async () => {
  const page = boot("?ui_full=1", { readable: true });
  await flush();
  assert.ok(page.events.includes("directory"));
  assert.equal(page.timers.length, 1);
  page.timers.shift()();
  await flush();
  assert.equal(page.events.at(-1), "./api-health.js");
});

test("safe mode always avoids OWNER module and rich dashboard", async () => {
  const page = boot("?operator=1&ui_full=1&ui_safe=1");
  await flush();
  assert.deepEqual(
    page.events.filter((event) => event.startsWith("./api-")),
    [],
  );
  assert.equal(page.element("owner-session-panel").hidden, true);
  assert.equal(page.timers.length, 0);
});

test("public fallback stays visible until advanced board confirms refresh", async () => {
  const page = boot("?ui_full=1", { readable: true });
  await flush();
  assert.equal(page.element("public-services-panel").hidden, false);
  assert.equal(page.timers.length, 1);
  page.timers.shift()();
  await flush();
  assert.equal(page.element("public-services-panel").hidden, false);
  page.emit("health-board-refreshed");
  assert.equal(page.element("public-services-panel").hidden, true);
});

test("advanced bootstrap rejection leaves the public catalogue visible", async () => {
  const page = boot("?ui_full=1", { readable: true });
  await flush();
  assert.equal(page.timers.length, 1);
  page.timers.shift()();
  await flush();
  page.emit("health-board-bootstrap-failed");
  assert.equal(page.element("public-services-panel").hidden, false);
  assert.match(
    page.element("health-summary-text").textContent,
    /could not initialize/,
  );
});

test("rich ESM module reports asynchronous bootstrap failures", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../../nabla/api/assets/api-health.js", import.meta.url)),
    "utf8",
  );
  assert.ok(source.includes("void bootstrapHealthUi().catch(() => {"));
  assert.ok(source.includes('new Event("health-board-bootstrap-failed")'));
  assert.ok(!source.includes("console.error(error)"));
});
