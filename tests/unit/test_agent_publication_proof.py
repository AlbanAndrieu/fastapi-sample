"""Behavioral tests for the local publication-proof cache."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent-publish.sh"


def _run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _git(cwd: Path, *args: str) -> str:
    return _run(cwd, "git", *args).stdout.strip()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_uv(version: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1:-}}" == "--version" ]]; then
    printf '%s\\n' 'uv {version}'
    exit 0
fi
if [[ "${{1:-}}" == "build" ]]; then
    printf '1\\n' >> "${{QUALITY_TEST_BUILD_COUNTER}}"
    exit 0
fi
if [[ "${{1:-}}" == "run" && "${{2:-}}" == "--no-sync" ]]; then
    case "${{3:-}}" in
        python)
            if [[ "${{4:-}}" == "--version" ]]; then
                printf '%s\\n' 'Python 3.13.7'
            fi
            exit 0
            ;;
        pre-commit)
            printf '%s\\n' 'pre-commit 4.6.2'
            exit 0
            ;;
        pylint)
            exit 0
            ;;
    esac
fi
exit 2
"""


def test_publication_proof_reuses_exact_head_base_and_toolchain(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "quality@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Proof")

    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "base")

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    counter = tmp_path / ".git" / "gate-count.txt"
    build_counter = tmp_path / ".git" / "build-count.txt"
    _write_executable(
        scripts / "agent-quality-gate.sh",
        """#!/usr/bin/env bash
set -euo pipefail
printf '1\\n' >> "${QUALITY_TEST_COUNTER}"
""",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "server_app.py").write_text("app = object()\n", encoding="utf-8")
    _git(tmp_path, "add", "scripts/agent-quality-gate.sh", "uv.lock", "server_app.py")
    _git(tmp_path, "commit", "-m", "head")

    fake_bin = tmp_path / ".git" / "fake-bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", _fake_uv("0.12.1"))

    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "QUALITY_TEST_COUNTER": str(counter),
        "QUALITY_TEST_BUILD_COUNTER": str(build_counter),
    }

    first = _run(tmp_path, "bash", str(SCRIPT), env=env)
    assert "QG_PUBLISH_PROOF_WRITTEN" in first.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]
    assert build_counter.read_text(encoding="utf-8").splitlines() == ["1"]

    second = _run(tmp_path, "bash", str(SCRIPT), env=env)
    assert "QG_PUBLISH_PROOF_REUSED" in second.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]
    assert build_counter.read_text(encoding="utf-8").splitlines() == ["1"]

    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")
    dirty = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert dirty.returncode != 0
    assert "QG_PUBLISH_DIRTY" in dirty.stderr
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]

    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "new-head")
    third = _run(tmp_path, "bash", str(SCRIPT), env=env)
    assert "QG_PUBLISH_PROOF_WRITTEN" in third.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1", "1"]

    _write_executable(fake_bin / "uv", _fake_uv("0.13.0"))
    fourth = _run(tmp_path, "bash", str(SCRIPT), env=env)
    assert "QG_PUBLISH_PROOF_WRITTEN" in fourth.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1", "1", "1"]


def test_publication_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


@pytest.mark.parametrize(
    "token",
    [
        "QG_PUBLISH_BASE_STALE",
        "QG_PUBLISH_DIRTY",
        "QG_PUBLISH_PROOF_REUSED",
        "QG_PUBLISH_PROOF_WRITTEN",
        "uv run --no-sync pylint",
        "uv build",
    ],
)
def test_publication_script_keeps_required_contract(token: str) -> None:
    assert token in SCRIPT.read_text(encoding="utf-8")
