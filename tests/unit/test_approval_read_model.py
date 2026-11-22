"""OWNER approval DTO and database-unavailable boundaries; no real PostgreSQL."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.api.approvals import read_model
from nabla.route_policy import Credential, Visibility, route_policy_for


def test_read_model_fail_closed_and_method_policy(monkeypatch):
    settings = SimpleNamespace(operation_approval_read_model_enabled=False)
    monkeypatch.setattr(read_model, "get_settings", lambda: settings)
    monkeypatch.setattr(read_model, "homelab_runtime_detected", lambda: True)
    monkeypatch.setattr(read_model, "owner_ui_authenticated", lambda *_: True)
    app = FastAPI()
    read_model.register_approval_read_routes(app)
    client = TestClient(app)
    assert client.get("/api/homelab/approvals/pending").status_code == 404
    assert route_policy_for("/api/homelab/approvals/pending").credential is Credential.DIAGNOSTICS_KEY
    assert route_policy_for("/api/homelab/approvals/pending").visibility is Visibility.OWNER
    assert route_policy_for("/api/homelab/approvals/pending", method="POST").visibility is Visibility.OWNER


def test_owner_reads_minimal_pending_and_failure_is_503(monkeypatch):
    settings = SimpleNamespace(operation_approval_read_model_enabled=True)
    monkeypatch.setattr(read_model, "get_settings", lambda: settings)
    monkeypatch.setattr(read_model, "homelab_runtime_detected", lambda: True)
    owner = {"allowed": False}
    monkeypatch.setattr(read_model, "owner_ui_authenticated", lambda *_: owner["allowed"])
    expiry = datetime.now(timezone.utc) + timedelta(minutes=20)
    row = {
        "challenge_sha256": "a" * 64,
        "repository": "AlbanAndrieu/nabla-compose",
        "workflow": "entra.yml",
        "run_id": 42,
        "expires_at": expiry,
        "private_plan": "never send",
        "state": "pending",
    }
    db = SimpleNamespace(is_connected=True, fetch_all=AsyncMock(return_value=[row]))
    monkeypatch.setattr(read_model, "database", db)
    app = FastAPI()
    read_model.register_approval_read_routes(app)
    client = TestClient(app)
    assert client.get("/api/homelab/approvals/pending").status_code == 403
    db.fetch_all.assert_not_awaited()
    owner["allowed"] = True
    assert client.get("/api/homelab/approvals/pending?q=secret").status_code == 422
    ok = client.get("/api/homelab/approvals/pending")
    assert ok.status_code == 200
    assert ok.json()["count"] == 1
    assert ok.json()["approvals"][0]["status"] == "pending"
    assert "never send" not in ok.text
    assert ok.headers["cache-control"].startswith("private, no-store")
    db.fetch_all.side_effect = RuntimeError("sensitive PG error")
    denial = client.get("/api/homelab/approvals/pending")
    assert denial.status_code == 503
    assert "sensitive" not in denial.text
    monkeypatch.setattr(read_model, "homelab_runtime_detected", lambda: False)
    assert client.get("/api/homelab/approvals/pending").status_code == 404
