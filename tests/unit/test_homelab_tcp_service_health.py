"""Tests for TCP-only homelab service reconciliation."""

from nabla.api.homelab_health_evidence import build_reconciled_service_health
from nabla.api.homelab_models import HomelabService


def test_tcp_only_postgresql_dependency_row_is_preserved() -> None:
    service = HomelabService(
        id="postgresql",
        name="PostgreSQL",
        tunnelUrl="postgres://postgres.albandrieu.com:5432/",
        internalHost="172.17.0.24",
        internalPort=5432,
        external=False,
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
    assert rows[0]["url"] == "postgres://postgres.albandrieu.com:5432/"
    assert rows[0]["internal_state"] == "ok"
    assert rows[0]["state"] == "ok"
