"""Offline-only contracts for bounded workstation observability diagnostics."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/agent-diagnostics.sh"


def _invoke(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    safe = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/")}
    if env:
        safe.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=safe,
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
    )


def test_shell_syntax_and_help() -> None:
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    help_output = _invoke("--help")
    assert help_output.returncode == 0
    assert "--metrics-lan" in help_output.stdout
    assert "--plan" in help_output.stdout


@pytest.mark.parametrize("action", ["--runtime", "--dns-only", "--metrics-lan", "--metrics-both"])
def test_offline_rejects_live_probe_before_execution(action: str) -> None:
    result = _invoke(action, "--plan")
    assert result.returncode == 2
    assert "NOT_RUN" in result.stderr
    assert "PLAN" not in result.stdout


@pytest.mark.parametrize(
    ("action", "collector", "scope"),
    [
        ("--runtime", "truenas-runtime-evidence.sh", "--quick"),
        ("--dns-only", "truenas-runtime-evidence.sh", "--dns-only"),
        ("--metrics-lan", "verify-prometheus-cloud-projection.py", "lan"),
        ("--metrics-both", "verify-prometheus-cloud-projection.py", "both"),
    ],
)
def test_workstation_plan_is_read_only_and_never_runs_probe(
    action: str,
    collector: str,
    scope: str,
) -> None:
    result = _invoke(action, "--plan", env={"AGENT_EXECUTION_MODE": "workstation"})
    assert result.returncode == 0, result.stderr
    assert "NOT_RUN" in result.stdout
    assert collector in result.stdout
    assert scope in result.stdout


@pytest.mark.parametrize("sentinel", ["CI", "CODEX_HOME", "CODEX_THREAD_ID"])
def test_ci_codex_cannot_run_even_if_workstation_requested(sentinel: str) -> None:
    result = _invoke(
        "--runtime",
        "--plan",
        env={"AGENT_EXECUTION_MODE": "workstation", sentinel: "true"},
    )
    assert result.returncode == 2
    assert "NOT_RUN" in result.stderr


@pytest.mark.parametrize("arguments", [("--mode", "unknown"), ("--bogus",)])
def test_unknown_options_fail_closed(arguments: tuple[str, ...]) -> None:
    result = _invoke(*arguments)
    assert result.returncode == 2
