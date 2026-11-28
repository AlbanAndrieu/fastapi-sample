"""Cloud cannot gain LAN fan-out merely by setting an environment switch."""

from nabla.api.homelab_health import internal_probes_enabled


def test_cloud_runtime_rejects_internal_probe_override(monkeypatch):
    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", "true")
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "cloud")
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "unit-cloud")
    assert internal_probes_enabled() is False


def test_homelab_runtime_accepts_opt_in(monkeypatch):
    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", "true")
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    monkeypatch.delenv("FASTAPICLOUD_DEPLOYMENT_ID", raising=False)
    assert internal_probes_enabled() is True
