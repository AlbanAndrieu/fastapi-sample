"""Small, dependency-free environment parsing helpers."""

import os
from collections.abc import Mapping

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_bool(
    name: str,
    default: bool = False,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Read a permissive boolean without treating non-empty false values as true."""
    values = os.environ if environ is None else environ
    raw = values.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().casefold() in _TRUE_VALUES
