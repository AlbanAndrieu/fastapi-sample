"""Offline contracts for the future deployment-unit sampling boundary."""

from __future__ import annotations

import json
import sys

import pytest

from nabla.api.homelab_probe_units import (
    build_probe_units,
    main,
    select_probe_units,
)


def _component(
    name: str,
    *,
    unit: str | None = None,
    priority: int | None = None,
    external: bool = False,
    policy: dict | None = None,
) -> dict:
    entry = {"id": name, "external": external}
    if unit is not None:
        entry["deploymentUnitId"] = unit
    if priority is not None:
        entry["probePriority"] = priority
    if policy is not None:
        entry["probePolicy"] = policy
    return entry


def test_garage_is_one_unit_with_distinct_components_and_explicit_sequence() -> None:
    policy = {
        "primaryEndpoint": "garage",
        "secondaryEndpoints": ["garage-admin", "garage-webui"],
    }
    entries = [
        _component("garage", unit="truenas:garage", priority=0, policy=policy),
        _component("garage-admin", unit="truenas:garage", priority=1, policy=policy),
        _component(
            "garage-webui",
            unit="truenas:garage",
            priority=2,
            external=True,
            policy=policy,
        ),
    ]
    internal = build_probe_units(entries, observer="internal")
    assert len(internal) == 1
    assert internal[0].unit_id == "truenas:garage"
    assert internal[0].component_ids == ("garage", "garage-admin", "garage-webui")
    assert internal[0].primary_endpoint == "garage"
    assert internal[0].secondary_endpoints == ("garage-admin", "garage-webui")
    assert internal[0].priority == 0
    public = build_probe_units(entries, observer="public")
    assert len(public) == 1
    assert public[0].component_ids == ("garage-webui",)
    assert public[0].primary_endpoint is None
    assert public[0].secondary_endpoints == ("garage-webui",)


def test_unpublished_unit_metadata_never_guesses_membership() -> None:
    entries = [
        _component("garage"),
        _component("garage-admin"),
        _component("garage-webui"),
    ]
    assert len(build_probe_units(entries, observer="internal")) == 3
    assert build_probe_units(entries, observer="public") == []


def test_full_budget_keeps_ten_prioritized_units_and_rotates_all() -> None:
    entries = [
        *[_component(f"priority-{i}", priority=i) for i in range(12)],
        *[_component(f"background-{i}") for i in range(15)],
    ]
    units = build_probe_units(entries, observer="internal")
    batches = [select_probe_units(units, limit=12, cycle=i) for i in range(14)]
    assert all(len(batch) == 12 for batch in batches)
    fixed = {f"service:priority-{i}" for i in range(10)}
    assert all(fixed <= {unit.unit_id for unit in batch} for batch in batches)
    assert {u.unit_id for batch in batches for u in batch} == {u.unit_id for u in units}


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_small_budgets_never_starve_other_units(limit: int) -> None:
    units = build_probe_units(
        [_component(f"service-{i}", priority=i) for i in range(7)],
        observer="internal",
    )
    batches = [select_probe_units(units, limit=limit, cycle=i) for i in range(10)]
    assert all(len(batch) == limit for batch in batches)
    assert {u.unit_id for batch in batches for u in batch} == {u.unit_id for u in units}


@pytest.mark.parametrize("invalid", [
    [_component("garage", priority=True)],
    [_component("garage", priority=-1)],
    [_component("garage", unit="")],
    [_component("garage"), _component("garage")],
    [_component("garage", policy={"primaryEndpoint": "not-garage"})],
    [
        _component(
            "garage",
            policy={"primaryEndpoint": "garage", "secondaryEndpoints": ["garage"]},
        )
    ],
])
def test_invalid_unit_metadata_fails_closed(invalid: list[dict]) -> None:
    with pytest.raises(ValueError):
        build_probe_units(invalid, observer="internal")


def test_public_observer_cannot_select_private_garage_admin() -> None:
    entries = [
        _component("garage", unit="truenas:garage"),
        _component("garage-admin", unit="truenas:garage"),
        _component("garage-webui", unit="truenas:garage", external=True),
    ]
    ids = [
        name
        for unit in build_probe_units(entries, observer="public")
        for name in unit.component_ids
    ]
    assert ids == ["garage-webui"]


def test_offline_preview_does_not_attempt_network(
    tmp_path, monkeypatch, capsys
) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"services": [
            _component("garage", unit="truenas:garage"),
            _component("garage-admin", unit="truenas:garage"),
        ]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv",
        ["probe-plan", "--catalog", str(catalog), "--observer", "internal"],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_performed"] is False
    assert len(payload["selected_units"]) == 1
    assert payload["selected_units"][0]["component_ids"] == [
        "garage", "garage-admin"
    ]
