"""Reusable Pydantic models used by application settings."""

import os
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CHAT_MODEL = "gpt-4.1"


def openai_api_key_from_env() -> str:
    """Default OpenAI API key from the same environment variable as the SDK."""
    return os.environ["OPENAI_API_KEY"]


class AzureOpenAiInstance(BaseModel):
    """Configuration for one Azure OpenAI instance."""

    url: Annotated[
        str,
        Field(pattern=r"^https://[a-z0-9\-]+\.openai\.azure\.com$"),
    ]
    api_key: Annotated[
        str,
        Field(default_factory=openai_api_key_from_env, min_length=1),
    ]
    api_alias: Annotated[str, Field(min_length=1)]
    available_models: Annotated[str, Field(default="gpt-5", min_length=1)]


class McpServerConfig(BaseModel):
    """One external MCP server reached over stdio or Streamable HTTP."""

    model_config = ConfigDict(extra="ignore")

    name: Annotated[str, Field(min_length=1, description="Logical server name.")]
    transport: Literal["stdio", "streamable-http"] = "stdio"
    command: str | None = Field(default=None, description="stdio executable.")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    url: str | None = Field(default=None, description="Streamable HTTP MCP endpoint.")
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    startup_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    tool_call_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
