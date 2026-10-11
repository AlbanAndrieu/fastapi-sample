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
