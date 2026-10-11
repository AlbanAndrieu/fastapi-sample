"""Static and shell contracts for the portable TrueNAS evidence wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "truenas-runtime-evidence.sh"


def test_portable_script_syntax_and_help_from_another_directory(tmp_path: Path) -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr
    help_result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "--strict" in help_result.stdout


def test_wrapper_is_bounded_and_does_not_expose_secrets() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'dirname -- "${BASH_SOURCE[0]}"' in source
    assert "diagnose-local-runtime-dependencies.py" in source
    assert "--report-only" in source
    assert "docker ps -a" in source
    assert "--max-time 5" in source
    assert "docker logs" not in source
    assert ".Config.Env" not in source
    assert "docker restart" not in source
    assert "docker exec" not in source


def test_vantage_selection_is_documented_and_prevents_local_docker_confusion() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--vantage" in source
    assert "workstation" in source
    assert 'if [[ "$vantage" != truenas ]]' in source
    assert "DOCKER_HOST" in source
    assert "DOCKER_CONTEXT" in source
    assert "ix-postgres-postgres-1" in source
    assert "ix-sentry-sentry-web-1" in source


def test_invalid_vantage_returns_error(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--vantage", "invalid"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Invalid vantage" in result.stderr


def test_local_docker_lines_do_not_print_literal_backslash_n() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for line in source.splitlines():
        if "local %-10s" in line:
            assert r"\\n" not in line
            assert r"\n" in line


def test_http_readiness_distinguishes_non_2xx_from_transport_failure() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "HTTP responded; readiness not confirmed" in source
    assert "result='unreachable'" in source
    assert "missing cached metric is a reconciliation gap" in source
    assert "Pyroscope readiness: recovered at this vantage" in source
