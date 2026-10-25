"""Offline contracts for the bounded TrueNAS FastAPI scrape preflight."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/truenas/diagnose-fastapi-metrics-auth.py"
spec = importlib.util.spec_from_file_location("metrics_auth_preflight", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    ("anonymous", "authorized", "token_supplied", "state", "approved"),
    [
        (401, None, False, "key_configured_scraper_credentials_unverified", False),
        (401, 200, True, "scrape_auth_accepted", True),
        (401, 401, True, "scrape_credential_rejected", False),
        (401, 503, True, "authenticated_gate_unavailable", False),
        (401, None, True, "authenticated_probe_unverified", False),
        (503, None, False, "metrics_key_unconfigured_or_gate_unavailable", False),
        (200, None, False, "unexpected_anonymous_metrics_access", False),
        (None, None, False, "metrics_origin_unverified", False),
    ],
)
def test_metrics_scrape_states(anonymous, authorized, token_supplied, state, approved):
    result = module.assess(anonymous, authorized, token_supplied)
    assert result["state"] == state
    assert result["scrape_authorized"] is approved
    assert "http://" not in str(result)
    assert "secret" not in str(result)


def test_token_file_is_private_bounded_and_not_symlink(tmp_path):
    token = tmp_path / "scrape.token"
    token.write_text("private-test-token\n", encoding="utf-8")
    token.chmod(0o600)
    assert module.read_token_file(token) == "private-test-token"
    token.chmod(0o640)
    assert module.read_token_file(token) == "private-test-token"
    token.chmod(0o644)
    assert module.read_token_file(token) is None
    token.chmod(0o600)
    link = tmp_path / "scrape.link"
    link.symlink_to(token)
    assert module.read_token_file(link) is None
    token.write_bytes(b"x" * 513)
    assert module.read_token_file(token) is None


def test_main_prints_only_redacted_classification(monkeypatch, capsys):
    monkeypatch.setattr(module, "http_status", lambda token: 401 if token is None else 200)
    monkeypatch.setenv("METRICS_SCRAPE_KEY", "never-print-secret")
    monkeypatch.setattr("sys.argv", ["diagnose-fastapi-metrics-auth.py", "--check"])
    assert module.main() == 0
    output = capsys.readouterr().out
    assert json.loads(output)["scrape_authorized"] is True
    assert "never-print-secret" not in output
    assert "127.0.0.1" not in output


def test_without_token_is_unverified_not_a_failure(monkeypatch, capsys):
    monkeypatch.delenv("METRICS_SCRAPE_KEY", raising=False)
    monkeypatch.setattr(module, "http_status", lambda token: 401)
    monkeypatch.setattr("sys.argv", ["diagnose-fastapi-metrics-auth.py", "--check"])
    assert module.main() == 2
    record = json.loads(capsys.readouterr().out)
    assert record["state"] == "key_configured_scraper_credentials_unverified"
    assert record["authenticated_http"] is None
