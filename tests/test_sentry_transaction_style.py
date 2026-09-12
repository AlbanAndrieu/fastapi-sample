"""Regression coverage for Sentry FastAPI transaction naming."""

from sentry_sdk.integrations.fastapi import FastApiIntegration

from nabla.utils import sentry_config


def test_fastapi_transactions_use_route_names() -> None:
    integrations = sentry_config._integrations(include_logging=False)
    fastapi = next(integration for integration in integrations if isinstance(integration, FastApiIntegration))

    assert fastapi.transaction_style == "url"
