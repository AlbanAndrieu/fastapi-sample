"""Post-deploy edge smoke never validates the retired pfSense appliance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "master-smoke.yml"


def test_retired_pfsense_ignored_without_false_green() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '.checks.pfsense.credential_mode == "disabled"' in text
    assert ".checks.pfsense.skipped == true" in text
    assert ".checks.pfsense.reachable == null" in text
    assert ".checks.pfsense.api_authenticated == true" not in text


def test_cloud_freebox_vantage_is_not_mistaken_for_a_lan_check() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert ".checks.freebox.skipped == true" in text
    assert '.checks.freebox.vantage_point == "fastapi_cloud"' in text
    assert ".checks.freebox.status_confirmed == false" in text
    assert "FREEBOX_APP_TOKEN" not in text
