"""Offline tests for host-side split-DNS diagnostics."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diagnose-homelab-dns.py"
spec = importlib.util.spec_from_file_location("diagnose_homelab_dns", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_ipv4_answers_deduplicate_getent_and_dig():
    assert mod.ipv4_answers("172.17.0.24 STREAM a\n172.17.0.24 DGRAM\n") == [
        "172.17.0.24"
    ]
    assert mod.ipv4_answers("188.114.97.0\n188.114.96.0\n") == [
        "188.114.96.0",
        "188.114.97.0",
    ]


def test_mismatch_not_healthy():
    assert mod.classify_internal(["172.17.0.24"], None, "172.17.0.24") == "unverified"
    assert (
        mod.classify_internal(["172.17.0.24"], [], "172.17.0.24")
        == "system_resolver_mismatch"
    )
    assert (
        mod.classify_internal([], ["172.17.0.24"], "172.17.0.24")
        == "pfsense_record_mismatch"
    )
    assert (
        mod.classify_internal(["172.17.0.24"], ["172.17.0.24"], "172.17.0.24")
        == "matched"
    )


def test_strict_both_vantages_offline(monkeypatch, capsys):
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mock")
    seen = []

    def fake_run(command, **_kwargs):
        seen.append(command)
        host = next(x for x in command if "sample." in x)
        is_direct = command[0] == "dig"
        if host.startswith("sample.int"):
            value = (
                "172.17.0.24\n"
                if is_direct
                else "172.17.0.24 STREAM sample.int.albandrieu.com\n"
            )
        else:
            value = (
                "188.114.96.0\n"
                if is_direct
                else "188.114.97.0 STREAM sample.albandrieu.com\n"
            )
        return SimpleNamespace(returncode=0, stdout=value)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    for vantage in ("workstation", "truenas"):
        assert mod.main(["--vantage", vantage, "--strict"]) == 0
    assert len(seen) == 8
    output = capsys.readouterr().out
    assert "matched" in output
    assert "ms" in output


def test_missing_dig_fails_strict_not_default(monkeypatch, capsys):
    monkeypatch.setattr(
        mod.shutil,
        "which",
        lambda name: None if name == "dig" else "/usr/bin/getent",
    )
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda _cmd, **_kwargs: SimpleNamespace(
            returncode=0, stdout="172.17.0.24 STREAM\n"
        ),
    )
    assert mod.main(["--vantage", "truenas"]) == 0
    assert mod.main(["--vantage", "truenas", "--strict"]) == 1
    assert "NOT_RUN" in capsys.readouterr().out


def test_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mock")

    def slow(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 3)

    monkeypatch.setattr(mod.subprocess, "run", slow)
    assert mod.main(["--vantage", "workstation", "--strict"]) == 1
