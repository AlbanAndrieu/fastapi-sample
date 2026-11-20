"""Offline webhook signature, provenance and route boundary regressions."""
import hashlib
import hmac
from datetime import datetime, timezone

from nabla.api.github_webhooks import project, valid_signature
from nabla.route_policy import Credential, Visibility, route_policy_for


def test_signature_and_exact_route():
    raw = b'{"fixture":true}'
    secret = "unit-test-only-not-a-real-secret-value"
    signed = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert valid_signature(raw, secret, signed)
    assert not valid_signature(raw + b" ", secret, signed)
    assert not valid_signature(raw, secret, "sha256=bad")
    assert route_policy_for("/webhooks/github", method="POST").credential is Credential.GITHUB_WEBHOOK
    assert route_policy_for("/webhooks/github", method="GET").visibility is Visibility.REVIEW
    assert route_policy_for("/webhooks/github/extra", method="POST").visibility is Visibility.REVIEW
    assert route_policy_for("/api/homelab/github-workflows").visibility is Visibility.OWNER


def test_projection_refuses_unapproved_installation_and_branch():
    now = datetime.now(timezone.utc)
    repo = {"full_name": "AlbanAndrieu/nabla-compose"}
    run = {
        "id": 123, "run_attempt": 1, "path": ".github/workflows/entra.yml",
        "head_branch": "master", "head_repository": repo, "head_sha": "a" * 40,
        "status": "completed", "conclusion": "success", "updated_at": now.isoformat(),
        "private_unused": "must-not-be-retained",
    }
    payload = {"action": "completed", "installation": {"id": 42}, "repository": repo, "workflow_run": run}
    receipt = project(payload, 42, now=now)
    assert receipt is not None
    assert receipt[1]["sha"] == "a" * 40
    assert "private_unused" not in receipt[1]
    assert project(payload, 43, now=now) is None
    for key, value in (("head_branch", "feature"), ("path", ".github/workflows/unknown.yml"),
                       ("head_repository", {"full_name": "unapproved/fork"}),
                       ("updated_at", "2020-01-01T00:00:00Z")):
        assert project({**payload, "workflow_run": {**run, key: value}}, 42, now=now) is None
