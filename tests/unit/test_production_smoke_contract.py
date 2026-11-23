"""Regression tests for post-deployment diagnostic smoke semantics."""

import re
from pathlib import Path

import yaml

from nabla.access_control import _SMOKE_READ_ROUTES

ROOT = Path(__file__).resolve().parents[2]


def test_production_smoke_asserts_retired_edge_without_router_secrets() -> None:
    smoke = (ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8")

    assert "Check production runtime topology" in smoke
    assert '"${PRODUCTION_API_URL}/runtime/topology"' in smoke
    assert ".platform_replica_count_available == false" in smoke
    assert "Check retired pfSense and Freebox observer contract" in smoke
    assert ".checks.pfsense.skipped == true" in smoke
    assert '.checks.pfsense.credential_mode == "disabled"' in smoke
    assert ".checks.freebox.skipped == true" in smoke
    assert '.checks.freebox.vantage_point == "fastapi_cloud"' in smoke
    assert ".checks.freebox.status_confirmed == false" in smoke
    assert "PFSENSE_POSTURE_API_KEY" not in smoke
    assert "FREEBOX_APP_TOKEN" not in smoke


def test_smoke_key_stays_in_the_post_deploy_job_and_never_prints_payloads() -> None:
    """Public repo logs: the dedicated key reads, asserts and prints nothing private."""
    text = (ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8")
    jobs = yaml.safe_load(text)["jobs"]
    public, private = jobs["production-smoke"], jobs["authenticated-smoke"]

    assert "environment" not in public
    assert "secrets." not in yaml.safe_dump(public)
    assert private["environment"] == "production-smoke"
    assert private["if"] == "${{ github.event_name != 'pull_request' }}"
    assert text.count("secrets.PRODUCTION_SMOKE_ACCESS_KEY") == 2
    assert "X-Diagnostics-Key" not in text and "Authorization" not in text
    assert "| jq ." not in text and "::group::" not in text

    # The anonymous 401 probe and the code allowlist cover exactly the same routes.
    probe = next(step["run"] for step in public["steps"] if step["name"] == "Verify private diagnostics refuse anonymous reads")
    probed = {("/api" if base == "API" else "") + path for base, path in re.findall(r'"\$\{PRODUCTION_(ROOT|API)_URL\}(/[^"]+)"', probe)}
    assert probed == set(_SMOKE_READ_ROUTES)


def test_playwright_smoke_runs_on_a_runner_playwright_supports() -> None:
    """ubuntu-latest moved to 26.04, which Playwright 1.55 cannot provision (master-red, 22/11)."""
    jobs = yaml.safe_load((ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8"))["jobs"]
    for name, job in jobs.items():
        if "playwright install" in yaml.safe_dump(job):
            assert job["runs-on"] == "ubuntu-24.04", name
