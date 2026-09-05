"""Composable application settings domains."""

from nabla.settings.database import DatabaseSettings
from nabla.settings.homelab import TrueNASProviderSettings
from nabla.settings.models import AzureOpenAiInstance, McpServerConfig

__all__ = [
    "AzureOpenAiInstance",
    "DatabaseSettings",
    "McpServerConfig",
    "TrueNASProviderSettings",
]
