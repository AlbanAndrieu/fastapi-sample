"""Behavioral Garage card projection and health-page wiring contracts."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla/api/assets"
SCRIPT = ROOT / "tests/js/garage-health-ui.mjs"


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
    assert re.search(
        r"setExposureMetadata\(\s*row,\s*garageExposureForFilter\(",
        source,
    )


def test_garage_projection_preserves_private_exposure_and_stale_unknown() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js unavailable: browser JavaScript test optional")

    completed = subprocess.run(
        ["node", str(SCRIPT), str(ASSETS / "api-health-garage.js")],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
