"""Appliance credentials must never inherit an ambient HTTP(S) proxy."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Header names that carry homelab appliance credentials (pfSense REST API).
_APPLIANCE_CREDENTIAL_HEADERS = frozenset({"X-API-Key"})


def _httpx_client_calls(node: ast.AST) -> list[ast.Call]:
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"AsyncClient", "Client"}
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "httpx"
    ]


def _sends_appliance_credentials(node: ast.AST) -> bool:
    return any(isinstance(constant, ast.Constant) and constant.value in _APPLIANCE_CREDENTIAL_HEADERS for constant in ast.walk(node))


def _ignores_ambient_proxy(call: ast.Call) -> bool:
    return any(keyword.arg == "trust_env" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False for keyword in call.keywords)


def test_credential_bearing_appliance_clients_disable_trust_env() -> None:
    checked: set[str] = set()
    offenders: set[str] = set()
    for path in sorted((ROOT / "nabla").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not _sends_appliance_credentials(function):
                continue
            for call in _httpx_client_calls(function):
                location = f"{path.relative_to(ROOT)}:{call.lineno}"
                checked.add(location)
                if not _ignores_ambient_proxy(call):
                    offenders.add(location)

    # pfSense DNS posture, security telemetry, liveness and the auth smoke CLI.
    assert len(checked) >= 4, sorted(checked)
    assert sorted(offenders) == []
