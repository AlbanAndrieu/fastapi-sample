import assert from "node:assert/strict";
import { test } from "node:test";

import {
  publicServiceSubtitle,
  validOverview,
} from "../../nabla/api/assets/api-public-services.js";

const REVISION = "sha256:" + "a".repeat(64);
function payload(service) {
  return {
    schemaVersion: 2,
    model: "public-service-overview",
    catalogRevision: REVISION,
    boardState: "fresh",
    catalogSource: "backstage-v2",
    services: [service],
  };
}

test("Backstage V2 service labels and categories remain display-only", () => {
  const item = {
    name: "Gatus UI",
    kind: "Component",
    state: "unknown",
    serviceType: "status-monitor",
    tags: ["observability", "nist-detect"],
  };
  assert.equal(validOverview(payload(item)), true);
  assert.equal(
    publicServiceSubtitle(item),
    "status-monitor · observability · nist-detect",
  );
});

test("invalid or oversized public catalog metadata is rejected", () => {
  const base = {
    name: "Service",
    kind: "Component",
    state: "unknown",
    serviceType: "service",
    tags: [],
  };
  for (const update of [
    { serviceType: "https://172.17.0.24:8091" },
    { tags: ["../../secret"] },
    { tags: Array(4).fill("security") },
  ]) {
    assert.equal(validOverview(payload({ ...base, ...update })), false);
  }
});

test("older minimal V2 payload remains displayable during rollout", () => {
  const item = { name: "PostgreSQL", kind: "Resource", state: "unknown" };
  assert.equal(validOverview(payload(item)), true);
  assert.equal(publicServiceSubtitle(item), "Resource");
});
