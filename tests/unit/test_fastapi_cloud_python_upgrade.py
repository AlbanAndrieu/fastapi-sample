"""No-network contracts for the FastAPI Cloud Python major-version canary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/check_fastapi_cloud_python_upgrade.py"
spec = importlib.util.spec_from_file_location("cloud_python_upgrade", SCRIPT)
assert spec is not None and spec.loader is not None
cloud_upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_upgrade)


def test_active_runtime_is_explicitly_pinned_to_313() -> None:
    report = cloud_upgrade.audit(ROOT, "3.14.9")
    assert report["status"] == "BLOCKED_PENDING_RESOLUTION"
    assert report["locked_requires_python"] == "==3.13.*"
    assert report["current_requires_python"] == "==3.13.*"
    assert report["lock_packages"] > 100
    assert report["packages_with_cp313_wheels"] > 0


def test_315_candidate_is_not_misrepresented_as_compatible() -> None:
    report = cloud_upgrade.audit(ROOT, "3.15.1")
    assert report["candidate"] == "3.15.1"
    assert report["status"] == "BLOCKED_PENDING_RESOLUTION"


def test_canary_fails_if_lock_disagrees_with_manifest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nrequires-python = "==3.13.*"\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        'requires-python = "==3.14.*"\n', encoding="utf-8",
    )
    (tmp_path / ".python-version").write_text("3.13.17\n", encoding="utf-8")
    with pytest.raises(ValueError, match="disagree"):
        cloud_upgrade.audit(tmp_path, "3.14.9")


def test_probe_uses_disposable_copy_and_offline_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    probe_evidence = tmp_path / "evidence.json"
    uv_stub = bin_dir / "uv"
    uv_stub.write_text(
        '#!/usr/bin/env python3\n'
        'import json, os, pathlib, sys\n'
        'data = {\n'
        '  "argv": sys.argv[1:],\n'
        '  "project": pathlib.Path("pyproject.toml").read_text(),\n'
        '  "offline": os.getenv("UV_OFFLINE"),\n'
        '}\n'
        'pathlib.Path(os.environ["EVIDENCE_FILE"]).write_text(json.dumps(data))\n',
        encoding="utf-8",
    )
    uv_stub.chmod(0o700)
    monkeypatch.setenv("PATH", str(bin_dir) + ":" + __import__("os").environ["PATH"])
    monkeypatch.setenv("EVIDENCE_FILE", str(probe_evidence))
    current_project = (ROOT / "pyproject.toml").read_bytes()
    current_lock = (ROOT / "uv.lock").read_bytes()
    result = cloud_upgrade.probe(ROOT, "3.14.9", allow_network=False)
    assert result["status"] == "RESOLVER_PASSED_NOT_DEPLOYABLE"
    evidence = json.loads(probe_evidence.read_text(encoding="utf-8"))
    assert evidence["argv"] == ["lock", "--dry-run"]
    assert evidence["offline"] == "1"
    assert 'requires-python = "==3.14.*"' in evidence["project"]
    assert (ROOT / "pyproject.toml").read_bytes() == current_project
    assert (ROOT / "uv.lock").read_bytes() == current_lock
