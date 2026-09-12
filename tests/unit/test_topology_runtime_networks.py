"""Contracts for canonical Docker network memberships in the topology API."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from nabla.api.homelab_topology import HomelabTopologyRuntime


ASSETS = Path("nabla/api/assets")


def test_runtime_serializes_all_canonical_network_memberships() -> None:
    runtime = HomelabTopologyRuntime.model_validate(
        {
            "provider": "truenas-app",
            "containerService": "fastapi-sample",
            "networks": ["intranet", "sample-observer", "traefik_network"],
        }
    )

    assert runtime.networks == ["intranet", "sample-observer", "traefik_network"]
    assert runtime.model_dump(by_alias=True)["networks"] == [
        "intranet",
        "sample-observer",
        "traefik_network",
    ]


def test_runtime_rejects_duplicate_network_memberships() -> None:
    with pytest.raises(ValidationError, match="runtime.networks must not contain duplicates"):
        HomelabTopologyRuntime.model_validate(
            {
                "provider": "truenas-app",
                "containerService": "fastapi-sample",
                "networks": ["intranet", "intranet"],
            }
        )


def test_docker_network_grouping_preserves_multi_network_membership() -> None:
    javascript = (ASSETS / "api-topology-operator.js").read_text(encoding="utf-8")

    assert 'return networks.length > 0 ? networks.join(" + ") : "";' in javascript
    assert "multi-network services are never assigned to an arbitrary first network" in javascript
    assert "runtime.networks" in javascript
