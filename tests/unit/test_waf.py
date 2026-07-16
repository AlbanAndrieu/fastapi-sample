import pytest
from fastapi_featureflags import FeatureFlags


@pytest.mark.skip(reason="Relies on external HTTP/WAF returning 403, brittle; mock if you want stable test.")
def test_ff_waf() -> None:
    """It runs and should be blocked by WAF."""
    FeatureFlags()
    with pytest.raises(Exception) as e_info:
        FeatureFlags.load_conf_from_url("https://pastebin.com/raw/4Ai3j2DC")
        FeatureFlags.reload_feature_flags()
    assert print("Enabled Features:", FeatureFlags.get_features())
    assert "API response status_code: 403" in str(e_info.value)


def test_ff_working() -> None:
    """It runs and should be blocked by WAF."""

    FeatureFlags()
    FeatureFlags.load_conf_from_dict({"web_only": False, "web_1": True, "web_2": False, "web_3": True, "web_4": False})
    FeatureFlags.reload_feature_flags()
    print("Enabled Features:", FeatureFlags.get_features())

    if FeatureFlags.is_enabled("web_only"):
        print("Web 1 is enabled")
    else:
        print("Web 1 is disabled")

    assert FeatureFlags.is_enabled("web_1")
    assert not FeatureFlags.is_enabled("web_2")
    assert FeatureFlags.is_enabled("web_3")
    assert not FeatureFlags.is_enabled("web_4")
