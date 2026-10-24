"""Temporary read-only diagnostics switch shared by access control and UI.

WARNING: When enabled, selected operational GET responses are public.
Remove this compatibility mode after trusted owner access is restored.
"""

from __future__ import annotations

import os


def public_diagnostics_readonly_enabled() -> bool:
    """Return whether the temporary public diagnostic read rollback is active."""
    return os.getenv("HOMELAB_PUBLIC_DIAGNOSTICS_READONLY", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
