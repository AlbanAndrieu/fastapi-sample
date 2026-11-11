import test from "node:test";
import assert from "node:assert/strict";

import {
  NANO_REFERENCE_BYTES,
  nanoProcessMemoryAssessment,
  cgroupMemoryAssessment,
  installCloudProcessBudgetSample,
} from "../../nabla/api/assets/api-cloud-budget.js";

test("Nano reference is never treated as team quota consumption", () => {
  assert.deepEqual(nanoProcessMemoryAssessment(null), { state: "unknown", percentage: null });
  assert.deepEqual(nanoProcessMemoryAssessment(NaN), { state: "unknown", percentage: null });
  assert.equal(nanoProcessMemoryAssessment(NANO_REFERENCE_BYTES * 0.79).state, "unknown");
  assert.equal(nanoProcessMemoryAssessment(NANO_REFERENCE_BYTES * 0.80).state, "warning");
  assert.equal(nanoProcessMemoryAssessment(NANO_REFERENCE_BYTES).state, "danger");
});

test("Cloud process sample is OWNER-initiated and never polled", async () => {
  let onClick = null;
  let fetchCount = 0;
  const status = { textContent: "" };
  const memory = { textContent: "" };
  const container = { dataset: {} };
  const button = {
    dataset: {},
    disabled: false,
    closest: () => container,
    addEventListener: (name, callback) => {
      assert.equal(name, "click");
      onClick = callback;
    },
  };
  const nodes = new Map([
    ["runtime-cloud-process-refresh", button],
    ["runtime-cloud-process-rss", memory],
    ["runtime-cloud-process-status", status],
  ]);
  const oldDocument = globalThis.document;
  const oldFetch = globalThis.fetch;
  try {
    globalThis.document = { getElementById: (key) => nodes.get(key) || null };
    globalThis.fetch = async (url, options) => {
      fetchCount += 1;
      assert.equal(url, "/api/runtime/resources");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.cache, "no-store");
      return {
        ok: true,
        status: 200,
        json: async () => ({ rss_bytes: NANO_REFERENCE_BYTES * 0.85, process_cpu_seconds_total: 4 }),
      };
    };
    installCloudProcessBudgetSample();
    installCloudProcessBudgetSample();
    assert.equal(fetchCount, 0);
    assert.equal(typeof onClick, "function");
    await onClick();
    assert.equal(fetchCount, 1);
    assert.equal(container.dataset.severity, "warning");
    assert.match(status.textContent, /Nano reference/);
    assert.match(memory.textContent, /85.0%/);
    assert.equal(button.disabled, false);
  } finally {
    globalThis.document = oldDocument;
    globalThis.fetch = oldFetch;
  }
});

test("Forbidden OWNER sample does not fabricate usage", async () => {
  let click = null;
  const status = { textContent: "" };
  const memory = { textContent: "" };
  const container = { dataset: {} };
  const button = {
    dataset: {},
    disabled: false,
    closest: () => container,
    addEventListener: (_, callback) => { click = callback; },
  };
  const nodes = {
    "runtime-cloud-process-refresh": button,
    "runtime-cloud-process-rss": memory,
    "runtime-cloud-process-status": status,
  };
  const oldDocument = globalThis.document;
  const oldFetch = globalThis.fetch;
  try {
    globalThis.document = { getElementById: (key) => nodes[key] || null };
    globalThis.fetch = async () => ({ status: 403, ok: false });
    installCloudProcessBudgetSample();
    await click();
    assert.equal(memory.textContent, "Restricted");
    assert.match(status.textContent, /OWNER session required/);
    assert.equal(container.dataset.severity, "unknown");
  } finally {
    globalThis.document = oldDocument;
    globalThis.fetch = oldFetch;
  }
});

test("cgroup memory thresholds prioritize actual measured limit over Nano reference", () => {
  assert.deepEqual(cgroupMemoryAssessment(null), { state: "unknown", percentage: null });
  assert.equal(cgroupMemoryAssessment({ memory_current_bytes: 0, memory_limit_bytes: null }).percentage, null);
  assert.equal(cgroupMemoryAssessment({ memory_current_bytes: 200, memory_limit_bytes: 1000 }).percentage, 20);
  assert.equal(cgroupMemoryAssessment({ memory_current_bytes: 800, memory_limit_bytes: 1000 }).state, "warning");
  assert.equal(cgroupMemoryAssessment({ memory_current_bytes: 1000, memory_limit_bytes: 1000 }).state, "danger");
});

test("owner cgroup snapshot shows real replica percent with RSS separately", async () => {
  let click;
  const status = { textContent: "" };
  const memory = { textContent: "" };
  const container = { dataset: {} };
  const button = {
    dataset: {}, disabled: false, closest: () => container,
    addEventListener: (_, handler) => { click = handler; },
  };
  const oldDocument = globalThis.document, oldFetch = globalThis.fetch;
  try {
    globalThis.document = { getElementById: (name) => ({
      "runtime-cloud-process-refresh": button,
      "runtime-cloud-process-rss": memory,
      "runtime-cloud-process-status": status,
    }[name] || null) };
    globalThis.fetch = async () => ({
      ok: true, status: 200,
      json: async () => ({
        rss_bytes: 90 * 1024 * 1024,
        process_cpu_seconds_total: 1.25,
        cgroup: {
          memory_current_bytes: 450 * 1024 * 1024,
          memory_limit_bytes: 500 * 1024 * 1024,
          oom_kill_count: 2,
        },
      }),
    });
    installCloudProcessBudgetSample();
    await click();
    assert.equal(container.dataset.severity, "warning");
    assert.match(memory.textContent, /90.0% of measured cgroup limit/);
    assert.match(memory.textContent, /90.0 MiB process RSS/);
    assert.match(status.textContent, /OOM kills \(cumulative\): 2/);
  } finally {
    globalThis.document = oldDocument;
    globalThis.fetch = oldFetch;
  }
});
