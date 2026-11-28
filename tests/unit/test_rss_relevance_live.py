"""Real adapter orchestration with MockTransport; no LAN or external calls."""

import json
from unittest.mock import AsyncMock
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from redis.exceptions import RedisError

from nabla.api.site_architecture_catalog import SiteArchitectureCatalogV2, SiteV2Entity, SiteV2Metadata
from nabla.integrations import rss_relevance_live as live


def catalog() -> SiteArchitectureCatalogV2:
    return SiteArchitectureCatalogV2(
        catalogRevision="sha256:" + "a" * 64,
        entities=[
            SiteV2Entity(
                kind="Component",
                entityRef="component:default/traefik",
                sourcePath="apps/traefik/catalog-info.yaml",
                metadata=SiteV2Metadata(name="traefik", tags=["security", "production"]),
                spec={"type": "service"},
            ),
        ],
    )


@pytest.mark.asyncio
async def test_greader_backstage_langfuse_litellm_end_to_end(monkeypatch):
    calls = []

    def transport(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, str(req.url)))
        if req.url.path.endswith("/subscription/list"):
            return httpx.Response(200, json={"subscriptions": [{"id": "feed/public", "url": "https://security.example.com/rss"}]})
        if req.url.path.endswith("/stream/contents/reading-list"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "article-1", "title": "<b>Traefik</b> CVE", "origin": {"streamId": "feed/public"}, "summary": {"content": "<p>Fix released</p>"}},
                    ],
                },
            )
        assert req.method == "POST"
        assert str(req.url) == "http://172.17.0.24:4000/v1/chat/completions"
        data = json.loads(req.content)
        assert data["model"] == "fastapi-qwen"
        assert "tools" not in data
        assert "fix released" in data["messages"][1]["content"].lower()
        assert "172.17" not in data["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "relevant": True,
                                    "matched": ["traefik"],
                                    "reason": "Security update",
                                },
                            ),
                        },
                    },
                ],
            },
        )

    genuine_client = httpx.AsyncClient
    monkeypatch.setattr(
        live.httpx,
        "AsyncClient",
        lambda **kw: genuine_client(
            transport=httpx.MockTransport(transport),
            **kw,
        ),
    )
    monkeypatch.setattr("nabla.api.runtime_environment.homelab_runtime_detected", lambda: True)
    monkeypatch.setattr("nabla.api.site_architecture_catalog.fetch_site_catalog_v2", __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=catalog()))
    monkeypatch.setattr(
        "nabla.config_settings.get_settings",
        lambda: SimpleNamespace(
            litellm_url="http://172.17.0.24:4000",
            litellm_api_key=SecretStr("unit-key"),
        ),
    )
    monkeypatch.setattr(live, "managed_prompt", __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=("JSON-only strict prompt", 4)))
    monkeypatch.setenv("FRESHRSS_RELEVANCE_AUTH", "unit-freshrss-auth")
    rows = await live.run_once()
    assert len(rows) == 1
    assert rows[0]["matched"] == ["traefik"]
    assert rows[0]["prompt_version"] == 4
    assert calls[-1][0] == "POST"
    assert all("unit-freshrss-auth" not in str(x) for x in calls)


def test_catalog_projection_rejects_unknown_or_unsafe_catalog():
    revision, technologies = live.technology_projection(catalog())
    assert revision.startswith("sha256:")
    assert "traefik" in technologies
    assert "production" not in technologies
    with pytest.raises(live.RSSConfigurationError):
        live.technology_projection({"catalogRevision": revision})


@pytest.mark.asyncio
async def test_langfuse_must_be_private_versioned_and_never_fallback(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-unit")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-unit")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    with pytest.raises(live.RSSConfigurationError):
        await live.managed_prompt("nabla-homelab-rss-relevance", "production")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.albandrieu.com")

    class Prompt:
        version = 3

        def compile(self):
            return "Strict JSON only"

    class Client:
        def get_prompt(self, name, **kwargs):
            assert kwargs["label"] == "production"
            assert name == "nabla-homelab-rss-relevance"
            return Prompt()

    monkeypatch.setattr("nabla.integrations.langfuse_prompts._langfuse_client", Client)
    assert await live.managed_prompt("nabla-homelab-rss-relevance", "production") == ("Strict JSON only", 3)


@pytest.mark.asyncio
async def test_redis_classification_cache_avoids_repeated_litellm(monkeypatch):
    class MemoryRedis:
        def __init__(self):
            self.data = {}
            self.ttls = []

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, *, ex):
            self.data[key] = value
            self.ttls.append(ex)

    cache = MemoryRedis()
    network_calls = []

    def transport(req):
        network_calls.append(req.method)
        if req.url.path.endswith("/subscription/list"):
            return httpx.Response(200, json={"subscriptions": [{"id": "feed/public", "url": "https://security.example.com/feed"}]})
        if req.url.path.endswith("/stream/contents/reading-list"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "a", "title": "Traefik patch", "origin": {"streamId": "feed/public"}, "summary": {"content": "CVE patch"}},
                    ],
                },
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"relevant":true,"matched":["traefik"],"reason":"Patch"}'}}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        live.httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(transport),
            **kw,
        ),
    )
    monkeypatch.setattr("nabla.api.runtime_environment.homelab_runtime_detected", lambda: True)

    monkeypatch.setattr("nabla.api.site_architecture_catalog.fetch_site_catalog_v2", AsyncMock(return_value=catalog()))
    monkeypatch.setattr(
        "nabla.config_settings.get_settings",
        lambda: SimpleNamespace(
            litellm_url="http://172.17.0.24:4000",
            litellm_api_key=SecretStr("unit-key"),
        ),
    )
    monkeypatch.setattr("nabla.api.external_probe_cache_redis.resolve_redis_client", lambda: cache)
    monkeypatch.setattr(live, "managed_prompt", AsyncMock(return_value=("strict", 2)))
    monkeypatch.setenv("FRESHRSS_RELEVANCE_AUTH", "unit-auth")
    assert len(await live.run_once()) == 1
    assert len(await live.run_once()) == 1
    assert network_calls.count("POST") == 1
    assert cache.ttls == [86400]
    assert all(key.startswith("rss:v1:classify:") for key in cache.data)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["read", "write"])
