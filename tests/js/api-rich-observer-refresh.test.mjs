import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const source = (path) =>
  readFileSync(
    fileURLToPath(new URL("../../nabla/api/assets/" + path, import.meta.url)),
    "utf8",
  );

function excerpt(text, startMarker, endMarker) {
  const start = text.indexOf(startMarker);
  const end = text.indexOf(endMarker, start);
  assert.ok(
    start >= 0 && end > start,
    "Missing source boundaries: " + startMarker,
  );
  return text.slice(start, end).replace(/^export /, "");
}

function scheduleHarness() {
  const script = excerpt(
    source("api-service-diagnostics.js"),
    "function scheduleRefresh(records)",
    "\nexport function installServiceDiagnostics",
  );
  const frames = [];
  let decorated = 0;
  const context = {
    refreshScheduled: false,
    decorateRows: () => {
      decorated += 1;
    },
    window: { requestAnimationFrame: (callback) => frames.push(callback) },
  };
  runInNewContext(
    script + "\nthis.scheduleRefresh = scheduleRefresh;",
    context,
  );
  return { context, frames, decoratedCount: () => decorated };
}

test("probe badge changes do not re-run all service diagnostics", () => {
  const { context, frames, decoratedCount } = scheduleHarness();
  context.scheduleRefresh([
    {
      addedNodes: [
        {
          nodeType: 1,
          matches: () => false,
          querySelector: () => null,
        },
      ],
      removedNodes: [],
    },
  ]);
  assert.equal(frames.length, 0);
  assert.equal(decoratedCount(), 0);
});

test("new service rows reconcile with one scheduled animation frame", () => {
  const { context, frames, decoratedCount } = scheduleHarness();
  const rows = [
    {
      addedNodes: [
        { nodeType: 1, matches: (s) => s === "[data-service-filter-target]" },
      ],
      removedNodes: [],
    },
  ];
  context.scheduleRefresh(rows);
  context.scheduleRefresh(rows);
  assert.equal(frames.length, 1);
  frames.shift()();
  assert.equal(decoratedCount(), 1);
  context.scheduleRefresh();
  assert.equal(frames.length, 1);
});

test("stable row visibility does not rewrite the hidden attribute", () => {
  const script = excerpt(
    source("api-service-filter.js"),
    "export function refreshServiceFilter()",
    "\nfunction clearFilters()",
  );
  let currentHidden = false;
  let writes = 0;
  let match = true;
  const row = {};
  Object.defineProperty(row, "hidden", {
    get: () => currentHidden,
    set: (value) => {
      currentHidden = value;
      writes += 1;
    },
  });
  const context = {
    document: { querySelectorAll: () => [row] },
    queryMatches: () => match,
    statusMatches: () => true,
    environmentMatches: () => true,
    groupMatches: () => true,
    exposureMatches: () => true,
    probeMatches: () => true,
    updateGroupVisibility: () => {},
    updateFilterResult: () => {},
    updateCollapseButton: () => {},
    syncIssuesButton: () => {},
    syncProtocolShortcuts: () => {},
    notifyFilterChanged: () => {},
  };
  runInNewContext(
    script + "\nthis.refreshServiceFilter = refreshServiceFilter;",
    context,
  );
  context.refreshServiceFilter();
  context.refreshServiceFilter();
  assert.equal(writes, 0);
  match = false;
  context.refreshServiceFilter();
  context.refreshServiceFilter();
  assert.equal(writes, 1);
  assert.equal(currentHidden, true);
});

test("stable detail rows do not rewrite their class and re-fire the observer", () => {
  const script = excerpt(
    source("api-service-detail-drawer.js"),
    "function ensureDetailTrigger(row)",
    "\nfunction decorateRows(",
  );
  class FakeElement {}
  const classes = new Set();
  let classWrites = 0;
  const trigger = {};
  const row = Object.assign(new FakeElement(), {
    // Like DOMTokenList.add, every call writes the attribute (a mutation record).
    classList: {
      contains: (name) => classes.has(name),
      add: (name) => {
        classes.add(name);
        classWrites += 1;
      },
    },
    querySelector: () => trigger,
  });
  let updates = 0;
  const context = {
    HTMLElement: FakeElement,
    updateDetailTrigger: () => {
      updates += 1;
    },
  };
  runInNewContext(
    script + "\nthis.ensureDetailTrigger = ensureDetailTrigger;",
    context,
  );
  context.ensureDetailTrigger(row);
  context.ensureDetailTrigger(row);
  context.ensureDetailTrigger(row);
  assert.equal(classWrites, 1);
  assert.equal(updates, 3);
});
