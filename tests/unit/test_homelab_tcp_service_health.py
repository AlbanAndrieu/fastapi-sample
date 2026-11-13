"""Tests for TCP-only homelab service reconciliation."""

from nabla.api.homelab_health_evidence import build_reconciled_service_health
from tests.unit.catalog_v2_fixture import service as v2_service


def test_tcp_only_postgresql_dependency_row_is_preserved() -> None:
    service = v2_service(
        "postgresql",
        "https://postgres.albandrieu.com:5432",
        kind="Resource",
        title="PostgreSQL",
        backend=("172.17.0.24", 5432),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[
            {
                "id": "postgresql",
                "name": "PostgreSQL",
                "host": "172.17.0.24",
                "port": 5432,
                "reachable": True,
                "state": "ok",
            },
        ],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["id"] == "postgresql"
    assert rows[0]["entity_ref"] == "resource:default/postgresql"
    assert rows[0]["url"] == "https://postgres.albandrieu.com:5432/"
    assert rows[0]["internal_state"] == "ok"
    assert rows[0]["state"] == "ok"
