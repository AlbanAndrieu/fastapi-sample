"""Deployment configuration regression tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vercel_is_a_lightweight_fastapi_cloud_proxy() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] is None
    assert config["ignoreCommand"] == '[ "$VERCEL_GIT_COMMIT_REF" != "master" ]'
    assert config["rewrites"] == [
        {
            "source": "/:path*",
            "destination": "https://fastapi-sample.fastapicloud.dev/:path*",
        }
    ]

    ignored = (ROOT / ".vercelignore").read_text(encoding="utf-8")
    assert "!pyproject.toml" not in ignored
    assert "!uv.lock" not in ignored
    assert "!nabla" not in ignored


def test_production_branch_is_master() -> None:
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")
    codeql = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    release = (ROOT / ".releaserc.yaml").read_text(encoding="utf-8")

    assert "branches: [master]" in deploy
    assert "branches: [master]" in python_ci
    assert "branches: [master]" in codeql
    assert "\n  - master\n" in release
    assert "branches: [main]" not in deploy
    assert "\n  - main\n" not in release


def test_production_validation_provides_required_auth_settings() -> None:
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")

    required_test_settings = (
        "KEYCLOAK_CLIENT_ID: test",
        "KEYCLOAK_CLIENT_SECRET: test-secret",
        "KEYCLOAK_REALM: test",
        "KEYCLOAK_SERVER_URL: http://localhost:8080",
        "OAUTH_TOKEN_SECRET: mocked-oauth-token-secret",
    )
    for setting in required_test_settings:
        assert setting in deploy
        assert setting in python_ci
