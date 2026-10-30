import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const config = readFileSync(
  fileURLToPath(new URL("../../.pre-commit-config.yaml", import.meta.url)),
  "utf8",
);

test("pre-commit reuses installed Node and does not resolve prerelease via nodeenv", () => {
  assert.match(
    config,
    /^default_language_version:\s*\n\s+node:\s*system\s*$/m,
  );
  assert.doesNotMatch(config, /^\s+node:\s*(latest|default)\s*$/m);
});

test("pre-commit Node hooks stay enabled and pinned", () => {
  for (const hook of ["biome-check", "htmllint", "htmlhint", "markdown-toc", "prettier"]) {
    assert.ok(config.includes("      - id: " + hook), hook + " missing from pre-commit");
  }
  assert.doesNotMatch(config, /^\s*SKIP\s*:/m);
});
