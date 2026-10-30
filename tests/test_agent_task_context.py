"""Dependency-free tests for the FastAPI local-first agent task router."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/agent-task-context.py"
spec = importlib.util.spec_from_file_location("fastapi_agent_context", SCRIPT)
router = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(router)


def call(repo: Path, *args: str) -> None:
    process = subprocess.run(
        ["git", *args], cwd=repo, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=6, check=False,
    )
    if process.returncode:
        raise AssertionError("synthetic git setup failed")


class RouterContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="fastapi-agent-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        call(self.repo, "init", "-q", "-b", "master")
        (self.repo / "README.md").write_text("initial\n", encoding="utf-8")
        call(self.repo, "add", "README.md")
        call(self.repo, "-c", "user.name=Offline Test",
             "-c", "user.email=test@example.invalid",
             "commit", "-qm", "baseline")
        call(self.repo, "switch", "-q", "-c", "fix/agent-ui")

    def test_infer_ui_only_and_one_narrow_check(self) -> None:
        path = self.repo / "nabla/api/assets/api-health-entry.js"
        path.parent.mkdir(parents=True)
        path.write_text("console.log('ui');\n", encoding="utf-8")
        with patch.object(router, "ROOT", self.repo):
            result = router.context("auto", 20)
        self.assertEqual(result["task"], "ui")
        self.assertEqual(result["firstCheck"], "just ui-quick")
        self.assertIn("local-first-quality", result["skills"])
        self.assertEqual(result["localGate"], "NOT_RUN")
        self.assertEqual(result["runtime"], "NOT_RUN")
        self.assertEqual(result["prState"], "NOT_CHECKED")

    def test_explicit_cloud_task_never_triggers_network(self) -> None:
        with patch.object(router, "ROOT", self.repo):
            with patch.object(router, "git", wraps=router.git) as mocked:
                result = router.context("cloud", 10)
        self.assertIn("fastapi-cloud", result["skills"])
        self.assertEqual(result["task"], "cloud")
        for call_args in mocked.call_args_list:
            command = call_args.args
            self.assertNotIn("fetch", command)
            self.assertNotIn("pull", command)
            self.assertNotIn("push", command)

    def test_truncated_paths_are_counted_not_misreported_as_full(self) -> None:
        for index in range(5):
            (self.repo / f"change-{index}.txt").write_text("x", encoding="utf-8")
        with patch.object(router, "ROOT", self.repo):
            result = router.context("quality", 2)
        self.assertEqual(result["changedCount"], 5)
        self.assertEqual(len(result["changedPaths"]), 2)
        self.assertEqual(result["omittedPaths"], 3)

    def test_original_secret_contents_not_printed(self) -> None:
        (self.repo / ".env.secrets").write_text("PRIVATE_CONTENT_NEVER_PRINT\n", encoding="utf-8")
        with patch.object(router, "ROOT", self.repo):
            with redirect_stdout(io.StringIO()) as stream:
                router.main(["--task", "ui", "--json"])
        self.assertNotIn("PRIVATE_CONTENT_NEVER_PRINT", stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())["firstCheck"], "just ui-quick")

    def test_unavailable_configured_base_has_no_fake_comparison(self) -> None:
        with patch.object(router, "ROOT", self.repo):
            with patch.dict(os.environ, {"QUALITY_BASE_REF": "refs/not-present"}):
                result = router.context("api", 3)
        self.assertEqual(result["baseState"], "NOT_RUN")
        self.assertEqual(result["prState"], "NOT_CHECKED")

    def test_unavailable_git_checkout_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="not-a-checkout-") as missing:
            with patch.object(router, "ROOT", Path(missing)):
                result = router.context("auto", 1)
        self.assertEqual(result["state"], "NOT_RUN")

    def test_invalid_path_cap_fails_without_reading_repo(self) -> None:
        with patch.dict(os.environ, {"AGENT_CONTEXT_MAX_PATHS": "0"}):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    router.main(["--json"])
        self.assertEqual(error.exception.code, 2)

    def test_explicit_quality_routing_not_confused_with_runtime(self) -> None:
        with patch.object(router, "ROOT", self.repo):
            result = router.context("quality", 2)
        self.assertEqual(result["firstCheck"], "just test-local-first")
        self.assertNotIn("homelab-runtime-status", result["skills"])


if __name__ == "__main__":
    unittest.main()
