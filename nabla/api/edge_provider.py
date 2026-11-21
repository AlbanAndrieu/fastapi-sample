"""Explicit edge-provider transition; legacy pfSense code remains available."""
from __future__ import annotations

import os


def active_edge_provider() -> str:
    """Switch only observed checks; never infer a router from a DNS alias."""
    configured = os.environ.get("NETWORK_EDGE_PROVIDER", "pfsense").strip().lower()
    return configured if configured in {"pfsense", "freebox"} else "pfsense"


def pfsense_retired() -> bool:
    return active_edge_provider() == "freebox"