async def test_redis_cache_failures_never_log_credentials_or_cache_keys(
    monkeypatch,
    caplog,
    failure_stage,
):
    """Redis is best effort; errors never publish credentials or content keys."""

    class FailingCache:
        async def get(self, key):
            if failure_stage == "read":
                raise RedisError("redis://:PRIVATE_CANARY@127.0.0.1:6379")
            return None

        async def set(self, key, value, *, ex):
            assert ex == 86400
            if failure_stage == "write":
                raise RedisError("redis://:PRIVATE_CANARY@127.0.0.1:6379")

    result = json.dumps({"relevant": True, "matched": ["traefik"], "reason": "Patch"})
    llm = AsyncMock(return_value=result)
    monkeypatch.setattr(live, "lite_llm_json", llm)
    async with httpx.AsyncClient(trust_env=False) as client:
        classifier = live._RSSClassifier(
            client=client,
            key="virtual-key-private",
            redis_cache=FailingCache(),
            revision="sha256:" + "a" * 64,
            technologies=["traefik"],
            prompt_version=7,
        )
        with caplog.at_level("WARNING", logger=live.__name__):
            actual = await classifier.classify("strict prompt", "sanitized article")
    assert actual == result
    llm.assert_awaited_once()
    assert "cache" in caplog.text
    assert "PRIVATE_CANARY" not in caplog.text
    assert "rss:v1:classify:" not in caplog.text
    assert "virtual-key-private" not in caplog.text


@pytest.mark.parametrize(
    ("url", "valid"),
    [
        ("http://172.17.0.24:4000", True),
        ("http://192.168.1.24:4000", True),
        ("http://10.2.3.4:4000", True),
        ("http://litellm:4000", True),
        ("https://cloud.example.com:4000", False),
        ("http://8.8.8.8:4000", False),
        ("http://192.168.1.24:4001", False),
        ("http://192.168.1.24:4000/redirect", False),
        ("http://192.168.1.24:4000@attacker.example", False),
    ],
)
def test_private_litellm_endpoint_adapts_to_freebox_without_ssrf(url, valid):
    if valid:
        assert live._checked_litellm_url(url) == url
    else:
        with pytest.raises(live.RSSConfigurationError):
            live._checked_litellm_url(url)


def test_preflight_reports_only_bools_without_credentials(monkeypatch, capsys):
    monkeypatch.setattr("nabla.api.runtime_environment.homelab_runtime_detected", lambda: True)
    monkeypatch.setattr(
        "nabla.config_settings.get_settings",
        lambda: SimpleNamespace(
            litellm_url="http://172.17.0.24:4000",
            litellm_api_key=SecretStr("SECRET_VIRTUAL_KEY_CANARY"),
            truenas_federation_cloud_url="https://fastapi-sample.fastapicloud.dev",
            truenas_federation_secret=SecretStr("S" * 40),
        ),
    )
    monkeypatch.setenv("FRESHRSS_RELEVANCE_AUTH", "SECRET_G_READER_CANARY")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "SECRET_LANGFUSE_CANARY")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.albandrieu.com")
    checks = live.preflight_checks()
    assert checks and all(checks.values())
    assert all(type(value) is bool for value in checks.values())
    monkeypatch.setattr("sys.argv", ["rss_relevance_live.py", "--preflight"])
    assert live.main() == 0
    output = capsys.readouterr().out
    assert json.loads(output)["state"] == "ready_for_live_validation"
    assert "CANARY" not in output
    assert "172.17.0.24" not in output


def test_preflight_handles_absent_credentials_without_network(monkeypatch, capsys):
    monkeypatch.setattr("nabla.api.runtime_environment.homelab_runtime_detected", lambda: True)
    monkeypatch.setattr(
        "nabla.config_settings.get_settings",
        lambda: SimpleNamespace(
            litellm_url="http://localhost:4000",
            litellm_api_key=SecretStr(""),
            truenas_federation_cloud_url="",
            truenas_federation_secret=SecretStr(""),
        ),
    )
    for name in (
        "FRESHRSS_RELEVANCE_AUTH", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL", "FRESHRSS_CF_ACCESS_CLIENT_ID", "FRESHRSS_CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("sys.argv", ["rss_relevance_live.py", "--preflight"])
    assert live.main() == 2
    checks = json.loads(capsys.readouterr().out)["checks"]
    assert checks["freshrss_auth_present"] is False
    assert checks["litellm_endpoint_approved"] is False
    assert checks["langfuse_keys_present"] is False
    assert checks["cloudflare_service_pair_complete"] is True


def test_cli_error_messages_are_safe(monkeypatch):
    from nabla.integrations.freshrss_greader import FreshRSSUnavailable

    assert "Dedicated FreshRSS account not configured" in live.safe_cli_failure(
        live.RSSConfigurationError("Dedicated FreshRSS account not configured")
    )
    assert "GReader request refused" in live.safe_cli_failure(
        FreshRSSUnavailable("GReader request refused")
    )
    assert "SECRET_CANARY" not in live.safe_cli_failure(RuntimeError("SECRET_CANARY"))
    assert "unexpected RuntimeError" in live.safe_cli_failure(RuntimeError("SECRET_CANARY"))
