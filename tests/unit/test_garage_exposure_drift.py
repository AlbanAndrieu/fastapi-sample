"""Offline, credential-free Garage exposure reconciliation contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "audit"
    / "garage_exposure_drift.py"
)
spec = importlib.util.spec_from_file_location("garage_exposure_drift", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
WHEN = "2026-10-17T11:00:00Z"


def _record(
    status: str,
    *,
    source: str = "outside_in",
    when: str = WHEN,
    http_status: int = 302,
) -> dict:
    return {
        "status": status,
        "source": source,
        "observed_at": when,
        "http_status": http_status,
        "location": "https://secret.invalid/?token=DO_NOT_COPY",
        "cookie": "DO_NOT_COPY",
    }


def _report(layer: str, entry: dict, *, service: str = "garage-admin") -> dict:
    return module.reconcile(
        {
            "catalog_revision": "fixture-sha",
            "services": [{"id": service, "external": False}],
        },
        {"observations": [{"service_id": service, "layers": {layer: entry}}]},
        now=NOW,
    )


@pytest.mark.parametrize("http_status", [200, 302, 403, 502])
def test_access_edge_is_review_not_anonymous_origin_proof(http_status: int) -> None:
    payload = _report("cloudflare_access", _record("observed", http_status=http_status))
    row = payload["services"][0]
    assert payload["catalog_revision"] == "fixture-sha"
    assert row["exposure_assessment"] == "requires_review"
    assert row["origin_anonymously_accessible"] is None
    assert row["layers"]["public_dns"]["status"] == "unknown"
    assert "DO_NOT_COPY" not in str(payload)


def test_confirmed_drift_requires_fresh_authoritative_source() -> None:
    row = _report("cloudflare_tunnel", _record("drift", source="cloudflare_api"))[
        "services"
    ][0]
    assert row["exposure_assessment"] == "confirmed_drift"
    assert row["layers"]["cloudflare_tunnel"]["source"] == "cloudflare_api"


def test_stale_drift_is_unknown_not_confirmed() -> None:
    old = _record("drift", source="pfsense_config", when="2026-10-10T11:00:00Z")
    row = _report("pfsense_nat_haproxy", old)["services"][0]
    assert row["exposure_assessment"] == "unknown"
    assert row["layers"]["pfsense_nat_haproxy"] == {
        "status": "unknown", "reason": "stale_or_future_evidence"
    }


@pytest.mark.parametrize(
    "invalid",
    [
        {"status": "drift"},
        _record("drift", source="outside_in"),
        _record("drift", source="cloudflare_api", when="not-a-date"),
        _record("drift", source="cloudflare_api", when="2026-10-17T11:00:00"),
        {"status": ["drift"]},
    ],
)
def test_rejects_unverifiable_cloudflare_drift(invalid: dict) -> None:
    with pytest.raises(ValueError):
        _report("cloudflare_tunnel", invalid)


def test_unknown_does_not_require_source() -> None:
    payload = _report("cloudflare_tunnel", {"status": "unknown"})
    assert payload["services"][0]["exposure_assessment"] == "unknown"


def test_future_evidence_is_not_current() -> None:
    row = _report(
        "cloudflare_access", _record("observed", when="2026-10-19T11:00:00Z")
    )["services"][0]
    assert row["exposure_assessment"] == "unknown"


def test_no_confirmed_drift_does_not_mean_secure() -> None:
    payload = module.reconcile(
        [{"id": "garage-webui", "external": True}],
        [],
        now=NOW,
    )
    assert payload["services"][0]["exposure_assessment"] == "unknown"


def test_rejects_bad_clocks_and_age_window() -> None:
    with pytest.raises(ValueError):
        module.reconcile([], [], now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        module.reconcile([], [], now=NOW, max_age=timedelta(days=9))
