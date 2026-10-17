"""Regression: the canonical gate supports an uv-only installation without uvx."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "quality-gate.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_repo(repo: Path) -> None:
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "quality-gate.sh").write_text(
        GATE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo / ".editorconfig").write_text("root = true\n", encoding="utf-8")
    (repo / ".editorconfig-checker.json").write_text("{}\n", encoding="utf-8")
    (repo / "README.md").write_text("first\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Quality gate fixture")
    _git(repo, "-c", "core.hooksPath=/dev/null", "add", ".")
    _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "initial")
    (repo / "README.md").write_text("second\n", encoding="utf-8")
    _git(repo, "-c", "core.hooksPath=/dev/null", "add", "README.md")
    _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "change")


def _run(
    repo: Path,
    tmp_path: Path,
    *,
    uv_available: bool = True,
) -> tuple[subprocess.CompletedProcess[str], str]:
    env_file = tmp_path / "bash_env.sh"
    log_file = tmp_path / "commands.log"
    env_file.write_text(
        """# Environment function mocks avoid executing temporary files on /tmp noexec.
command() {
    if [[ "$1" == '-v' ]]; then
        case "$2" in
            ec|editorconfig-checker|uvx) return 1 ;;
            uv) [[ "${QG_NO_UV:-0}" == 1 ]] && return 1 ;;
        esac
    fi
    builtin command "$@"
}
pre-commit() {
    printf 'pre-commit %s\\n' "$*" >> "$QG_MOCK_LOG"
    return 0
}
uv() {
    printf 'uv %s\\n' "$*" >> "$QG_MOCK_LOG"
    [[ "$1" == tool && "$2" == run && "$3" == --from &&
        "$4" == editorconfig-checker==3.11.1 && "$5" == ec &&
        "$6" == -config ]]
}
        """,
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "BASH_ENV": str(env_file),
            "QG_MOCK_LOG": str(log_file),
            "QG_NO_UV": "0" if uv_available else "1",
        },
    )
    completed = subprocess.run(
        ["bash", "scripts/quality-gate.sh"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return completed, (log_file.read_text(encoding="utf-8") if log_file.exists() else "")


def test_quality_gate_uses_uv_tool_run_when_uvx_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo)
    completed, commands = _run(repo, tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "pre-commit run --hook-stage pre-commit" in commands
    assert "uv tool run --from editorconfig-checker==3.11.1 ec -config" in commands
    assert "✅ Quality gate passed" in completed.stdout


def test_quality_gate_fails_closed_when_no_editorconfig_runner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo)
    completed, commands = _run(repo, tmp_path, uv_available=False)
    assert completed.returncode == 2
    assert "editorconfig-checker is required" in completed.stdout
    assert "uv tool run" not in commands
