"""Hermetic FreshRSS GReader limits and public-only subscription contract."""

import httpx
import pytest

from nabla.integrations.freshrss_greader import FreshRSSUnavailable, _plain_text, _project_recent_public_articles, recent_public_articles


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
                        {
                            "id": "article-id",
                            "title": "<b>Traefik</b> &amp; CrowdSec",
                            "origin": {"streamId": "feed/pub"},
                            "summary": {"content": "<p>Security update</p>"},
                            "canonical": [{"href": "http://172.17.0.24/tracker"}],
                            "alternate": [{"href": "https://security.example.org/traefik-crowdsec", "type": "text/html"}],
                        },
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
    assert rows[0]["url"] == "https://security.example.org/traefik-crowdsec"  # the LAN canonical link is dropped
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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("&lt;script&gt;FAKE_CREDENTIAL&lt;/script&gt; Cloudflare", "Cloudflare"),
        ("<style>hidden</style><p>CrowdSec <b>AppSec</b></p>", "CrowdSec AppSec"),
        ("Traefik\u202e reverse\u200f proxy\x00", "Traefik reverse proxy"),
        ("<div>Line1<br/>Line2</div>", "Line1 Line2"),
    ],
)
def test_untrusted_html_and_bidi_controls_are_removed(source: str, expected: str) -> None:
    assert _plain_text(source, 300) == expected


def test_untrusted_article_projection_has_bounded_text_cost() -> None:
    assert len(_plain_text("<b>" + "a" * 50000 + "</b>", 300)) == 300


@pytest.mark.parametrize(
    "malformed_feed_id",
    [[], {"stream": "feed/public"}, 7, None, "a" * 513],
)
def test_untrusted_greader_origin_id_is_skipped_without_aborting_public_articles(malformed_feed_id):
    items = [
        {"id": "untrusted", "title": "Reject", "origin": {"streamId": malformed_feed_id}},
        {"id": "approved", "title": "Traefik security", "origin": {"streamId": "feed/public"}},
    ]
    rows = _project_recent_public_articles(items, {"feed/public"}, 5)
    assert len(rows) == 1
    assert rows[0]["title"] == "Traefik security"


def test_public_article_rotation_covers_multiple_waves_without_extra_inference():
    items = [{"id": f"article-{index}", "title": f"Security advisory {index}", "origin": {"streamId": "feed/public"}} for index in range(13)]
    first = _project_recent_public_articles(items, {"feed/public"}, 5, 0)
    second = _project_recent_public_articles(items, {"feed/public"}, 5, 1)
    third = _project_recent_public_articles(items, {"feed/public"}, 5, 2)
    assert len({article["id"] for article in first + second + third}) == 13
    assert all(len(batch) <= 5 for batch in (first, second, third))
    assert _project_recent_public_articles(items, {"feed/public"}, 5, 0) == first
    with pytest.raises(FreshRSSUnavailable):
        _project_recent_public_articles(items, {"feed/public"}, 5, -1)
