import assert from "node:assert/strict";
import test from "node:test";

import { installOwnerLastKnown } from "../../nabla/api/assets/api-owner-last-known.js";
import { resetOwnerSessionStatus } from "../../nabla/api/assets/api-owner-session.js";

test("historical OWNER DOM clears on revocation and late responses cannot restore it", async () => {
  const previous = {
    document: globalThis.document,
    window: globalThis.window,
    fetch: globalThis.fetch,
  };
  const nodes = new Map();
  class FakeNode {
    constructor(tag) {
      this.tagName = tag;
      this.id = "";
      this.textContent = "";
      this.hidden = false;
      this.children = [];
      this.parentElement = null;
    }
    appendChild(child) {
      this.children.push(child);
      child.parentElement = this;
      if (child.id) nodes.set(child.id, child);
      return child;
    }
    replaceChildren() {
      this.children = [];
    }
    remove() {
      nodes.delete(this.id);
      if (this.parentElement) {
        this.parentElement.children = this.parentElement.children.filter(
          (child) => child !== this,
        );
      }
    }
  }
  const parent = new FakeNode("section");
  const anchor = new FakeNode("div");
  anchor.id = "health-board-freshness";
  parent.appendChild(anchor);

  const doc = new EventTarget();
  doc.getElementById = (id) => nodes.get(id) ?? null;
  doc.createElement = (tag) => new FakeNode(tag);
  let authenticated = true;
  let historyFetches = 0;
  let releasePending = null;
  const response = {
    ok: true,
    status: 200,
    json: async () => ({
      state: "historical",
      current: false,
      observations: [
        {
          id: "gatus",
          scope: "internal",
          state: "warn",
          observedAt: "2026-11-14T10:00:00Z",
          ageSeconds: 120,
        },
      ],
    }),
  };
  try {
    globalThis.document = doc;
    globalThis.window = {
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
    };
    globalThis.fetch = async (url) => {
      if (url === "/api/ui/session") {
        return { ok: true, json: async () => ({ authenticated }) };
      }
      assert.equal(url, "/api/health-board/last-known");
      historyFetches += 1;
      if (historyFetches === 2) {
        return new Promise((resolve) => {
          releasePending = resolve;
        });
      }
      return response;
    };
    resetOwnerSessionStatus();
    installOwnerLastKnown();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(historyFetches, 1);
    assert.ok(nodes.has("owner-last-known-evidence"));

    doc.dispatchEvent(
      new CustomEvent("health-board-refreshed", {
        detail: { state: "fresh", refreshing: false, serviceEvidenceCount: 2 },
      }),
    );
    assert.equal(nodes.get("owner-last-known-evidence").hidden, true);
    doc.dispatchEvent(
      new CustomEvent("health-board-refreshed", {
        detail: { state: "stale", serviceEvidenceCount: 0 },
      }),
    );
    assert.equal(nodes.get("owner-last-known-evidence").hidden, false);

    authenticated = false;
    resetOwnerSessionStatus();
    doc.dispatchEvent(
      new CustomEvent("owner-session-changed", {
        detail: { authenticated: false },
      }),
    );
    assert.equal(nodes.has("owner-last-known-evidence"), false);

    authenticated = true;
    resetOwnerSessionStatus();
    doc.dispatchEvent(
      new CustomEvent("owner-session-changed", {
        detail: { authenticated: true },
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(historyFetches, 2);
    assert.equal(nodes.has("owner-last-known-evidence"), false);

    // The old request completes after the OWNER session was revoked.
    authenticated = false;
    resetOwnerSessionStatus();
    doc.dispatchEvent(
      new CustomEvent("owner-session-changed", {
        detail: { authenticated: false },
      }),
    );
    assert.equal(typeof releasePending, "function");
    releasePending(response);
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(nodes.has("owner-last-known-evidence"), false);

    // A new authenticated session may fetch a new historical response.
    authenticated = true;
    resetOwnerSessionStatus();
    doc.dispatchEvent(
      new CustomEvent("owner-session-changed", {
        detail: { authenticated: true },
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(historyFetches, 3);
    assert.ok(nodes.has("owner-last-known-evidence"));
  } finally {
    resetOwnerSessionStatus();
    globalThis.document = previous.document;
    globalThis.window = previous.window;
    globalThis.fetch = previous.fetch;
  }
});
