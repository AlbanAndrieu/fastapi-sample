"""Regression tests for application-level wiring."""

from nabla import config_settings
from nabla import main as main_module


def test_mcp_resource_does_not_shadow_settings_factory() -> None:
    assert main_module.get_settings is config_settings.get_settings
    assert main_module.get_server_configuration().startswith("Server Configuration: Version ")
