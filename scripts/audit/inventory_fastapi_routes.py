#!/usr/bin/env python3
"""Read-only inventory of registered FastAPI routes for privacy review.

This is a desired-classification *audit*, not an access-control mechanism.
Unclassified routes always require review; nothing becomes public by default.
No HTTP probes, credentials, service names, route responses or URLs are fetched.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
import sys
from typing import Any

# Keep the offline script usable without installing the repository package.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from nabla.route_policy import route_policy_for  # noqa: E402


def intended_policy(path: str, methods: Iterable[str], kind: str) -> str:
    """Classify from the same source used in middleware, not a duplicate list."""
    method_set = set(methods)
    if kind == "http" and not method_set:
        return "REVIEW"
    choices = {route_policy_for(path, method=method, kind=kind).visibility.value for method in method_set}
    if not choices:
        return route_policy_for(path, kind=kind).visibility.value
    return choices.pop() if len(choices) == 1 else "REVIEW"


def inventory_routes(routes: Iterable[Any], *, prefix: str = "") -> list[dict[str, object]]:
    """Traverse declared routes including mounts, websocket and opaque apps."""
    result: list[dict[str, object]] = []
    for route in routes:
        fragment = getattr(route, "path", None)
        # Starlette Host routes have no .path; retain a review placeholder
        # rather than silently omitting that entire ASGI application.
        if fragment is None and type(route).__name__ == "Host":
            fragment = "/__host_mount__"
        if not isinstance(fragment, str) or not fragment.startswith("/"):
            continue
        path = prefix.rstrip("/") + fragment
        nested = getattr(route, "routes", None)
        if nested is not None:
            children = inventory_routes(nested, prefix=path)
            if children:
                result.extend(children)
                continue
        kind = "websocket" if "WebSocket" in type(route).__name__ else "http"
        if nested is not None or type(route).__name__ in {"Mount", "Host"}:
            kind = "opaque_mount"
        methods = sorted(str(method).upper() for method in (getattr(route, "methods", None) or ()))
        policy = intended_policy(path, methods, kind)
        result.append({"path": path, "kind": kind, "methods": methods, "intended_policy": policy})
    return sorted(result, key=lambda row: (str(row["path"]), str(row["kind"]), str(row["methods"])))


def audit_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    """Return only stable route definitions, no request or runtime metadata."""
    counts = Counter(str(row["intended_policy"]) for row in rows)
    return {
        "schema_version": 1,
        "classification_is_enforcement": False,
        "total_routes": len(rows),
        "review_required": counts["REVIEW"],
        "counts": dict(sorted(counts.items())),
        "routes": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 3 when any route requires review")
    args = parser.parse_args()
    # Import is intentionally deferred: --help and unit tests need no app
    # lifecycle, network, credentials or external service integration.
    from nabla.main import app  # noqa: PLC0415

    summary = audit_summary(inventory_routes(app.routes))
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 3 if args.strict and summary["review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
