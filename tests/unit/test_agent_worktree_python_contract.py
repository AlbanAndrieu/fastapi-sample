"""Hermetic Bash/uv worktree safety tests; no internet or install."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/agent-worktree-python.sh"


class WorktreePythonContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts/agent-worktree-python.sh")
        (self.root / "pyproject.toml").write_text("requires-python = '==3.13.*'")
        (self.root / "uv.lock").write_text("fixture")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.trace = self.root / "trace"
        uv = self.bin / "uv"
        uv.write_text('''#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == sync && "$2" == --locked && "$3" == --python && "$4" == 3.13.17 ]]
[[ "$UV_PROJECT_ENVIRONMENT" == "$MOCK_ROOT/.venv" ]]
[[ "$UV_PYTHON_DOWNLOADS" == never && -z "${VIRTUAL_ENV:-}" ]]
printf 'sync\\n' >> "$MOCK_TRACE"
mkdir -p .venv/bin
printf '#!/bin/sh\\nexit 0\\n' > .venv/bin/python
chmod +x .venv/bin/python
''')
        uv.chmod(0o700)

    def run_command(self, arg="--check"):
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                   MOCK_ROOT=str(self.root), MOCK_TRACE=str(self.trace),
                   VIRTUAL_ENV="/wrong/global/.venv")
        return subprocess.run(["bash", str(self.root / "scripts/agent-worktree-python.sh"), arg],
                              env=env, cwd="/", capture_output=True, text=True)

    def test_check_does_not_install(self):
        result = self.run_command()
        self.assertEqual(result.returncode, 3)
        self.assertFalse(self.trace.exists())

    def test_sync_pins_python_and_worktree(self):
        result = self.run_command("--sync")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trace.read_text().splitlines(), ["sync"])

    def test_symlinked_venv_rejected_before_install(self):
        target = self.root / "protected"
        target.mkdir()
        (self.root / ".venv").symlink_to(target)
        self.assertEqual(self.run_command("--sync").returncode, 3)
        self.assertFalse(self.trace.exists())

    def test_parent_shell_survives_source_failure(self):
        result = subprocess.run(["bash", "-c", 'source "$1" || :; echo PARENT_ALIVE',
                                 "test", str(self.root / "scripts/agent-worktree-python.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PARENT_ALIVE", result.stdout)

    def test_help_is_not_mutating(self):
        self.assertEqual(self.run_command("--help").returncode, 0)
        self.assertFalse(self.trace.exists())


if __name__ == "__main__":
    unittest.main()
