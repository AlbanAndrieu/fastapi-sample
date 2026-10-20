"""No privileged catalog attributes can enter the public DTO."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from nabla.api.public_homelab_dto import PublicHomelabV1, load_public_homelab_v1


def test_empty_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLIC_HOMELAB_V1_SERVICES_JSON", raising=False)
    assert load_public_homelab_v1().model_dump(mode="json") == {
        "version": 1,
        "services": [],
    }


def test_explicit_allowlist_contains_only_public_display_fields() -> None:
    entry = {"id": "garage-webui", "label": "Garage UI", "category": "storage"}
    result = load_public_homelab_v1(json.dumps([entry])).model_dump(mode="json")
    assert result == {"version": 1, "services": [entry]}
    assert set(result["services"][0]) == {"id", "label", "category"}


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "garage", "label": "Garage", "category": "storage", "port": 3900},
        {"id": "garage", "label": "172.17.0.24", "category": "storage"},
        {"id": "garage", "label": "https://internal", "category": "storage"},
        {"id": "garage", "label": "Garage", "category": "other", "internalHost": "secret"},
        {"id": "garage", "label": "Garage", "category": "unknown"},
    ],
)
def test_secrets_and_extra_metadata_rejected(entry: dict[str, object]) -> None:
    with pytest.raises(RuntimeError, match="invalid public homelab"):
        load_public_homelab_v1(json.dumps([entry]))


def test_duplicate_ids_and_oversized_config_are_rejected() -> None:
    entry = {"id": "garage", "label": "Garage", "category": "storage"}
    with pytest.raises(RuntimeError, match="invalid public homelab"):
        load_public_homelab_v1(json.dumps([entry, entry]))
    with pytest.raises(RuntimeError, match="invalid public homelab"):
        load_public_homelab_v1("a" * 5000)


def test_output_schema_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        PublicHomelabV1.model_validate({"services": [], "port": 3900})
