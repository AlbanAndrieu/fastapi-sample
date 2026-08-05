"""Application and release version resolution."""

import os
import re
from importlib.metadata import PackageNotFoundError, version as package_version

from nabla._release import __version__ as generated_release_version

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _valid_release_version(value: str | None) -> str | None:
    """Return a normalized SemVer release, or ``None`` for unusable values."""
    if not value:
        return None
    normalized = value.removeprefix("v")
    return normalized if _SEMVER_PATTERN.fullmatch(normalized) else None


def resolve_release_version() -> str:
    """Resolve the release without requiring a ``.git`` directory at runtime."""
    configured = _valid_release_version(os.getenv("RELEASE_VERSION"))
    if configured:
        return configured

    try:
        installed = _valid_release_version(package_version("fastapi-sample"))
    except PackageNotFoundError:
        installed = None

    return installed or generated_release_version


API_VERSION = os.getenv("API_VERSION", os.getenv("APP_PREFIX_VERSION", "v0"))
RELEASE_VERSION = resolve_release_version()
RUNTIME_VERSION = f"{API_VERSION}+{RELEASE_VERSION}"

__all__ = ("API_VERSION", "RELEASE_VERSION", "RUNTIME_VERSION", "resolve_release_version")
