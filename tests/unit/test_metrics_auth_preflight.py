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
    token.chmod(0o660)
    assert module.read_token_file(token) is None
    token.chmod(0o640)
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


def test_remote_probe_pins_target_and_never_sends_secret(monkeypatch):
    from types import SimpleNamespace

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "origin": "truenas_loopback",
                "path": "/metrics",
                "anonymous_http": 401,
                "authenticated_http": 200,
                "credentials_tested": True,
                "scrape_authorized": True,
                "state": "scrape_auth_accepted",
                "private_token": "never-copy-remote-output",
            }),
            stderr="secret-header-do-not-print",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("METRICS_SCRAPE_KEY", "secret-from-local-machine")
    result, code = module.ssh_status(
        "operator@172.17.0.24", Path("/mnt/cpool/var/nabla/metrics.token"),
    )
    assert code == 0
    assert result["origin"] == "truenas_ssh"
    assert result["scrape_authorized"] is True
    assert "private_token" not in result
    command, kwargs = calls[0]
    assert "-T" in command and "StrictHostKeyChecking=yes" in command
    assert "BatchMode=yes" in command
    assert "--" in command and "operator@172.17.0.24" in command
    assert "python3 - --check" in command[-1]
    assert "--token-file" in command[-1]
    assert "secret-from-local-machine" not in str(command) + kwargs["input"]
    assert "never-copy-remote-output" not in str(result)
    assert "secret-header-do-not-print" not in str(result)
    assert kwargs["timeout"] <= 20


def test_remote_probe_refuses_unapproved_ssh_endpoints(monkeypatch):
    def no_ssh(*args, **kwargs):
        raise AssertionError("SSH must not run")

    monkeypatch.setattr(module.subprocess, "run", no_ssh)
    for target in (
        "operator@198.51.100.7",
        "operator@172.17.0.24;echo-secret",
        "operator@example.org",
        "operator@172.17.0.24 -o ProxyCommand=evil",
        "root@", "", "Operator@172.17.0.24",
    ):
        result, code = module.ssh_status(target)
        assert code == 2 and result["scrape_authorized"] is False
    result, code = module.ssh_status("operator@172.17.0.24", port=0)
    assert code == 2 and result["state"] == "ssh_target_invalid"
    result, code = module.ssh_status("operator@172.17.0.24", Path("relative.key"))
    assert code == 2 and result["state"] == "remote_token_path_invalid"


def test_remote_probe_fails_closed_on_untrusted_output(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        module.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout='{"state":"scrape_auth_accepted","secret":"LEAK"}',
            stderr="untrusted banner token",
        ),
    )
    result, code = module.ssh_status("operator@172.17.0.24")
    assert code == 2 and result["scrape_authorized"] is False
    assert "LEAK" not in str(result)
    assert "untrusted banner" not in str(result)


def test_remote_missing_token_file_yields_a_safe_category(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        module.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2,
            stdout=json.dumps({
                "state": "token_file_invalid_or_unreadable",
                "scrape_authorized": False,
            }),
            stderr="Private token path and secret must remain hidden",
        ),
    )
    result, code = module.ssh_status(
        "operator@172.17.0.24", Path("/mnt/cpool/var/nabla/metrics-token"),
    )
    assert code == 2
    assert result == {
        "origin": "truenas_ssh",
        "state": "remote_token_file_invalid_or_unreadable",
        "scrape_authorized": False,
    }


def test_remote_probe_denial_does_not_become_up(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        module.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=json.dumps({
                "origin": "truenas_loopback",
                "path": "/metrics",
                "anonymous_http": 401,
                "authenticated_http": 401,
                "credentials_tested": True,
                "scrape_authorized": False,
                "state": "scrape_credential_rejected",
            }),
            stderr="",
        ),
    )
    result, code = module.ssh_status("operator@172.17.0.24")
    assert code == 1 and result["scrape_authorized"] is False
    assert result["state"] == "scrape_credential_rejected"
