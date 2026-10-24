"""Offline unit tests for production-facing Prometheus projection verification."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "scripts/verify-prometheus-cloud-projection.py"
spec = importlib.util.spec_from_file_location("verify_prometheus_cloud_projection", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_scrape_projection_matches_only_two_known_jobs() -> None:
    lan = {"status": "success", "data": {
        "resultType": "vector",
        "result": [
            {"metric": {"job": "akvorado_inlet"}, "value": [1, "1"]},
            {"metric": {"job": "akvorado_outlet"}, "value": [1, "1"]},
            {"metric": {"job": "other"}, "value": [1, "1"]},
        ],
    }}
    current = mod.observed_up(lan)
    assert current == {"akvorado_inlet": 1.0, "akvorado_outlet": 1.0}
    statuses, passed = mod.compare(current, {
        "platform_metrics": {"exporter_jobs": current}
    })
    assert passed
    assert set(statuses.values()) == {"scrape_projected_up"}


def test_missing_or_downgraded_telemetry_cannot_claim_success() -> None:
    lan = {"akvorado_inlet": 1.0, "akvorado_outlet": 1.0}
    for board in (
        {},
        {"platform_metrics": {"exporter_jobs": {"akvorado_inlet": 1.0}}},
        {"platform_metrics": {
            "exporter_jobs": {"akvorado_inlet": 1.0, "akvorado_outlet": 0.0}
        }},
    ):
        _, ok = mod.compare(lan, board)
        assert not ok


def test_prometheus_target_conflicts_fail_closed() -> None:
    payload = {"status": "success", "data": {
        "resultType": "vector",
        "result": [
            {"metric": {"job": "akvorado_inlet"}, "value": [1, "1"]},
            {"metric": {"job": "akvorado_inlet"}, "value": [1, "0"]},
            {"metric": {"job": "akvorado_outlet"}, "value": [1, "NaN"]},
        ],
    }}
    assert mod.observed_up(payload) == {"akvorado_inlet": 0.0}


def test_verifier_uses_fixed_urls_no_redirects_and_never_prints_secret() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "https://fastapi-sample.fastapicloud.dev" in source
    assert "http://172.17.0.24:9090" in source
    assert "NoRedirect" in source
    assert "ProxyHandler({})" in source
    assert "MAX_RESPONSE = 4 * 1024 * 1024" in source
    assert "DIAGNOSTICS_ACCESS_KEY" in source
    assert "print(key)" not in source


def test_cloud_access_denial_message_is_actionable_without_secret() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "authorization_denied; Akvorado projection=unverified" in source
    assert "Review diagnostics key, trusted CIDRs, Cloudflare Access" in source
    assert "Do not bypass access controls." in source
    assert '("configured" if key else "not_provided")' in source
    assert "print(key)" not in source
