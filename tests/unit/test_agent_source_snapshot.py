"""Offline acceptance for the exact-Git-commit source materializer."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "scripts" / "agent-source-snapshot.sh"


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_snapshot_uses_committed_tree_not_dirty_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    file = repo / "value.txt"
    file.write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "value.txt")
    _git(
        repo, "-c", "user.name=Test", "-c", "user.email=test@example.test",
        "commit", "-qm", "fixture",
    )
    head = _git(repo, "rev-parse", "HEAD")
    file.write_text("uncommitted\n", encoding="utf-8")
    destination = tmp_path / "snapshot"
    result = subprocess.run(
        ["bash", str(SNAPSHOT), str(repo), head, str(destination)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (destination / "value.txt").read_text(encoding="utf-8") == "committed\n"
    assert _git(destination, "rev-parse", "HEAD") == head
    assert _git(destination, "status", "--porcelain") == ""

    repeated = subprocess.run(
        ["bash", str(SNAPSHOT), str(repo), head, str(destination)],
        capture_output=True, text=True, check=False,
    )
    assert repeated.returncode == 2
    assert "refusing to overwrite" in repeated.stderr


def test_snapshot_rejects_invalid_or_uncached_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for value, expected in [("master", 2), ("a" * 40, 1)]:
        result = subprocess.run(
            ["bash", str(SNAPSHOT), str(repo), value, str(tmp_path / "output")],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == expected
        assert not (tmp_path / "output").exists()


def test_snapshot_historical_commit_with_spaces_and_symlink_guard(tmp_path: Path) -> None:
    """Offline clone uses the requested commit, and refuses symlink destinations."""
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.test")
    file = repo / "value.txt"
    file.write_text("first\n", encoding="utf-8")
    _git(repo, "add", "value.txt")
    _git(repo, "commit", "-qm", "first")
    old_head = _git(repo, "rev-parse", "HEAD")
    file.write_text("second\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "second")

    destination = tmp_path / "snapshot with spaces"
    result = subprocess.run(
        ["bash", str(SNAPSHOT), str(repo), old_head, str(destination)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert _git(destination, "rev-parse", "HEAD") == old_head
    assert (destination / "value.txt").read_text(encoding="utf-8") == "first\n"

    symlink = tmp_path / "symlink-destination"
    symlink.symlink_to(destination, target_is_directory=True)
    rejected = subprocess.run(
        ["bash", str(SNAPSHOT), str(repo), old_head, str(symlink)],
        capture_output=True, text=True, check=False,
    )
    assert rejected.returncode == 2
    assert "refusing to overwrite" in rejected.stderr


def test_snapshot_prevents_destination_nesting_on_late_creation() -> None:
    """The final move must refuse an occupied destination, not nest within it."""
    script = SNAPSHOT.read_text(encoding="utf-8")
    assert 'destination appeared during snapshot creation' in script
    assert 'mv -T -- "$staging" "$destination"' in script
    assert script.index('destination appeared during snapshot creation') < script.index(
        'mv -T -- "$staging" "$destination"'
    )


def test_snapshot_rejects_destination_created_mid_checkout(tmp_path: Path) -> None:
    """Inject late directory creation and verify no nested checkout is published."""
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "file.txt").write_text("committed", encoding="utf-8")
    _git(repo, "add", ".")
    _git(
        repo, "-c", "user.name=Test", "-c", "user.email=test@example.test",
        "commit", "-qm", "fixture",
    )
    sha = _git(repo, "rev-parse", "HEAD")
    destination = tmp_path / "late-destination"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_path = shutil.which("git")
    assert git_path is not None
    wrapper = bin_dir / "git"
    wrapper.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "$*" == *"rev-parse HEAD"* && '
        '"$*" == *".source-snapshot."* ]]; then\n'
        '  mkdir -p "$RACE_DEST"\n'
        'fi\n'
        f'exec "{git_path}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "RACE_DEST": str(destination),
    }
    result = subprocess.run(
        ["bash", str(SNAPSHOT), str(repo), sha, str(destination)],
        capture_output=True, text=True, env=env, check=False,
    )
    assert result.returncode == 2
    assert "destination appeared during snapshot creation" in result.stderr
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
