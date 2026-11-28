"""Security and contract tests for the FreshRSS → Cloud → Site Alban handoff."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from pydantic import SecretStr
import pytest

from nabla.api import rss_publication as pub
from nabla.route_policy import Credential, Visibility, route_policy_for


REVISION = "sha256:" + "a" * 64
ARTICLE = "b" * 64
SECRET = "s" * 40


def decision() -> dict:
    return {
        "article_id": ARTICLE,
        "title": "Traefik CVE untrusted text",
        "matched": ["traefik", "kubernetes"],
        "reason": "Not exported",
        "prompt_version": 3,
        "catalogRevision": REVISION,
        "content_sha256": "c" * 64,
    }


def test_closed_schema_never_exports_articles_or_model_reasoning():
    value = pub.build_batch([decision()], now=1000)
    assert pub.validate_batch(value, now=1000) == value
    raw = json.dumps(value)
    assert set(value["items"][0]) == {"article_id", "matched"}
    assert "Traefik CVE" not in raw
    assert "Not exported" not in raw
    assert "content_sha256" not in raw
    for tampered in (
        {**value, "title": "leak"},
        {**value, "observed_at": 600},
        {**value, "items": [{**value["items"][0], "url": "http://192.168.1.1"}]},
        {**value, "items": [{"article_id": ARTICLE, "matched": ["../../secret"]}]},
        {**value, "items": value["items"] * 2},
        {**value, "promptVersion": True},
    ):
        assert pub.validate_batch(tampered, now=1000) is None


def test_rejects_mixed_versions_and_non_hash_ids():
    with pytest.raises(ValueError):
        pub.build_batch([{**decision(), "article_id": "not-a-hash"}], now=1000)
    with pytest.raises(ValueError):
        pub.build_batch([decision(), {**decision(), "prompt_version": 4}], now=1000)


class RedisFake:
    def __init__(self):
        self.data = None
        self.calls = 0

    async def eval(self, _lua, num_keys, key, payload, observed):
        assert num_keys == 1
        assert key == pub._CACHE_KEY
        self.calls += 1
        body = json.loads(payload)
        if self.data and body["observed_at"] <= self.data["observed_at"]:
            return 0
        body["items"] = [
            {"article_id": row["article_id"], "matched": row["matched"], "seen_at": observed}
            for row in body["items"]
        ]
        self.data = body
        return 1

    async def get(self, key):
        assert key == pub._CACHE_KEY
        return json.dumps(self.data) if self.data else None


@pytest.fixture
def app(monkeypatch):
    from time import time

    monkeypatch.setenv("RSS_RELEVANCE_PUBLICATION_ENABLED", "true")
    monkeypatch.setattr(pub, "fastapi_cloud_runtime_detected", lambda host=None: True)
    monkeypatch.setattr(
        pub,
        "get_settings",
        lambda: SimpleNamespace(
            truenas_federation_secret=SecretStr(SECRET),
            truenas_federation_cloud_url="https://fastapi-sample.fastapicloud.dev",
        ),
    )
    cache = RedisFake()
    monkeypatch.setattr(pub, "_redis", lambda: cache)
    application = FastAPI()
    pub.register_routes(application)
    return TestClient(application), cache, int(time())


def test_ingestion_hmac_replay_and_public_projection(app, monkeypatch):
    client, cache, now = app
    payload = pub.build_batch([decision()], now=now)
    raw = json.dumps(payload).encode()
    headers = {"content-type": "application/json", pub.SIGNATURE_HEADER: pub.sign(raw, SECRET)}
    assert client.post(pub.INGEST_PATH, content=raw, headers=headers).status_code == 202
    assert client.post(pub.INGEST_PATH, content=raw, headers=headers).status_code == 409
    visible = client.get(pub.PUBLIC_PATH)
    assert visible.status_code == 200
    output = visible.json()
    assert output["model"] == "rss-relevance"
    assert output["items"] == [{"article_id": ARTICLE, "matched": ["kubernetes", "traefik"]}]
    assert "promptVersion" in output and "catalogRevision" in output
    assert cache.calls == 2

    assert client.post(
        pub.INGEST_PATH,
        content=raw,
        headers={"content-type": "application/json", pub.SIGNATURE_HEADER: pub.sign(raw, "x" * 40)},
    ).status_code == 401
    assert client.post(pub.INGEST_PATH, content=b"x" * (pub.MAX_BODY_BYTES + 1), headers=headers).status_code == 413
    monkeypatch.setenv("RSS_RELEVANCE_PUBLICATION_ENABLED", "false")
    assert client.get(pub.PUBLIC_PATH).status_code == 404
    assert client.post(pub.INGEST_PATH, content=raw, headers=headers).status_code == 404


def test_empty_cache_or_unconfigured_redis_is_not_invented_success(app, monkeypatch):
    client, _cache, now = app
    assert client.get(pub.PUBLIC_PATH).status_code == 503
    monkeypatch.setattr(pub, "_redis", lambda: None)
    value = pub.build_batch([decision()], now=now)
    raw = json.dumps(value).encode()
    assert client.post(
        pub.INGEST_PATH,
        content=raw,
        headers={"content-type": "application/json", pub.SIGNATURE_HEADER: pub.sign(raw, SECRET)},
    ).status_code == 503


@pytest.mark.asyncio
async def test_producer_is_true_nas_only_and_never_targets_arbitrary_url(monkeypatch):
    monkeypatch.setattr(pub, "homelab_runtime_detected", lambda: True)
    settings = SimpleNamespace(
        truenas_federation_secret=SecretStr(SECRET),
        truenas_federation_cloud_url="https://fastapi-sample.fastapicloud.dev",
    )
    monkeypatch.setattr(pub, "get_settings", lambda: settings)
    captures = []

    def handler(request: httpx.Request) -> httpx.Response:
        captures.append(request)
        return httpx.Response(202)

    assert await pub.publish([decision()], transport=httpx.MockTransport(handler)) == "sent"
    assert len(captures) == 1
    assert str(captures[0].url) == "https://fastapi-sample.fastapicloud.dev/federation/rss"
    assert "Traefik CVE" not in captures[0].content.decode()
    settings.truenas_federation_cloud_url = "https://attacker.example"
    assert await pub.publish([decision()], transport=httpx.MockTransport(handler)) == "unapproved_target"
    monkeypatch.setattr(pub, "homelab_runtime_detected", lambda: False)
    assert await pub.publish([decision()], transport=httpx.MockTransport(handler)) == "disabled"


def test_api_policy_separates_public_read_and_hmac_ingestion():
    read = route_policy_for(pub.PUBLIC_PATH, method="GET")
    write = route_policy_for(pub.INGEST_PATH, method="POST")
    assert read.visibility is Visibility.PUBLIC_CANDIDATE
    assert write.visibility is Visibility.SERVICE
    assert write.credential is Credential.FEDERATION_HMAC
    assert route_policy_for(pub.INGEST_PATH, method="GET").visibility is Visibility.REVIEW
