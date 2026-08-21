"""Shared Pydantic settings primitives."""

from pathlib import Path
from typing import Any, ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


def unset_empty_env(value: Any) -> Any:
    """Treat blank environment strings as unset so field defaults apply."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class SettingsBase(BaseSettings):
    """Repository-wide BaseSettings configuration."""

    _base_path: ClassVar[Path] = Path(__file__).resolve().parent.parent
    model_config = SettingsConfigDict(
        env_file=[_base_path / ".env", _base_path / ".env.local"],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )
