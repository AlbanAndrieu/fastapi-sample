"""No-network routing contract for workstation and isolated agent diagnostics."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/agent-diagnostics.sh"


def _plan(profile: str, scope: str, *, claude: bool = False) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "FASTAPI_AGENT_PROFILE": "isolated"}
    env.pop("CODEX_HOME", None)
    env.pop("CODEX_THREAD_ID", None)
    env.pop("CI", None)
    if claude:
        env["CLAUDECODE"] = "1"
    return subprocess.run(
        ["bash", str(SCRIPT), "--profile", profile, "--scope", scope, "--plan"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )


def test_bash_script_syntax_and_cli_help() -> None:
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr
    help_output = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True, check=False)
    assert help_output.returncode == 0
    assert "--scope" in help_output.stdout


def test_isolated_never_plans_private_network_or_docker_probe() -> None:
    for scope in ("runtime", "dns", "metrics", "metrics-both"):
        result = _plan("isolated", scope)
        assert result.returncode == 0, result.stderr
        assert "LIVE_RUNTIME=NOT_RUN" in result.stdout
        assert "scripts/agent-offline-check.sh" in result.stdout
        assert "truenas-runtime-evidence.sh" not in result.stdout
        assert "verify-prometheus-cloud-projection.py" not in result.stdout


def test_workstation_opt_in_only_selects_bounded_read_only_collectors() -> None:
    expected = {
        "runtime": "truenas-runtime-evidence.sh",
        "dns": "truenas-runtime-evidence.sh",
        "metrics": "verify-prometheus-cloud-projection.py",
        "metrics-both": "verify-prometheus-cloud-projection.py",
    }
    for scope, collector in expected.items():
        result = _plan("workstation", scope)
        assert result.returncode == 0, result.stderr
        assert "PROFILE=workstation" in result.stdout
        assert collector in result.stdout
        assert "L1=offline-only" not in result.stdout


def test_invalid_profile_or_scope_is_rejected_before_probe() -> None:
    for args in (["--profile", "unknown"], ["--scope", "unknown"]):
        result = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, check=False)
        assert result.returncode == 2


def test_codex_indicator_disables_requested_workstation_execution(tmp_path: Path) -> None:
    env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex")}
    result = subprocess.run(
        ["bash", str(SCRIPT), "--profile", "workstation", "--scope", "runtime", "--plan"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=12,
    )
    assert result.returncode == 0, result.stderr
    assert "LIVE_RUNTIME=NOT_RUN" in result.stdout
    assert "scripts/agent-offline-check.sh" in result.stdout
