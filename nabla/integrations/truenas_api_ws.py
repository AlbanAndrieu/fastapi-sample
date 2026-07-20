import os
from truenas_api_client import APIKeyAuthMech, Client, auth_api_key

TRUENAS_URL = os.environ.get("TRUENAS_URL", "https://172.17.0.24:7000")
TRUENAS_USER = os.environ.get("TRUENAS_USER", "root")
TRUENAS_API_KEY = os.environ.get("TRUENAS_API_KEY")
TRUENAS_WS_PATH = os.environ.get("TRUENAS_WS_PATH", "/api/current")


def compute_ws_url() -> str:
    base = TRUENAS_URL.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[8:] + TRUENAS_WS_PATH
    if base.startswith("http://"):
        return "ws://" + base[7:] + TRUENAS_WS_PATH
    raise RuntimeError("TRUENAS_URL doit commencer par http:// ou https://")


TRUENAS_WS_URL = compute_ws_url()


def fetch_truenas_apps_sync():
    if not TRUENAS_API_KEY or not TRUENAS_USER:
        raise RuntimeError("TRUENAS_API_KEY et TRUENAS_USER doivent être définis")

    with Client(uri=TRUENAS_WS_URL, verify_ssl=False) as c:
        auth_api_key.api_key_authenticate(
            c,
            APIKeyAuthMech.PLAIN,
            TRUENAS_USER,
            TRUENAS_API_KEY,
            use_legacy_endpoint=False,
            channel_binding=False,
        )
        return c.call("app.query", [])
