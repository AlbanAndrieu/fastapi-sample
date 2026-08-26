"""Compatibility imports for the consolidated TrueNAS integration client.

New code should import from :mod:`nabla.integrations.truenas_client`.
"""

from nabla.integrations.truenas_client import (
    DEFAULT_TRUENAS_URL,
    TrueNASClientProtocol,
    TrueNASReadOnlyAdapter,
    TrueNASSettings,
    build_truenas_adapter,
    observe_truenas_api,
    truenas_host_port,
    truenas_url,
)

__all__ = [
    "DEFAULT_TRUENAS_URL",
    "TrueNASClientProtocol",
    "TrueNASReadOnlyAdapter",
    "TrueNASSettings",
    "build_truenas_adapter",
    "observe_truenas_api",
    "truenas_host_port",
    "truenas_url",
]
