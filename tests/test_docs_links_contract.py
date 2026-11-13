"""Offline contracts for active-document validation and archival policy."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_docs_links.py"
spec = importlib.util.spec_from_file_location("fastapi_docs_links", SCRIPT)
checker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(checker)


class DocsLinkContracts(unittest.TestCase):
    def test_active_mode_skips_archives_without_skipping_live_docs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docs-link-audit-") as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Root\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            (root / "docs/archive").mkdir(parents=True)
            (root / "docs/README.md").write_text("# Current\n", encoding="utf-8")
            (root / "docs/archive/old.md").write_text(
                "[old](missing.md)\n", encoding="utf-8"
            )
            active = checker.default_markdown_files(root, include_archives=False)
            all_files = checker.default_markdown_files(root)
            self.assertEqual(len(active), 3)
            self.assertEqual(len(all_files), 4)
            self.assertTrue(all(not checker.validate_markdown(path, root) for path in active))
            self.assertTrue(checker.validate_markdown(root / "docs/archive/old.md", root))

    def test_broken_live_doc_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docs-link-audit-") as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            source = root / "docs/readme.md"
            source.write_text("[broken](missing.md)\n", encoding="utf-8")
            self.assertEqual(len(checker.validate_markdown(source, root)), 1)


if __name__ == "__main__":
    unittest.main()
