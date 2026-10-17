"""Behavioral Garage card projection and health-page wiring contracts."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla/api/assets"


def test_garage_cards_are_wired_to_health_board_without_hidden_network_fetch() -> None:
    page = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")
    projection = (ASSETS / "api-health-garage.js").read_text(encoding="utf-8")
    assert 'import { includeObservedGarageChecks } from "./api-health-garage.js";' in page
    assert "includeObservedGarageChecks(merged, homelab, snapshot.state)" in page
    assert "render(visible, snapshot.platform_metrics)" in page
    assert "fetch(" not in projection
    assert "garage-admin" in projection and "garage-webui" in projection


def test_exposure_filter_uses_declared_intent_without_certifying_ingress() -> None:
    source = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")
    assert "garageExposureForFilter(snapshot, row, exposure)" in source
    assert 'if (intent !== "internal" && intent !== "public")' in source
    assert 'external: intent === "public"' in source
    assert 'declared.unexpected_tunnel_route === true' in source
    assert 'setExposureMetadata(row, garageExposureForFilter' in source


def test_garage_projection_preserves_private_exposure_and_stale_unknown() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js unavailable: browser JavaScript test optional")

    javascript = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const script = readFileSync(process.argv[1], 'utf8');
const url = 'data:text/javascript;base64,' + Buffer.from(script).toString('base64');
const {includeObservedGarageChecks} = await import(url);
const checks = {pfsense: {name: 'pfSense', reachable: true}};
const homelab = {
  probe_cache: {stale: false},
  services: [
    {id: 'garage', state: 'ok', exposure_intent: 'internal', url: 'https://s3.int.albandrieu.com/'},
    {id: 'garage-admin', state: 'ok', exposure_intent: 'internal', unexpected_tunnel_route: true, url: 'https://garage-admin.albandrieu.com/'},
    {id: 'garage-webui', state: 'warn', exposure_intent: 'public', url: 'https://garage.albandrieu.com/path?secret=NEVER_LEAK'},
  ],
  internal_services: ['garage', 'garage-admin', 'garage-webui'].map(
    (id) => ({id, state: 'ok', probe_source: 'origin', probe_stale: false}),
  ),
};
const base = {checks};
const projected = includeObservedGarageChecks(base, homelab, 'fresh');
assert.deepEqual(Object.keys(projected.checks).sort(),
  ['pfsense', 'garage', 'garage-admin', 'garage-webui'].sort());
assert.equal(projected.checks.garage.local_state, 'ok');
assert.equal(projected.checks['garage-admin'].local_state, 'ok');
assert.equal(projected.checks['garage-admin'].risk_state, 'at_risk');
assert.equal(projected.checks['garage-admin'].url, undefined);
assert.equal(projected.checks.garage.url, undefined);
assert.equal(projected.checks['garage-webui'].url, 'https://garage.albandrieu.com');
assert.equal(projected.checks['garage-webui'].risk_state, 'at_risk');
assert.equal(base.checks.garage, undefined);
const again = includeObservedGarageChecks(projected, homelab, 'fresh');
assert.equal(again.checks.garage, projected.checks.garage);
const stale = includeObservedGarageChecks(base, homelab, 'stale');
assert.equal(stale.checks.garage.local_state, 'unknown');
assert.equal(stale.checks.garage.reachable, null);
const timeout = structuredClone(homelab);
timeout.internal_services[0].timed_out = true;
assert.equal(includeObservedGarageChecks(base, timeout, 'fresh').checks.garage.local_state, 'unknown');
assert.equal(includeObservedGarageChecks(base, {services: []}, 'fresh').checks.garage, undefined);
const aliased = includeObservedGarageChecks({checks: {
  albandrieu_garage_admin: {service_id: 'garage-admin', local_state: 'fail'},
}}, homelab, 'fresh');
assert.equal(aliased.checks['garage-admin'], undefined);
assert.equal(aliased.checks.albandrieu_garage_admin.local_state, 'fail');
"""
    proc = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            javascript,
            str(ASSETS / "api-health-garage.js"),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
