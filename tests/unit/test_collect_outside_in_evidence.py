"""Offline contracts for the read-only outside-in exposure evidence collector."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import socket

import httpx

AUDIT = Path(__file__).resolve().parents[2] / "scripts" / "audit"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, AUDIT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = _load("collect_outside_in_evidence")
drift = _load("garage_exposure_drift")

EDGE = ["188.114.96.2", "188.114.97.2"]


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def _service(service_id: str, url: str | None, *, external: bool) -> dict:
    return {"id": service_id, "tunnelUrl": url, "external": external}


def _access_redirect(request: httpx.Request) -> httpx.Response:
    return httpx.Response(302, headers={"location": "https://albandrieu.cloudflareaccess.com/cdn-cgi/access/login?token=DO_NOT_COPY"})


def test_access_redirect_is_edge_evidence_not_origin() -> None:
    report = collector.collect(
        [_service("garage-admin", "https://garage-admin.albandrieu.com", external=False)],
        resolver=lambda host: EDGE,
        client=_client(_access_redirect),
    )

    layers = report["observations"][0]["layers"]
    assert layers["public_dns"]["status"] == "observed"
    assert layers["cloudflare_access"]["status"] == "observed"
    assert layers["cloudflare_access"]["http_status"] == 302
    assert "outside_in_origin" not in layers
    assert "location" not in layers["cloudflare_access"]


def test_private_service_answering_publicly_is_origin_evidence() -> None:
    report = collector.collect(
        [_service("garage", "https://s3.int.albandrieu.com", external=False)],
        resolver=lambda host: EDGE,
        client=_client(lambda request: httpx.Response(403, text="<Error><Code>AccessDenied</Code></Error>")),
    )

    layers = report["observations"][0]["layers"]
    assert layers["outside_in_origin"] == {
        "status": "observed",
        "source": "outside_in",
        "observed_at": layers["outside_in_origin"]["observed_at"],
        "http_status": 403,
    }


def test_lan_only_resolution_is_unknown_and_skips_http() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("LAN-resolved hostnames must not be probed as outside-in")

    report = collector.collect(
        [_service("garage", "https://s3.int.albandrieu.com", external=False)],
        resolver=lambda host: ["172.17.0.24"],
        client=_client(fail),
    )

    assert report["observations"][0]["layers"] == {"public_dns": {"status": "unknown"}}


def test_hairpin_wan_address_is_not_outside_in_evidence() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("NAT-reflected requests must not be recorded as outside-in")

    report = collector.collect(
        [_service("garage", "https://s3.int.albandrieu.com", external=False)],
        resolver=lambda host: ["82.66.4.247"],
        client=_client(fail),
        hairpin_addresses=frozenset({"82.66.4.247"}),
    )

    layers = report["observations"][0]["layers"]
    assert set(layers) == {"public_dns"}
    assert layers["public_dns"]["status"] == "observed"


def test_missing_private_record_matches_and_missing_public_record_drifts() -> None:
    def nxdomain(host: str) -> list[str]:
        raise socket.gaierror("nxdomain")

    report = collector.collect(
        [
            _service("garage", "https://s3.int.albandrieu.com", external=False),
            _service("garage-webui", "https://garage.albandrieu.com", external=True),
            _service("no-host", None, external=False),
        ],
        resolver=nxdomain,
        client=_client(_access_redirect),
    )

    statuses = {row["service_id"]: row["layers"]["public_dns"]["status"] for row in report["observations"]}
    assert statuses == {"garage": "matched", "garage-webui": "drift"}


def test_collected_evidence_is_accepted_by_the_offline_reconciler() -> None:
    services = [_service("garage-admin", "https://garage-admin.albandrieu.com", external=False)]
    observed = collector.collect(services, resolver=lambda host: EDGE, client=_client(_access_redirect))

    report = drift.reconcile(
        {"services": [{"id": "garage-admin", "external": False}]},
        observed,
        now=datetime.now(timezone.utc),
    )

    row = report["services"][0]
    assert row["exposure_assessment"] == "requires_review"
    assert row["origin_anonymously_accessible"] is None
    assert row["layers"]["cloudflare_tunnel"] == {"status": "unknown"}
