"""Native parser contracts, private receipt and fixed GitHub provider scope."""

import importlib.util
import json
from pathlib import Path

import pytest

def load_script(file: str):
    path = Path(__file__).resolve().parents[2] / "scripts/security" / file
    spec = importlib.util.spec_from_file_location(file.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_zap_uses_native_xml_and_expected_cloud_origin():
    dojo = load_script("import_defectdojo.py")
    data = b'<OWASPZAPReport><site name="https://fastapi-sample.fastapicloud.dev"><alerts/></site></OWASPZAPReport>'
    dojo.validate_format("zap", data)
    assert dojo.REPORTS["zap"] == ("fastapi-sample/zap.xml", "ZAP Scan")
    for unsafe in (
        b'{"site":[]}',
        data.replace(b"fastapi-sample.fastapicloud.dev", b"other.invalid"),
        data.replace(b"<alerts/>", b"<requestheader>private</requestheader>"),
        b'<!DOCTYPE x [<!ENTITY x "a">]>' + data,
    ):
        with pytest.raises(ValueError):
            dojo.validate_format("zap", unsafe)


def test_prowler_native_ocsf_and_provider_boundary():
    dojo = load_script("import_defectdojo.py")
    finding = {"cloud": {"provider": "github"}, "finding_info": {}, "message": "fixture", "status_code": "FAIL"}
    assert dojo.validate_prowler(json.dumps([finding]).encode()) == 1
    assert dojo.REPORTS["prowler"] == ("prowler-github.json", "Prowler Scan")
    for unsafe in ([], [dict(finding, cloud={"provider": "aws"})], [dict(finding, status_code="unknown")]):
        with pytest.raises(ValueError):
            dojo.validate_prowler(json.dumps(unsafe).encode())


def test_prowler_runner_is_explicitly_repo_scoped_and_private():
    source = (Path(__file__).resolve().parents[2] / "scripts/security/run_prowler_github.py").read_text()
    assert 'REPO = "AlbanAndrieu/fastapi-sample"' in source
    assert '"github", "--repository", REPO, "--output-formats", "json-ocsf"' in source
    assert '"refs/remotes/origin/master"' in source
    assert 'os.umask(0o077)' in source
    assert 'stdout=subprocess.DEVNULL' in source
    assert '"--ignore-exit-code-3"' not in source
