"""Offline CIDR and spoofed-header policy contracts for owner endpoints."""

from types import SimpleNamespace

import pytest

from nabla.homelab_trusted_ip import allowed_owner_source, parse_cidrs


def _settings(**kwargs):
    return SimpleNamespace(
        homelab_trusted_cidrs="82.66.4.247/32",
        homelab_trusted_proxy_cidrs="",
        **kwargs,
    )


def test_only_configured_public_home_ip_is_trusted() -> None:
    settings = _settings()
    assert allowed_owner_source({"client": ("82.66.4.247", 53000)}, settings)
    for address in ("82.66.4.246", "172.17.0.57", "203.0.113.25"):
        assert not allowed_owner_source({"client": (address, 53000)}, settings)
    assert not allowed_owner_source({"client": None}, settings)


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        " ",
        "bad-ip",
        "82.66.4.247/33",
        "0.0.0.0/0",
        "::/0",
        "82.66.4.247/32,",
        ",82.66.4.247/32",
    ],
)
def test_invalid_configuration_denied(invalid: str) -> None:
    if invalid.strip():
        with pytest.raises(ValueError):
            parse_cidrs(invalid)
    settings = SimpleNamespace(homelab_trusted_cidrs=invalid)
    assert not allowed_owner_source({"client": ("82.66.4.247", 53000)}, settings)


def test_proxy_source_requires_explicit_peer_and_single_consistent_header() -> None:
    settings = SimpleNamespace(
        homelab_trusted_cidrs="82.66.4.247/32",
        homelab_trusted_proxy_cidrs="10.30.0.5/32",
    )
    peer = {"client": ("10.30.0.5", 443)}
    assert allowed_owner_source(
        {**peer, "headers": [(b"x-forwarded-for", b"82.66.4.247")]},
        settings,
    )
    for headers in (
        [(b"x-forwarded-for", b"82.66.4.246")],
        [(b"x-forwarded-for", b"82.66.4.247, 203.0.113.9")],
        [
            (b"x-forwarded-for", b"82.66.4.247"),
            (b"x-forwarded-for", b"82.66.4.247"),
        ],
        [
            (b"x-forwarded-for", b"82.66.4.247"),
            (b"cf-connecting-ip", b"203.0.113.9"),
        ],
    ):
        assert not allowed_owner_source({**peer, "headers": headers}, settings)
    assert not allowed_owner_source(
        {
            "client": ("203.0.113.9", 443),
            "headers": [(b"x-forwarded-for", b"82.66.4.247")],
        },
        settings,
    )


def test_malformed_asgi_headers_fail_closed() -> None:
    settings = _settings()
    for headers in (
        None,
        "invalid",
        [("x-forwarded-for", "82.66.4.247")],
        [(b"x-forwarded-for",)],
        [(b"x-forwarded-for", b"82.66.4.247", b"extra")],
    ):
        assert not allowed_owner_source(
            {"client": ("82.66.4.247", 443), "headers": headers},
            settings,
        )


def test_strict_cidr_and_ipv6_support() -> None:
    with pytest.raises(ValueError):
        parse_cidrs("82.66.4.247/24")
    assert len(parse_cidrs("82.66.4.247/32,2001:db8::1/128")) == 2
