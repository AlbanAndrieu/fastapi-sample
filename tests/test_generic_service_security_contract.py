from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "generic-service"
VALUES = CHART / "values.yaml"
DEPLOYMENT = CHART / "templates" / "deployment.yaml"
BASE_DEPLOYMENT = CHART / "base" / "deployment.yaml"
NETWORK_POLICY = CHART / "templates" / "networkpolicy.yaml"
RESTRICTED_NAMESPACE = CHART / "examples" / "namespace-restricted.yaml"


def test_default_values_match_restricted_security_contract() -> None:
    values = yaml.safe_load(VALUES.read_text(encoding="utf-8"))

    assert values["podSecurityStandards"]["enforceRestricted"] is True
    assert values["podSecurityStandards"]["namespace"]["enforce"] == "restricted"
    assert values["podSecurityStandards"]["namespace"]["audit"] == "restricted"
    assert values["podSecurityStandards"]["namespace"]["warn"] == "restricted"

    assert values["serviceAccount"]["automount"] is False
    assert values["pod"]["automountServiceAccountToken"] is False
    assert values["pod"]["enableServiceLinks"] is False
    assert values["pod"]["hostNetwork"] is False
    assert values["pod"]["hostPID"] is False
    assert values["pod"]["hostIPC"] is False

    pod_security = values["podSecurityContext"]
    assert pod_security["runAsNonRoot"] is True
    assert pod_security["seccompProfile"]["type"] == "RuntimeDefault"

    container_security = values["securityContext"]
    assert container_security["privileged"] is False
    assert container_security["allowPrivilegeEscalation"] is False
    assert container_security["runAsNonRoot"] is True
    assert container_security["readOnlyRootFilesystem"] is True
    assert "ALL" in container_security["capabilities"]["drop"]

    assert values["service"]["type"] == "ClusterIP"
    assert values["ingress"]["enabled"] is False


def test_helm_template_fails_closed_when_restricted_controls_are_weakened() -> None:
    text = DEPLOYMENT.read_text(encoding="utf-8")

    for control in (
        "PSS Restricted: podSecurityContext.runAsNonRoot must be true",
        "PSS Restricted: pod seccompProfile.type must be RuntimeDefault",
        "PSS Restricted: privileged containers are forbidden",
        "PSS Restricted: allowPrivilegeEscalation must be false",
        "PSS Restricted: capabilities.drop must contain ALL",
        "PSS Restricted: hostNetwork must be false",
        "PSS Restricted: hostPID must be false",
        "PSS Restricted: hostIPC must be false",
        "Pod ServiceAccount token automount must be false",
        "ServiceAccount token automount must be false",
    ):
        assert control in text

    assert "automountServiceAccountToken:" in text
    assert "enableServiceLinks:" in text


def test_base_manifest_is_restricted_compatible() -> None:
    deployment = yaml.safe_load(BASE_DEPLOYMENT.read_text(encoding="utf-8"))
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    assert pod["hostNetwork"] is False
    assert pod["hostPID"] is False
    assert pod["hostIPC"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["securityContext"]["privileged"] is False
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert "ALL" in container["securityContext"]["capabilities"]["drop"]


def test_psa_bootstrap_is_explicit_and_network_policy_is_fail_closed() -> None:
    namespace = yaml.safe_load(RESTRICTED_NAMESPACE.read_text(encoding="utf-8"))
    labels = namespace["metadata"]["labels"]
    network_policy = NETWORK_POLICY.read_text(encoding="utf-8")

    assert namespace["kind"] == "Namespace"
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert labels["pod-security.kubernetes.io/audit"] == "restricted"
    assert labels["pod-security.kubernetes.io/warn"] == "restricted"

    assert not (CHART / "templates" / "namespace.yaml").exists()
    assert "kind: NetworkPolicy" in network_policy
    assert ".Values.networkPolicy.enabled" in network_policy
    assert ".Values.networkPolicy.ingress" in network_policy
    assert ".Values.networkPolicy.egress" in network_policy
