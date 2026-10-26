import test from "node:test";
import assert from "node:assert/strict";
import { withRequestDeadline } from "../../nabla/api/assets/api-request-deadline.js";

globalThis.window = { setTimeout, clearTimeout };

test("bounded request returns normal results", async () => {
  const result = await withRequestDeadline(async (signal) => {
    assert.equal(signal.aborted, false);
    return { status: 200, rows: 12 };
  }, 60);
  assert.deepEqual(result, { status: 200, rows: 12 });
});

test("hung request stops loading and aborts transport", async () => {
  let signal;
  const start = performance.now();
  await assert.rejects(
    withRequestDeadline((provided) => {
      signal = provided;
      return new Promise(() => {});
    }, 25),
    /Request deadline exceeded/,
  );
  assert.equal(signal.aborted, true);
  assert.ok(performance.now() - start < 400);
});

test("timeout includes slow JSON decoding, not only fetch headers", async () => {
  let signal;
  await assert.rejects(
    withRequestDeadline(async (provided) => {
      signal = provided;
      const response = { status: 200, json: () => new Promise(() => {}) };
      return response.json();
    }, 25),
    /Request deadline exceeded/,
  );
  assert.equal(signal.aborted, true);
});

test("failed requests do not wait for the deadline", async () => {
  const start = performance.now();
  await assert.rejects(
    withRequestDeadline(async () => { throw new Error("HTTP 503"); }, 300),
    /HTTP 503/,
  );
  assert.ok(performance.now() - start < 200);
});
