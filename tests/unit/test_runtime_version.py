import httpx
import pytest

from nabla.api import runtime_version


def test_version_comparison_normalizes_runtime_prefix() -> None:
    assert runtime_version.normalized_version("v0+1.13.15") == "1.13.15"
    assert runtime_version.version_is_behind("1.13.12", "v0+1.13.15") is True
    assert runtime_version.version_is_behind("1.13.15", "v0+1.13.15") is False


@pytest.mark.asyncio
async def test_cloud_version_failure_is_non_blocking(monkeypatch) -> None:
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(
        runtime_version.httpx,
        "AsyncClient",
        lambda **_kwargs: Client(),
    )
    result = await runtime_version.fetch_cloud_version_status("1.13.12")
    assert result["behind"] is None
    assert result["status_confirmed"] is False
    assert result["warning"]
