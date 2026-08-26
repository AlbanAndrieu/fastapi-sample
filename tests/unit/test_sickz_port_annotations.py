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
                    "https://home.albandrieu.com:10443/": {"reachable": False},
                    "https://172.17.0.1:10443/": {"reachable": False},
                    "http://172.17.0.1:8076/": {"reachable": True},
                },
                "reachable": True,
                "pfsense_tcp_ports": {"22": False, "3000": None, "4000": False, "8200": None},
                "pfsense_tcp_port_policy": {},
            }
        }
    }

    result = enrich_pfsense_port_annotations(payload)
    check = result["checks"]["pfsense"]

    assert check["pfsense_tcp_ports"]["10443"] is False
    assert check["pfsense_tcp_port_policy"]["10443"]["service"] == "pfSense"
    assert check["pfsense_tcp_port_policy"]["10443"]["expected_reachable"] is False


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
    assert all(policy[port]["expected_reachable"] is False for port in ("22", "3000", "4000", "8200", "10443"))
