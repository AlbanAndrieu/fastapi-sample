"""Connection matrix separates data plane, control plane, and telemetry evidence."""

from __future__ import annotations

from nabla.api.connection_matrix import build_connection_matrix


def _rows(value: dict) -> dict[str, dict]:
    return {row["id"]: row for row in value["rows"]}


def test_healthy_scrape_does_not_mask_down_origin_or_access_protection() -> None:
    homelab = {
        "checked_at": "2026-11-04T15:00:00Z",
        "truenas": {
            "api": {"reachable": False},
            "public": {"state": "warn", "http_status": 403},
            "internal": {"state": "ok"},
            "internal_probe_enabled": True,
        },
        "cloudflare": {
            "status_confirmed": True, "stale": False,
            "tunnels": [{"status": "healthy"}],
            "access_observer_state": "ok",
        },
    }
    metrics = {
        "state": "degraded", "configured": True,
        "generated_at": "2026-11-04T15:00:00Z",
        "exporter_jobs": {"fastapi_sample": 1.0, "truenas_node": 0.0},
    }
    external = {
        "state": "observed", "observed_at": "2026-11-04T15:00:00Z",
        "scope": "outside_in_from_truenas",
        "cloud": {"state": "warn", "http_status": 302, "origin_verified": False},
        "cloudflare_public_dns": {
            "sample.albandrieu.com": {"state": "ok"},
            "fastapi-sample.fastapicloud.dev": {"state": "ok"},
        },
    }
    report = build_connection_matrix(homelab, metrics, external)
    rows = _rows(report)
    assert rows["truenas_api"]["state"] == "warn"
    assert rows["truenas_lan"]["state"] == "ok"
    assert rows["truenas_https"]["http_status"] == 403
    assert rows["prometheus_query"]["state"] == "ok"
    assert rows["scrape_fastapi_sample"]["state"] == "ok"
    assert rows["scrape_truenas_node"]["state"] == "fail"
    assert rows["fastapi_cloud"]["state"] == "warn"
    assert rows["dns_sample"]["state"] == "ok"
    assert rows["cloudflare_tunnels"]["state"] == "ok"
    assert rows["cloudflare_tunnel_runtime"]["state"] == "ok"
    assert "not origin" in rows["scrape_fastapi_sample"]["detail"].lower() or "not established" in rows["scrape_fastapi_sample"]["detail"].lower()
    assert sum(report["counts"].values()) == len(report["rows"])
    assert "172.17" not in str(report)


def test_missing_telemetry_and_unexecuted_cloud_probes_are_unknown() -> None:
    report = build_connection_matrix(
        {"truenas": {"api": {}}, "cloudflare": {"stale": True}},
        {"state": "telemetry_unavailable", "configured": True},
        {"state": "not_executed", "scope": "not_trusted_homelab"},
    )
    rows = _rows(report)
    assert rows["prometheus_query"]["state"] == "warn"
    assert rows["scrape_gatus"]["state"] == "unknown"
    assert rows["fastapi_cloud"]["state"] == "unknown"
    assert rows["dns_sample"]["state"] == "unknown"
    assert rows["cloudflare_tunnels"]["state"] == "unknown"
    assert rows["cloudflare_tunnel_runtime"]["state"] == "unknown"
    assert report["external_probe_state"] == "not_executed"


def test_inactive_tunnel_inventory_is_not_misreported_healthy() -> None:
    report = build_connection_matrix(
        {"cloudflare": {
            "status_confirmed": True, "stale": False,
            "tunnels": [{"status": "inactive"}],
            "access_observer_state": "ok",
        }},
        {"state": "not_configured", "configured": False},
        {"state": "not_executed"},
    )
    rows = _rows(report)
    assert rows["cloudflare_tunnels"]["state"] == "ok"
    assert rows["cloudflare_tunnel_runtime"]["state"] == "warn"


def test_gatus_raw_up_fallback_is_telemetry_only() -> None:
    report = build_connection_matrix(
        {}, {"state": "degraded", "configured": True,
             "synthetic_probes": {"gatus_up": 1.0}}, {"state": "not_executed"},
    )
    row = _rows(report)["scrape_gatus"]
    assert row["state"] == "ok"
    assert "application readiness" in row["detail"]


def test_connection_categories_remain_bounded_and_actionable() -> None:
    report = build_connection_matrix(
        {"truenas": {"api": {
            "reachable": False, "phase": "authentication", "stage": "missing_api_key"
        }}},
        {"state": "telemetry_unavailable", "configured": True,
         "error_kind": "authentication_rejected", "http_status": 403},
        {"state": "observed",
         "cloud": {"state": "warn", "category": "access_protected",
                   "http_status": 302},
         "cloudflare_public_dns": {
             "sample.albandrieu.com": {"state": "fail", "category": "nxdomain"},
         }},
    )
    rows = _rows(report)
    assert rows["truenas_api"]["diagnostic_category"] == "truenas_auth"
    assert rows["prometheus_query"]["diagnostic_category"] == "authentication_rejected"
    assert rows["prometheus_query"]["http_status"] == 403
    assert rows["fastapi_cloud"]["diagnostic_category"] == "access_protected"
    assert rows["dns_sample"]["diagnostic_category"] == "nxdomain"
    assert "token" not in str(report).lower()


def test_truenas_sample_runtime_and_probe_evidence_are_independent() -> None:
    report = build_connection_matrix(
        {
            "checked_at": "2026-11-04T17:00:00Z",
            "truenas_runtime_stale": False,
            "services": [
                {"id": "sample", "runtime_state": "RUNNING", "state": "ok"}
            ],
            "public_probe_results": [
                {"id": "sample", "state": "warn", "http_status": 403,
                 "probe_source": "origin", "probe_stale": False}
            ],
            "internal_services": [],
        },
        {"configured": True, "state": "healthy",
         "exporter_jobs": {"fastapi_sample": 1.0}},
        {"state": "not_executed"},
    )
    rows = _rows(report)
    assert rows["fastapi_truenas_runtime"]["state"] == "ok"
    assert rows["fastapi_truenas_public"]["state"] == "warn"
    assert rows["fastapi_truenas_lan"]["state"] == "unknown"
    assert rows["scrape_fastapi_sample"]["state"] == "ok"


def test_stale_sample_runtime_cannot_claim_container_healthy() -> None:
    report = build_connection_matrix(
        {
            "truenas_runtime_stale": True,
            "services": [{"id": "sample", "runtime_state": "RUNNING"}],
            "internal_services": [
                {"id": "sample", "state": "ok", "probe_stale": True,
                 "probe_source": "memory"}
            ],
        },
        {},
        {"state": "not_executed"},
    )
    rows = _rows(report)
    assert rows["fastapi_truenas_runtime"]["state"] == "unknown"
    assert rows["fastapi_truenas_lan"]["state"] == "unknown"
