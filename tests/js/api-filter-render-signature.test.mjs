import test from "node:test";
import assert from "node:assert/strict";
import {
  shouldUpdateRenderSignature,
} from "../../nabla/api/assets/api-dom-render-signature.js";

test("unchanged filter counts never rebuild the observed DOM", () => {
  const widget = { dataset: {} };
  let commits = 0;
  function render(counts, selected) {
    const signature = `${counts.ok}:${selected}`;
    if (shouldUpdateRenderSignature(widget, signature)) commits += 1;
  }
  render({ ok: 4 }, false);
  for (let index = 0; index < 100; index += 1) render({ ok: 4 }, false);
  assert.equal(commits, 1);
});

test("changes to filter state and evidence each trigger one render", () => {
  const widget = { dataset: {} };
  assert.equal(shouldUpdateRenderSignature(widget, "4:false"), true);
  assert.equal(shouldUpdateRenderSignature(widget, "4:false"), false);
  assert.equal(shouldUpdateRenderSignature(widget, "4:true"), true);
  assert.equal(shouldUpdateRenderSignature(widget, "5:true"), true);
  assert.equal(shouldUpdateRenderSignature(widget, "5:true"), false);
});

test("active filter list is not cleared on an identical observer cycle", () => {
  const active = { dataset: {} };
  const filters = [["query", "Search", "service-filter", "gatus"]];
  const signature = JSON.stringify(filters);
  assert.equal(shouldUpdateRenderSignature(active, signature), true);
  assert.equal(shouldUpdateRenderSignature(active, signature), false);
  assert.equal(
    shouldUpdateRenderSignature(active, JSON.stringify([...filters, ["status", "Health", "service-status-filter", "down"]])),
    true,
  );
});
