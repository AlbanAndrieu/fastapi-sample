"""Compatibility imports for the consolidated TrueNAS integration client.

New code should import from :mod:`nabla.integrations.truenas_client`.
"""

from nabla.integrations.truenas_client import (
    TrueNASClientProtocol,
    TrueNASReadOnlyAdapter,
    TrueNASSettings,
    build_truenas_adapter,
    observe_truenas_api,
)

__all__ = [
    "TrueNASClientProtocol",
    "TrueNASReadOnlyAdapter",
    "TrueNASSettings",
    "build_truenas_adapter",
    "observe_truenas_api",
]
