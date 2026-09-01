"""Tests for the ordered TrueNAS diagnostic pipeline."""

from nabla.api.truenas_diagnostics import append_truenas_api_stages


def _network_ok():
    return {
        "target": "truenas.example:7000",
        "stages": [
            {"id": "dns", "label": "DNS", "state": "ok"},
            {"id": "socket", "label": "TCP connect", "state": "ok"},
            {"id": "tls", "label": "TLS handshake", "state": "ok"},
            {"id": "https", "label": "HTTPS", "state": "ok"},
            {"id": "websocket", "label": "WebSocket tunnel", "state": "ok"},
        ],
    }


def test_missing_api_key_marks_auth_failed_and_api_blocked() -> None:
    result = append_truenas_api_stages(
        _network_ok(),
        {
            "reachable": False,
            "phase": "authentication",
            "stage": "missing_api_key",
            "error": "TRUENAS_API_KEY is missing; authentication cannot be attempted.",
        },
    )

    auth, api = result["stages"][-2:]
    assert auth["id"] == "authentication"
    assert auth["state"] == "fail"
    assert auth["failure_stage"] == "missing_api_key"
    assert api == {
        "id": "api",
        "label": "TrueNAS API",
        "state": "blocked",
        "detail": "Blocked by authentication",
    }


def test_websocket_failure_blocks_authentication() -> None:
    network = _network_ok()
    network["stages"][-1]["state"] = "fail"
    result = append_truenas_api_stages(network, {"reachable": False})

    assert result["stages"][-2]["state"] == "blocked"
    assert result["stages"][-1]["state"] == "blocked"
