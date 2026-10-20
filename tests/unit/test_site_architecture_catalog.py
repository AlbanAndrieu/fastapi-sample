"""Backend v2 Backstage contract and source-only no-fallback regression tests."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from nabla.api import site_architecture_catalog as v2


def raw_fixture() -> dict:
    entities = [
        {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Resource",
            "entityRef": "resource:default/database",
            "sourcePath": "apps/database/catalog-info.yaml",
            "metadata": {
                "name": "database",
                "title": "Database",
                "annotations": {"internalHost": "172.17.0.24", "secret": "NEVER_EXPOSE"},
                "labels": {"albandrieu.com/business-criticality": "high", "token": "NEVER_EXPOSE"},
                "tags": ["data", "nist-protect"],
                "description": "Private internal path 172.17.0.24:5432",
            },
            "spec": {"type": "database", "owner": "group:default/nabla-platform"},
        },
        {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Group",
            "entityRef": "group:default/nabla-platform",
            "sourcePath": "catalog/catalog-info.yaml",
            "metadata": {"name": "nabla-platform"},
            "spec": {"type": "team"},
        },
        {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "entityRef": "component:default/api",
            "sourcePath": "apps/api/catalog-info.yaml",
            "metadata": {
                "name": "api",
                "title": "API",
                "tags": ["security", "nist-detect"],
                "labels": {"albandrieu.com/operational-criticality": "high"},
            },
            "spec": {
                "type": "service",
                "lifecycle": "production",
                "dependsOn": ["resource:default/database"],
                "owner": "group:default/nabla-platform",
                "originUrl": "http://172.17.0.24:8091",
            },
        },
    ]
    digest = hashlib.sha256(
        json.dumps(
            sorted(entities, key=lambda e: e["entityRef"]),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return {"schemaVersion": 2, "model": "backstage", "catalogRevision": "sha256:" + digest, "entities": entities}


def test_projection_keeps_v2_identity_revision_and_relations_without_private_fields() -> None:
    payload = raw_fixture()
    model = v2.project_site_catalog_v2(payload)
    wire = model.model_dump(mode="json", exclude_none=True)
    assert wire["schemaVersion"] == 2
    assert wire["model"] == "backstage"
    assert wire["catalogRevision"] == payload["catalogRevision"]
    assert len(wire["entities"]) == 3
    api = next(e for e in wire["entities"] if e["entityRef"] == "component:default/api")
    assert api["spec"]["dependsOn"] == ["resource:default/database"]
    assert api["spec"]["owner"] == "group:default/nabla-platform"
    assert api["kind"] == "Component"
    assert api["sourcePath"] == "apps/api/catalog-info.yaml"
    assert api["metadata"]["labels"] == {"albandrieu.com/operational-criticality": "high"}
    assert api["metadata"]["tags"] == ["security", "nist-detect"]
    serialized = json.dumps(wire)
    for forbidden in ("172.17.0.24", "NEVER_EXPOSE", "originUrl", "internalHost", "5432"):
        assert forbidden not in serialized
    assert "services" not in wire
    assert "version" not in wire


def test_revision_and_edges_fail_closed() -> None:
    raw = raw_fixture()
    raw["catalogRevision"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="revision mismatch"):
        v2.project_site_catalog_v2(raw)

    raw = raw_fixture()
    raw["entities"][2]["spec"]["dependsOn"] = ["resource:default/unknown"]
    raw["catalogRevision"] = "sha256:" + hashlib.sha256(
        json.dumps(
            sorted(raw["entities"], key=lambda e: e["entityRef"]),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="unresolved"):
        v2.project_site_catalog_v2(raw)


def test_no_v1_translation_or_extra_wire_fields() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        v2.project_site_catalog_v2({"version": 1, "services": [{"id": "api", "name": "API"}]})
    with pytest.raises(ValidationError):
        v2.SiteArchitectureCatalogV2.model_validate(
            {
                "schemaVersion": 2,
                "model": "backstage",
                "catalogRevision": "sha256:" + "a" * 64,
                "entities": [],
                "services": [],
            }
        )


def test_source_url_is_pinned_to_nabla_compose_https() -> None:
    assert v2._validated_source_url(v2._SOURCE_URL) == v2._SOURCE_URL
    for unsafe in (
        "http://127.0.0.1/a",
        "https://evil.invalid/entities.json",
        "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/generated/entities.json?bad=1",
    ):
        with pytest.raises(ValueError):
            v2._validated_source_url(unsafe)


@pytest.mark.asyncio
async def test_no_packaged_or_expired_cache_fallback(monkeypatch) -> None:
    v2.reset_site_catalog_v2_cache()
    fetch = AsyncMock(side_effect=httpx.ConnectError("offline"))
    monkeypatch.setattr(v2, "_download_site_catalog_v2", fetch)
    with pytest.raises(v2.SiteCatalogV2Unavailable):
        await v2.fetch_site_catalog_v2()
    assert fetch.await_count == 1
    v2.reset_site_catalog_v2_cache()


@pytest.mark.asyncio
async def test_verified_v2_cache_expires_and_then_fails(monkeypatch) -> None:
    v2.reset_site_catalog_v2_cache()
    expected = v2.project_site_catalog_v2(raw_fixture())
    fetch = AsyncMock(return_value=expected)
    monkeypatch.setattr(v2, "_download_site_catalog_v2", fetch)
    assert await v2.fetch_site_catalog_v2() is expected
    assert await v2.fetch_site_catalog_v2() is expected
    assert fetch.await_count == 1
    assert v2._cache is not None
    v2._cache = (0.0, expected)
    fetch.side_effect = httpx.ConnectError("offline")
    with pytest.raises(v2.SiteCatalogV2Unavailable):
        await v2.fetch_site_catalog_v2()
    assert fetch.await_count == 2
    v2.reset_site_catalog_v2_cache()
