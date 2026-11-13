"""Redis opt-in must share sanitized public evidence without leaking LAN targets."""

from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from nabla.api import homelab_probe_evidence, homelab_probe_evidence_redis
from tests.unit.catalog_v2_fixture import service as v2_service


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.data.get(key) for key in keys]

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        assert 0 < ex <= 3600
        self.data[key] = value
        return True


@pytest.mark.asyncio
async def test_redis_public_only_survives_worker_reset_without_sensitive_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setenv("HOMELAB_PUBLIC_PROBE_EVIDENCE_REDIS_ENABLED", "true")
    monkeypatch.setenv("HOMELAB_PROBE_EVIDENCE_NAMESPACE", "cloud_test")
    monkeypatch.setattr(homelab_probe_evidence_redis, "resolve_redis_client", lambda: fake)
    service = v2_service("gatus", "https://gatus.example.org", title="Gatus", public=True, edge="direct")
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    row = {
        "id": "gatus",
        "state": "warn",
        "reachable": True,
        "http_status": 403,
        "public_probe_verification": "access_protected_origin_unverified",
        "probe_source": "origin",
        "host": "172.17.0.24",
        "url": "https://gatus.example.org",
        "token": "must-never-persist",
    }
    assert (
        await homelab_probe_evidence_redis.write_public_probe_evidence(
            [row],
            observed_at,
        )
        is True
    )
    stored = json.dumps(fake.data)
    assert "172.17.0.24" not in stored
    assert "must-never-persist" not in stored
    assert "https://gatus.example.org" not in stored

    homelab_probe_evidence.reset_probe_evidence()
    try:
        entries, shared = await homelab_probe_evidence_redis.read_public_probe_evidence(
            [service],
        )
        assert shared is True
        results = homelab_probe_evidence.merge_probe_evidence(
            "public",
            current_results=[],
            eligible_services=[service],
            checked_at=observed_at,
            shared_entries=entries,
        )
        assert len(results) == 1
        assert results[0]["probe_source"] == "memory"
        assert results[0]["state"] == "warn"
        assert results[0]["public_probe_verification"] == ("access_protected_origin_unverified")
    finally:
        homelab_probe_evidence.reset_probe_evidence()


@pytest.mark.asyncio
async def test_redis_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HOMELAB_PUBLIC_PROBE_EVIDENCE_REDIS_ENABLED", raising=False)
    assert await homelab_probe_evidence_redis.read_public_probe_evidence([]) == ([], False)
    assert await homelab_probe_evidence_redis.write_public_probe_evidence([], "") is False
