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


def test_nss_has_independent_longer_bounded_timeout(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mock")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command[0], kwargs["timeout"]))
        ip = "172.17.0.24" if "sample.int.albandrieu.com" in command else "188.114.96.2"
        return SimpleNamespace(returncode=0, stdout=f"{ip}\n")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.main(["--vantage", "workstation", "--strict"]) == 0
    assert calls == [("dig", 3), ("getent", 10), ("dig", 3), ("getent", 10)]


def test_slow_but_correct_system_answer_is_not_reported_fast(monkeypatch, capsys):
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mock")
    ticks = iter((0, 0.04, 0.04, 6.04, 6.04, 6.05, 6.05, 6.06))
    monkeypatch.setattr(mod, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))

    def fake_run(command, **_kwargs):
        ip = "172.17.0.24" if "sample.int.albandrieu.com" in command else "188.114.96.2"
        return SimpleNamespace(returncode=0, stdout=f"{ip}\n")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.main(["--vantage", "truenas", "--strict"]) == 1
    output = capsys.readouterr().out
    assert "Internal DNS comparison=matched_slow" in output
    assert "6000.0ms" in output
    assert "WARNING: host resolver returned" in output


def test_system_timeout_preserves_unverified_and_recommends_host_checks(
    monkeypatch, capsys
):
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mock")

    def fake_run(command, **_kwargs):
        if command[0] == "getent" and "sample.int.albandrieu.com" in command:
            raise subprocess.TimeoutExpired(command, 10)
        ip = "172.17.0.24" if "sample.int.albandrieu.com" in command else "188.114.96.2"
        return SimpleNamespace(returncode=0, stdout=f"{ip}\n")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.main(["--vantage", "truenas", "--strict"]) == 1
    output = capsys.readouterr().out
    assert "Internal DNS comparison=unverified" in output
    assert "DIAGNOSIS: direct pfSense DNS works" in output
    assert "/etc/nsswitch.conf" in output


def test_link_dns_parsing_rejects_non_ip_metadata():
    assert mod.link_ipv4_servers(
        "Link 2 (eno1): 9.9.9.9 149.112.112.112 invalid"
    ) == ["149.112.112.112", "9.9.9.9"]


def test_resolver_context_explains_quad9_split_dns(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/mock")

    def fake_run(command, **kwargs):
        assert kwargs["timeout"] == 2
        replies = {
            "dns": "Link 2 (eno1): 9.9.9.9 149.112.112.112",
            "domain": "Link 2 (eno1): int.albandrieu.com",
            "status": "Link 2 (eno1) DNSOverTLS=opportunistic",
        }
        return SimpleNamespace(returncode=0, stdout=replies[command[1]])

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    context = mod.resolver_context("workstation", "eno1", "172.17.0.1")
    assert "pfSense not a DNS server on this link" in context
    assert "link_dot=opportunistic" in context
    assert "link_dns=149.112.112.112,9.9.9.9" in context
    assert "private_domain_route=yes" in context


def test_resolver_context_good_truenas_and_absent_command(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/mock")

    def fake_run(command, **_kwargs):
        replies = {
            "dns": "Link 2 (br0): 172.17.0.1",
            "domain": "Link 2 (br0): ~int.albandrieu.com",
            "status": "Link 2 (br0) DNSOverTLS=no",
        }
        return SimpleNamespace(returncode=0, stdout=replies[command[1]])

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    context = mod.resolver_context("truenas", "br0", "172.17.0.1")
    assert "private_domain_route=yes" in context
    assert "pfSense not a DNS" not in context
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    assert "unavailable" in mod.resolver_context("truenas", "br0", "172.17.0.1")
