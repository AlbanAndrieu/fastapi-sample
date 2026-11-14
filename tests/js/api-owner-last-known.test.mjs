import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { normalizeOwnerLastKnown } from "../../nabla/api/assets/api-owner-last-known.js";

const source = readFileSync(
  fileURLToPath(
    new URL("../../nabla/api/assets/api-owner-last-known.js", import.meta.url),
  ),
  "utf8",
);
const controller = readFileSync(
  fileURLToPath(
    new URL("../../nabla/api/assets/api-health-controller.js", import.meta.url),
  ),
  "utf8",
);
const observedAt = "2026-11-14T10:00:00Z";

test("historical owner states are normalized, never promoted to live", () => {
  const input = {
    state: "historical",
    current: false,
    observations: [
      {
        id: "gatus",
        scope: "internal",
        state: "fail",
        ageSeconds: 3600,
        observedAt,
        token: "must-not-propagate",
        url: "http://172.17.0.24",
      },
      {
        id: "<img onerror=alert(1)>",
        scope: "internal",
        state: "ok",
        ageSeconds: 3600,
        observedAt,
      },
      {
        id: "prometheus",
        scope: "public",
        state: "ok",
        ageSeconds: 8 * 86400,
        observedAt,
      },
      {
        id: "pfSense",
        scope: "private",
        state: "ok",
        ageSeconds: 200,
        observedAt,
      },
    ],
  };
  const rows = normalizeOwnerLastKnown(input);
  assert.deepEqual(rows, [
    {
      id: "gatus",
      scope: "internal",
      state: "fail",
      ageSeconds: 3600,
      observedAt,
    },
  ]);
  assert.equal(normalizeOwnerLastKnown({ ...input, current: true }).length, 0);
  assert.equal(normalizeOwnerLastKnown({ ...input, state: "fresh" }).length, 0);
});

test("owner-only historical panel cannot persist or inject HTML", () => {
  assert.ok(source.includes("await ownerSessionAvailable()"));
  assert.ok(source.includes('credentials: "same-origin"'));
  assert.ok(source.includes('cache: "no-store"'));
  assert.ok(source.includes("item.textContent"));
  assert.ok(!source.includes("innerHTML"));
  assert.ok(!source.includes("localStorage.setItem"));
  assert.ok(!source.includes("sessionStorage.setItem"));
  assert.ok(controller.includes("void installOwnerLastKnown()"));
});
