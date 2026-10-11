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


def test_cloudflare_sentry_diagnostics_are_application_owned() -> None:
    document = (ROOT / "docs/cloudflare-sentry-runtime-diagnostics.md").read_text(
        encoding="utf-8",
    )

    canonical_runbook = (
        "nabla-compose/blob/master/docs/"
        "cloudflare-sentry-platform-diagnostics.md"
    )
    assert canonical_runbook in document
    assert "SENTRY_LOCAL_DSN" in document
    assert "status_confirmed" not in document
    assert "Connection timed out - goodbye" in document
    assert "TLS 1.2 or newer" in document
    assert "2fauth.albandrieu.com ->" not in document


def test_pfsense_recovery_points_to_platform_owner() -> None:
    document = (ROOT / "docs/pfsense-webconfigurator-recovery.md").read_text(
        encoding="utf-8",
    )

    assert "nabla-compose/blob/master/docs/pfsense-diagnose-recover.md" in document
    assert "HTTP 502" in document
    assert "PFSENSE_POSTURE_API_KEY" in document
    assert "2026-09-08-pfsense-webconfigurator-http-502.md" in document
    assert "/etc/rc.php-fpm_restart" not in document
    assert "--unblock-sources" not in document


def test_documentation_owner_is_explicit_in_agent_guide() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Documentation ownership across Nabla repositories" in agents
    assert "nabla-compose" in agents
