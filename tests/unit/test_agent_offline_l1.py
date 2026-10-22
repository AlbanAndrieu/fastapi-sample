"""No-network subprocess contracts for the dependency-free agent L1 gate."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OFFLINE = ROOT / "scripts/agent-offline-check.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _fixture(repo: Path) -> None:
    (repo / "scripts/ci").mkdir(parents=True)
    (repo / "scripts/ci/check_draft_workflows.py").write_text(
        'raise SystemExit(0)\n',
        encoding="utf-8",
    )
    (repo / "valid.json").write_text('{"ok": true}\n', encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "offline-tests@example.invalid")
    _git(repo, "config", "user.name", "Offline Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")


def _run(repo: Path, **variables: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(OFFLINE)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
        env={**os.environ, **variables},
    )


def test_offline_l1_succeeds_with_strict_json_and_no_base(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OFFLINE_BASE_UNAVAILABLE" in result.stderr
    assert "OFFLINE_L1_PASS" in result.stdout
    assert "NOT_RUN" in result.stdout


def test_offline_l1_rejects_invalid_untracked_json(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "broken.json").write_text('{"broken": }\n', encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "JSONDecodeError" in result.stderr


def test_offline_l1_rejects_python_syntax_errors(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "broken.py").write_text("def f(: pass\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "SyntaxError" in result.stderr


def test_offline_l1_refuses_unsafe_scope_truncation(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _run(tmp_path, AGENT_OFFLINE_MAX_PATHS="1")
    assert result.returncode == 2
    assert "OFFLINE_LIMIT_EXCEEDED" in result.stderr
