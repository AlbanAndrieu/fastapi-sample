from nabla.api.homelab_declared import DeclaredService
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_monitoring import public_monitoring_url


def test_public_monitoring_url_reuses_canonical_path_and_query() -> None:
    service = HomelabService(
        name="Language Tool",
        tunnelUrl="https://languagetool.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )
    declared = DeclaredService(
        id="languagetool",
        name="LanguageTool",
        kind="language-service",
        category="productivity",
        sourcePath="apps/languagetool/compose.yml",
        composeService="languagetool",
        monitoring={
            "type": "http",
            "target": "http://172.17.0.24:8010/v2/check?language=en-US&text=healthcheck",
        },
    )
    assert public_monitoring_url(service, declared) == (
        "https://languagetool.albandrieu.com/v2/check?language=en-US&text=healthcheck"
    )


def test_public_monitoring_url_falls_back_to_public_root_without_contract() -> None:
    service = HomelabService(
        name="Example",
        tunnelUrl="https://example.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )
    assert public_monitoring_url(service, None) == "https://example.albandrieu.com/"
