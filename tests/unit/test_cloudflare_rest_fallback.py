"""Tests for the bounded Cloudflare REST observer fallback."""

from nabla.api import cloudflare_rest_fallback
from nabla.api.cloudflare_tunnels import CloudflareTunnelSettings


def _settings() -> CloudflareTunnelSettings:
    api_value = "-".join(("test", "value"))
    return CloudflareTunnelSettings(account_id="account", api_token=api_value)


def test_project_control_plane_filters_other_account_objects(monkeypatch) -> None:
    def fake_get(_settings, path):
        if path.endswith("/access/policies"):
            return {
                "success": True,
                "result": [
                    {
                        "id": "policy-fastapi",
                        "name": "fastapi-sample-monitor",
                        "decision": "non_identity",
                        "app_count": 1,
                    },
                    {
                        "id": "policy-other",
                        "name": "Everyone bypass",
                        "decision": "bypass",
                        "app_count": 50,
                    },
                ],
            }
        if path.endswith("/access/service_tokens"):
            return {
                "success": True,
                "result": [
                    {
                        "id": "token-fastapi",
                        "name": "fastapi-sample-monitor",
                        "enabled": True,
                    },
                    {
                        "id": "token-other",
                        "name": "n8n-internal-api",
                        "enabled": True,
                    },
                ],
            }
        raise AssertionError(path)

    monkeypatch.setattr(cloudflare_rest_fallback, "_get", fake_get)
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)

    result = cloudflare_rest_fallback.observe_project_access_control_plane_rest(
        _settings(),
    )

    assert result.reusable_policy_count == 1
    assert result.reusable_policy_total_count == 1
    assert result.reusable_policy_app_count == 1
    assert result.service_token_count == 1
    assert result.service_token_total_count == 1
    assert result.service_token_enabled_count == 1
    assert result.configured_service_token_present is True


def test_project_control_plane_names_are_overridable(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_PROJECT_ACCESS_POLICY_NAME", "custom-policy")
    monkeypatch.setenv("CLOUDFLARE_PROJECT_SERVICE_TOKEN_NAME", "custom-token")

    def fake_get(_settings, path):
        if path.endswith("/access/policies"):
            return {
                "success": True,
                "result": [{"id": "p1", "name": "custom-policy", "app_count": 2}],
            }
        return {
            "success": True,
            "result": [{"id": "t1", "name": "custom-token", "enabled": True}],
        }

    monkeypatch.setattr(cloudflare_rest_fallback, "_get", fake_get)

    result = cloudflare_rest_fallback.observe_project_access_control_plane_rest(
        _settings(),
    )

    assert result.reusable_policy_count == 1
    assert result.reusable_policy_app_count == 2
    assert result.service_token_count == 1


def test_tunnel_rest_filters_inactive_and_reads_remote_ingress(monkeypatch) -> None:
    def fake_get(_settings, path):
        if path.endswith("/cfd_tunnel"):
            return {
                "success": True,
                "result": [
                    {
                        "id": "dev",
                        "name": "nabla-albandrieu",
                        "status": "healthy",
                        "config_src": "cloudflare",
                    },
                    {
                        "id": "prod",
                        "name": "nabla-truescale",
                        "status": "healthy",
                        "config_src": "cloudflare",
                    },
                    {
                        "id": "old",
                        "name": "OVH - main",
                        "status": "inactive",
                        "config_src": "cloudflare",
                    },
                ],
            }
        tunnel_id = path.split("/")[-2]
        return {
            "success": True,
            "result": {
                "config": {
                    "ingress": [
                        {
                            "hostname": f"{tunnel_id}.example.com",
                            "service": "http://172.17.0.24:8080",
                        },
                        {"service": "http_status:404"},
                    ],
                },
            },
        }

    monkeypatch.setattr(cloudflare_rest_fallback, "_get", fake_get)

    tunnels, metadata = cloudflare_rest_fallback.observe_tunnels_rest(_settings())

    assert [tunnel.name for tunnel in tunnels] == [
        "nabla-albandrieu",
        "nabla-truescale",
    ]
    assert metadata["result_count"] == 2
    assert metadata["inactive_filtered"] == 1
    assert tunnels[0].ingress[0].hostname == "dev.example.com"
