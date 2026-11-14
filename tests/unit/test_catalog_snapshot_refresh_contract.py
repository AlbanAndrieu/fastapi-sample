"""Offline, fail-closed tests for the canonical Backstage V2 snapshot refresh."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/refresh-catalog-snapshot.sh"


def _source(tmp_path: Path, *, valid: bool) -> Path:
    entity = {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "entityRef": "component:default/test",
        "metadata": {"name": "test"},
        "spec": {"type": "service"},
        "sourcePath": "apps/test/catalog-info.yaml",
    }
    digest = hashlib.sha256(
        json.dumps([entity], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payload = {
        "schemaVersion": 2,
        "model": "backstage",
        "catalogRevision": "sha256:" + (digest if valid else "0" * 64),
        "entities": [entity],
    }
    path = tmp_path / ("valid.json" if valid else "invalid.json")
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def test_refresh_is_atomic_verifies_digest_and_skips_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    target = repo / "nabla/api/data/catalog-snapshot.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"old":true}\n', encoding="utf-8")
    script = repo / "scripts/refresh-catalog-snapshot.sh"
    shutil.copyfile(SCRIPT, script)

    invalid = _source(tmp_path, valid=False)
    failed = subprocess.run(["bash", str(script), str(invalid)], capture_output=True, text=True, check=False)
    assert failed.returncode != 0
    assert target.read_text(encoding="utf-8") == '{"old":true}\n'
    assert not list(target.parent.glob("catalog-snapshot.json.tmp.*"))

    valid = _source(tmp_path, valid=True)
    changed = subprocess.run(["bash", str(script), str(valid)], capture_output=True, text=True, check=False)
    assert changed.returncode == 0, changed.stderr
    assert target.read_bytes() == valid.read_bytes()
    before = target.stat().st_mtime_ns
    unchanged = subprocess.run(["bash", str(script), str(valid)], capture_output=True, text=True, check=False)
    assert unchanged.returncode == 0, unchanged.stderr
    assert "already current" in unchanged.stdout
    assert target.stat().st_mtime_ns == before
