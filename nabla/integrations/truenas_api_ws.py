"""Synchronous access to the TrueNAS 26 WebSocket API."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from truenas_api_client import Client

TRUENAS_URL = os.environ.get("TRUENAS_URL", "https://172.17.0.24:7000")
TRUENAS_USER = os.environ.get("TRUENAS_USER", "root")
TRUENAS_API_KEY = os.environ.get("TRUENAS_API_KEY")
TRUENAS_WS_PATH = os.environ.get("TRUENAS_WS_PATH", "/api/current")


def compute_ws_url(
    base_url: str | None = None,
    ws_path: str | None = None,
) -> str:
    """Convert the configured HTTP(S) URL to a TrueNAS WebSocket URL."""
    configured_url = (base_url or TRUENAS_URL).strip()
    parsed = urlsplit(configured_url)
    schemes = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}
    if parsed.scheme not in schemes or not parsed.netloc:
        raise RuntimeError(
            "TRUENAS_URL doit être une URL http(s):// ou ws(s):// valide",
        )

    # An explicitly configured TRUENAS_WS_PATH takes precedence. Otherwise,
    # preserve an API path already present in TRUENAS_URL.
    path = ws_path if ws_path is not None else TRUENAS_WS_PATH
    if parsed.path not in {"", "/"} and ws_path is None and "TRUENAS_WS_PATH" not in os.environ:
        path = parsed.path
    path = "/" + path.lstrip("/")
    return urlunsplit((schemes[parsed.scheme], parsed.netloc, path, "", ""))


TRUENAS_WS_URL = compute_ws_url()


def fetch_truenas_apps_sync() -> list[dict[str, Any]]:
    """Authenticate with TrueNAS 26 and return every installed application."""
    if not TRUENAS_API_KEY or not TRUENAS_USER:
        raise RuntimeError("TRUENAS_API_KEY et TRUENAS_USER doivent être définis")

    # The existing TrueNAS endpoint uses a private/self-signed certificate.
    # Set TRUENAS_VERIFY_SSL=true when the NAS certificate is trusted locally.
    verify_ssl = os.environ.get("TRUENAS_VERIFY_SSL", "false").lower() not in {
        "0",
        "false",
        "no",
    }
    with Client(uri=TRUENAS_WS_URL, verify_ssl=verify_ssl) as client:
        # TrueNAS 26 defaults to SCRAM-SHA-512 and channel binding. This is the
        # supported public helper from truenas/api_client.
        client.login_with_api_key(TRUENAS_USER, TRUENAS_API_KEY)
        apps = client.call("app.query")

    if not isinstance(apps, list):
        raise RuntimeError("TrueNAS app.query a retourné une réponse inattendue")
    return apps
