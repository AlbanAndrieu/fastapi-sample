"""Offline privacy and disabled-by-default contracts for the PostHog exporter."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from nabla.utils.posthog_business import _validate, export_business_event


def test_export_disabled_by_default():
    with patch.dict("os.environ", {"POSTHOG_BUSINESS_EVENTS_ENABLED": "false", "POSTHOG_PROJECT_KEY": "dummy"}):
        with patch("nabla.utils.posthog_business.httpx.post") as send:
            assert not export_business_event("catalog_loaded", {"app": "fastapi-sample"})
            send.assert_not_called()


def test_enabled_export_targets_fixed_eu_endpoint_and_fails_closed():
    env = {"POSTHOG_BUSINESS_EVENTS_ENABLED": "true", "POSTHOG_PROJECT_KEY": "dummy"}
    with patch.dict("os.environ", env), patch("nabla.utils.posthog_business.httpx.post") as send:
        send.return_value = httpx.Response(200)
        assert export_business_event("catalog_loaded", {"app": "fastapi-sample"})
        assert send.call_args.args == ("https://eu.i.posthog.com/capture/",)
        assert send.call_args.kwargs["json"]["properties"] == {"app": "fastapi-sample"}

        send.side_effect = httpx.ConnectError("offline")
        assert not export_business_event("catalog_loaded", {"app": "fastapi-sample"})


def test_reject_sensitive_data_and_unknown_events():
    assert _validate("unexpected", {}) is None
    assert _validate("catalog_loaded", {"source_ip": "127.0.0.1"}) is None
    assert _validate("catalog_loaded", {"release": "https://internal.example"}) is None
    assert _validate("catalog_load_failed", {"error_class": "secret text"}) is None
    assert _validate("diagnostics_unlock_failed", {"http_status": 200}) is None


def test_allow_strict_business_event():
    assert _validate(
        "catalog_loaded",
        {"app": "fastapi-sample", "environment": "production", "status": "OK"},
    ) == {"app": "fastapi-sample", "environment": "production", "status": "OK"}
