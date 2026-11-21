"""Hermetic FreshRSS GReader limits and public-only subscription contract."""

import httpx
import pytest

from nabla.integrations.freshrss_greader import FreshRSSUnavailable, recent_public_articles


@pytest.mark.asyncio
async def test_public_subscriptions_only_and_no_html_or_feed_url_leak():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.method == "GET"
        assert request.headers["authorization"] == "GoogleLogin auth=unit-service-token"
        if request.url.path.endswith("/subscription/list"):
            return httpx.Response(
                200,
                json={
                    "subscriptions": [
                        {"id": "feed/pub", "url": "https://security.example.org/feed"},
                        {"id": "feed/private", "url": "http://172.17.0.24/secret"},
                    ],
                },
            )
        if request.url.path.endswith("/stream/contents/reading-list"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "private-id", "title": "Private", "origin": {"streamId": "feed/private"}},
                        {"id": "article-id", "title": "<b>Traefik</b> &amp; CrowdSec", "origin": {"streamId": "feed/pub"}, "summary": {"content": "<p>Security update</p>"}},
                        {"id": "article-id", "title": "duplicate", "origin": {"streamId": "feed/pub"}},
                    ],
                },
            )
        raise AssertionError("unexpected endpoint")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        rows = await recent_public_articles(client, auth="unit-service-token")
    assert len(rows) == 1
    assert rows[0]["title"] == "Traefik & CrowdSec"
    assert rows[0]["summary"] == "Security update"
    assert rows[0]["id"] != "article-id"
    assert not any("private" in str(row) for row in rows)
    assert len(paths) == 2


@pytest.mark.asyncio
async def test_redirect_and_oversized_document_rejected():
    for mode in ("redirect", "large"):

        def handler(_request, *, mode=mode):
            if mode == "redirect":
                return httpx.Response(302, headers={"Location": "https://evil.example/"})
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=b"{" + b"x" * 1_500_001 + b"}",
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            with pytest.raises(FreshRSSUnavailable):
                await recent_public_articles(client, auth="unit-service-token")


@pytest.mark.asyncio
async def test_missing_pair_and_empty_or_internal_feeds_denied():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, json={"subscriptions": [{"id": "private", "url": "https://db.int.albandrieu.com/private"}]})),
        trust_env=False,
    ) as client:
        with pytest.raises(FreshRSSUnavailable):
            await recent_public_articles(client, auth="", limit=1)
        with pytest.raises(FreshRSSUnavailable):
            await recent_public_articles(client, auth="secret", cf_access_id="incomplete")
        with pytest.raises(FreshRSSUnavailable):
            await recent_public_articles(client, auth="unit-service-token")
