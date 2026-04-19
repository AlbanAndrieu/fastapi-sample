import pytest
from fastapi_featureflags import FeatureFlags


@pytest.mark.asyncio
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
    FeatureFlags.load_conf_from_dict(
        {
            "rate_limiter": True,
            "mcp": False,
        },
    )
    FeatureFlags.reload_feature_flags()
    print("Enabled Features:", FeatureFlags.get_features())

    assert FeatureFlags.is_enabled("rate_limiter")
    assert not FeatureFlags.is_enabled("mcp")
