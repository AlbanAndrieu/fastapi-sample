"""Behavioral tests for the local publication-proof cache."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent-publish.sh"


def _run(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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


def _fixture_env(fake_bin: Path, **extra: str) -> dict[str, str]:
    """Use the mocked toolchain, never the invoking `uv run pytest` environment."""
    excluded = {
        "QUALITY_BASE_REF",
        "BASH_ENV",
        "ENV",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "UV_PROJECT_ENVIRONMENT",
    }
    env = {key: value for key, value in os.environ.items() if key not in excluded and not key.startswith("BASH_FUNC_")}
    # Inherit neither a project venv/bin/uv nor a shell initialization
    # hook which can replace the mock with real uv. Keep Python and git
    # explicitly available so the isolated ci_scope fixture still runs.
    executable_dirs = (
        fake_bin,
        Path(sys.executable).parent,
        Path(shutil.which("git") or "/usr/bin/git").parent,
        Path(shutil.which("bash") or "/usr/bin/bash").parent,
        Path("/usr/bin"),
        Path("/bin"),
    )
    env["PATH"] = os.pathsep.join(dict.fromkeys(map(str, executable_dirs)))
    env.update(extra)
    return env


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


def test_publication_fixture_uses_only_its_mocked_uv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent accidental real Pylint/build invocations from a nested gate."""
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", _fake_uv("0.12.1"))
    # A parent shell's inherited startup hook must never supersede the mock.
    bash_env = tmp_path / "inherited-bash-env"
    bash_env.write_text("uv() { return 30; }\n", encoding="utf-8")
    monkeypatch.setenv("BASH_ENV", str(bash_env))
    monkeypatch.setenv("VIRTUAL_ENV", "/unexpected/outer/.venv")
    monkeypatch.setenv("PATH", "/unexpected/outer/.venv/bin:" + os.environ["PATH"])

    env = _fixture_env(fake_bin)
    completed = subprocess.run(
        ["bash", "-c", "command -v uv; uv --version"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == [str(fake_bin / "uv"), "uv 0.12.1"]
    assert "BASH_ENV" not in env
    assert "VIRTUAL_ENV" not in env


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
    (scripts / "ci-scope.sh").write_text(
        (ROOT / "scripts" / "ci-scope.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (scripts / "ci_scope.py").write_text(
        (ROOT / "scripts" / "ci_scope.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _git(
        tmp_path,
        "add",
        "scripts/agent-quality-gate.sh",
        "scripts/ci-scope.sh",
        "scripts/ci_scope.py",
        "uv.lock",
        "server_app.py",
    )
    _git(tmp_path, "commit", "-m", "head")

    fake_bin = tmp_path / ".git" / "fake-bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", _fake_uv("0.12.1"))

    env = _fixture_env(
        fake_bin,
        QUALITY_TEST_COUNTER=str(counter),
        QUALITY_TEST_BUILD_COUNTER=str(build_counter),
    )

    first = _run(tmp_path, "bash", str(SCRIPT), env=env)
    assert "QG_PUBLISH_PROOF_WRITTEN" in first.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]
    assert build_counter.read_text(encoding="utf-8").splitlines() == ["1"]

    second = _run(tmp_path, "bash", str(SCRIPT), env=env)
    assert "QG_PUBLISH_PROOF_REUSED" in second.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]
    assert build_counter.read_text(encoding="utf-8").splitlines() == ["1"]

    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")
    bash = shutil.which("bash")
    assert bash is not None
    dirty = subprocess.run(
        [bash, str(SCRIPT)],
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


def test_docs_only_publication_skips_application_build(tmp_path: Path) -> None:
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
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "quality.md").write_text("docs only\n", encoding="utf-8")
    _git(tmp_path, "add", "scripts/agent-quality-gate.sh", "docs/quality.md")
    _git(tmp_path, "commit", "-m", "docs")

    fake_bin = tmp_path / ".git" / "fake-bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", _fake_uv("0.12.1"))
    env = _fixture_env(
        fake_bin,
        QUALITY_TEST_COUNTER=str(counter),
        QUALITY_TEST_BUILD_COUNTER=str(build_counter),
    )

    result = _run(tmp_path, "bash", str(SCRIPT), env=env)

    assert "QG_PUBLISH_BUILD_SKIPPED" in result.stdout
    assert "build=false" in result.stdout
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]
    assert not build_counter.exists()


def test_publication_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


@pytest.mark.parametrize(
    "token",
    [
        "QG_PUBLISH_BASE_STALE",
        "QG_PUBLISH_DIRTY",
        "QG_PUBLISH_PROOF_REUSED",
        "QG_PUBLISH_PROOF_WRITTEN",
        "QG_PUBLISH_BUILD_SKIPPED",
        "QG_PUBLISH_SCOPE_INVALID",
        "uv run --no-sync pylint",
        "uv build",
    ],
)
def test_publication_script_keeps_required_contract(token: str) -> None:
    assert token in SCRIPT.read_text(encoding="utf-8")


def _resolve_shared_base(
    cwd: Path,
    *,
    configured: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Source the same Bash helper used by all three gates in an isolated repo."""
    helper = ROOT / "scripts/ci/quality-git.sh"
    env = {**os.environ}
    env.pop("QUALITY_BASE_REF", None)
    if configured is not None:
        env["QUALITY_BASE_REF"] = configured
    return subprocess.run(
        ["bash", "-c", 'source "$1"; quality_resolve_base_ref', "_", str(helper)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_shared_base_resolution_prioritizes_default_remote_and_override(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "quality@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Proof")
    (tmp_path / "README.md").write_text("first\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "first")
    first = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "README.md").write_text("second\n", encoding="utf-8")
    _git(tmp_path, "commit", "-am", "second")
    second = _git(tmp_path, "rev-parse", "HEAD")

    fallback = _resolve_shared_base(tmp_path)
    assert fallback.returncode == 0
    assert fallback.stdout.strip() == "HEAD~1"

    _git(tmp_path, "update-ref", "refs/remotes/origin/master", first)
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", second)
    default_master = _resolve_shared_base(tmp_path)
    assert default_master.returncode == 0
    assert default_master.stdout.strip() == "origin/master"

    _git(
        tmp_path,
        "symbolic-ref",
        "refs/remotes/origin/HEAD",
        "refs/remotes/origin/main",
    )
    declared = _resolve_shared_base(tmp_path)
    assert declared.returncode == 0
    assert declared.stdout.strip() == "origin/main"

    _git(tmp_path, "checkout", "--detach", second)
    detached = _resolve_shared_base(tmp_path)
    assert detached.returncode == 0
    assert detached.stdout.strip() == "origin/main"

    override = _resolve_shared_base(tmp_path, configured=first)
    assert override.returncode == 0
    assert override.stdout.strip() == first


def test_shared_base_rejects_invalid_explicit_reference(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "quality@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Proof")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "base")

    result = _resolve_shared_base(tmp_path, configured="origin/missing")
    assert result.returncode == 2
    assert "QG_BASE_MISSING" in result.stderr
    assert result.stdout == ""


def test_three_quality_entrypoints_use_one_reference_policy() -> None:
    helper = ROOT / "scripts/ci/quality-git.sh"
    assert helper.is_file()
    assert "quality_resolve_base_ref()" in helper.read_text(encoding="utf-8")
    for name in ("agent-publish.sh", "agent-quality-gate.sh", "quality-gate.sh"):
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "quality-git.sh" in script
        assert 'BASE_REF="$(quality_resolve_base_ref)"' in script
        assert "resolve_base_ref() {" not in script
