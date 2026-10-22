"""Offline contracts for the opt-in, private Talos deployment manifest."""

from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[2] / "deploy/talos/fastapi-sample.yaml"


def _documents() -> dict[str, dict]:
    docs = list(yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")))
    return {doc["kind"]: doc for doc in docs}


def test_talos_deployment_is_internal_only() -> None:
    docs = _documents()
    assert set(docs) == {
        "Namespace", "ConfigMap", "Deployment", "Service", "NetworkPolicy",
    }
    service = docs["Service"]
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"][0]["port"] == 8080
    assert docs["Deployment"]["spec"]["replicas"] == 1
    network_policy = docs["NetworkPolicy"]["spec"]
    assert network_policy["policyTypes"] == ["Ingress"]
    assert network_policy["ingress"][0]["from"] == [{"podSelector": {}}]


def test_talos_pod_security_and_supply_chain() -> None:
    pod = _documents()["Deployment"]["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    container = pod["containers"][0]
    assert "@sha256:" in container["image"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["startupProbe"]["httpGet"]["path"] == "/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["resources"]["limits"]["memory"]


def test_talos_configuration_does_not_ship_secrets() -> None:
    docs = _documents()
    assert "Secret" not in docs
    env = docs["ConfigMap"]["data"]
    assert env["HOMELAB_TRUSTED_CIDRS"] == "82.66.4.247/32"
    assert env["OPS_ROUTE_POLICY_STRICT"] == "false"
    assert "DIAGNOSTICS_ACCESS_KEY" not in env
    assert "LITELLM_API_KEY" not in env
    pod_env = docs["Deployment"]["spec"]["template"]["spec"]["containers"][0][
        "envFrom"
    ]
    assert pod_env[1]["secretRef"]["name"] == "fastapi-sample-runtime-secrets"
