"""Deployment configuration regression tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vercel_is_a_lightweight_fastapi_cloud_proxy() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] is None
    assert config["ignoreCommand"] == '[ "$VERCEL_GIT_COMMIT_REF" != "main" ]'
    assert config["rewrites"] == [
        {
            "source": "/:path*",
            "destination": "https://fastapi-sample.fastapicloud.dev/:path*",
        },
    ]

    ignored = (ROOT / ".vercelignore").read_text(encoding="utf-8")
    assert "!pyproject.toml" not in ignored
    assert "!uv.lock" not in ignored
    assert "!nabla" not in ignored
