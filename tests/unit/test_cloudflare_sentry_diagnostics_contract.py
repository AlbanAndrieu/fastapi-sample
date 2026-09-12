"""Static contracts for Cloudflare/Sentry operator diagnostics."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cloudflare_badge_is_provider_named_and_exposes_control_plane_counts() -> None:
    javascript = (ROOT / "nabla/api/assets/api-cloudflare-status.js").read_text(
        encoding="utf-8",
    )

    assert "<span>Cloudflare</span>" in javascript
    assert "config_src=" not in javascript
    assert "Tunnel ${tunnel.name" in javascript
    assert "status=${tunnel.status" in javascript
    assert "Access apps" in javascript
    assert "Reusable policies" in javascript
    assert "Service Tokens" in javascript
    assert "Service Token ${tokenOutcome}" in javascript


def test_successful_demo_tasks_do_not_emit_error_events() -> None:
    source = (ROOT / "nabla/api/ping.py").read_text(encoding="utf-8")

    assert 'logger.error("io task")' not in source
    assert 'logger.error("cpu task")' not in source
    assert 'logger.info("io task completed")' in source
    assert 'logger.info("cpu task completed")' in source


def test_cloudflare_sentry_diagnostics_are_documented() -> None:
    document = (ROOT / "docs/cloudflare-sentry-runtime-diagnostics.md").read_text(
        encoding="utf-8",
    )

    assert "nabla-truescale" in document
    assert "2fauth.albandrieu.com -> http://172.17.0.24:30081" in document
    assert "Connection timed out - goodbye" in document
    assert "TLS 1.2 or newer" in document
