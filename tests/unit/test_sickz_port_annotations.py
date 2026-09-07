"""Tests for pfSense TCP service labels and exposure expectations."""

from nabla.api.sickz_port_annotations import enrich_pfsense_port_annotations


def test_pfsense_10443_uses_https_alias_reachability() -> None:
    payload = {
        "checks": {
            "pfsense": {
                "name": "PfSense",
                "aliases_probed": [
                    "https://home.albandrieu.com:10443/",
                    "https://172.17.0.1:10443/",
                    "http://172.17.0.1:8076/",
                ],
                "alias_results": {
                    "https://home.albandrieu.com:10443/": {"reachable": True},
                    "https://172.17.0.1:10443/": {"reachable": False},
                    "http://172.17.0.1:8076/": {"reachable": True},
                },
                "reachable": True,
                "policy_status": "fail",
                "policy_detail": "legacy external=false verdict",
                "security_exception": "trusted-source exception",
                "pfsense_tcp_ports": {"22": False, "3000": None, "4000": False, "8200": None},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    result = enrich_pfsense_port_annotations(payload)
    check = result["checks"]["pfsense"]
    policy = check["pfsense_tcp_port_policy"]["10443"]

    assert check["pfsense_tcp_ports"]["10443"] is True
    assert policy["service"] == "pfSense Admin/API"
    assert policy["expected_reachable"] is False
    assert policy["access_policy"] == "trusted_sources_only"
    assert policy["default_action"] == "deny"
    assert policy["negative_probe_required"] is True
    assert check["policy_status"] == "fail"
    assert "not an approved administration source" in check["policy_detail"]
    assert "default-deny policy" in check["policy_detail"]
    assert "trusted-source exception" in check["policy_detail"]


def test_pfsense_10443_unreachable_cloud_probe_is_policy_ok() -> None:
    payload = {
        "checks": {
            "pfsense": {
                "name": "pfSense",
                "aliases_probed": ["https://home.albandrieu.com:10443/"],
                "alias_results": {
                    "https://home.albandrieu.com:10443/": {"reachable": False},
                },
                "reachable": False,
                "pfsense_tcp_ports": {},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    check = enrich_pfsense_port_annotations(payload)["checks"]["pfsense"]

    assert check["pfsense_tcp_ports"]["10443"] is False
    assert check["policy_status"] == "ok"
    assert "blocked from FastAPI Cloud as intended" in check["policy_detail"]
    assert "out-of-band observer" in check["policy_detail"]



def test_pfsense_10443_private_lan_reachability_is_ok_for_local_runtime() -> None:
    payload = {
        "checks": {
            "pfsense": {
                "name": "pfSense",
                "aliases_probed": [
                    "https://home.albandrieu.com:10443/",
                    "https://172.17.0.1:10443/",
                ],
                "alias_results": {
                    "https://home.albandrieu.com:10443/": {"reachable": True},
                    "https://172.17.0.1:10443/": {"reachable": True},
                },
                "reachable": True,
                "pfsense_tcp_ports": {},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    check = enrich_pfsense_port_annotations(
        payload,
        runtime_scope="local",
    )["checks"]["pfsense"]
    policy = check["pfsense_tcp_port_policy"]["10443"]

    assert check["policy_status"] == "ok"
    assert "private LAN address" in check["policy_detail"]
    assert "does not prove WAN exposure" in check["policy_detail"]
    assert policy["observer_scope"] == "local"
    assert policy["expected_reachable"] is True
    assert policy["negative_probe_required"] is False
    assert policy["direct_probe_semantics"] == "trusted_lan_control_check"
    assert policy["recommended_control_path"] == "direct_lan"


def test_pfsense_10443_public_only_local_reachability_is_warning() -> None:
    payload = {
        "checks": {
            "pfsense": {
                "name": "pfSense",
                "aliases_probed": [
                    "https://home.albandrieu.com:10443/",
                    "https://172.17.0.1:10443/",
                ],
                "alias_results": {
                    "https://home.albandrieu.com:10443/": {"reachable": True},
                    "https://172.17.0.1:10443/": {"reachable": False},
                },
                "reachable": True,
                "pfsense_tcp_ports": {},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    check = enrich_pfsense_port_annotations(
        payload,
        runtime_scope="local",
    )["checks"]["pfsense"]

    assert check["policy_status"] == "warn"
    assert "no private 10443 alias probe succeeded" in check["policy_detail"]
    assert "independent external negative exposure probe" in check["policy_detail"]


def test_pfsense_10443_private_lan_reachability_is_ok_for_homelab_runtime() -> None:
    payload = {
        "checks": {
            "pfsense": {
                "name": "pfSense",
                "aliases_probed": ["https://172.17.0.1:10443/"],
                "alias_results": {
                    "https://172.17.0.1:10443/": {"reachable": True},
                },
                "reachable": True,
                "pfsense_tcp_ports": {},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    check = enrich_pfsense_port_annotations(
        payload,
        runtime_scope="homelab",
    )["checks"]["pfsense"]

    assert check["policy_status"] == "ok"
    assert "trusted homelab observer" in check["policy_detail"]
    assert check["pfsense_tcp_port_policy"]["10443"]["observer_scope"] == "homelab"

def test_named_tcp_services_keep_expected_blocked_policy() -> None:
    payload = {
        "checks": {
            "pfsense": {
                "display_label": "PfSense",
                "reachable": False,
                "pfsense_tcp_ports": {},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    check = enrich_pfsense_port_annotations(payload)["checks"]["pfsense"]
    policy = check["pfsense_tcp_port_policy"]

    assert policy["22"]["service"] == "SSH"
    assert policy["3000"]["service"] == "ntopng"
    assert policy["4000"]["service"] == "LiteLLM"
    assert policy["8200"]["service"] == "Vault"
    assert all(
        policy[port]["expected_reachable"] is False
        for port in ("22", "3000", "4000", "8200")
    )
    assert policy["10443"]["expected_reachable"] is False
    assert policy["10443"]["access_policy"] == "trusted_sources_only"
    assert policy["10443"]["direct_probe_semantics"] == "negative_exposure_check"
    assert policy["10443"]["recommended_control_path"] == "out_of_band"
