"""Contract tests for read-only redacted health-board cycle summaries."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/audit/summarize_homelab_cycles.py"


def _run(*payloads: object) -> subprocess.CompletedProcess[str]:
    data = "\n".join(json.dumps(item) for item in payloads) + "\n"
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=data,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_summary_never_reprints_raw_service_urls_headers_or_secrets() -> None:
    response = {
        "state": "stale",
        "age_seconds": 36.8,
        "sensitive": "NEVER_LEAK",
        "homelab": {
            "probe_cache": {"source": "memory", "age_seconds": 32.0},
            "probe_summary": {
                "public": {
                    "completed": 1,
                    "timed_out": 11,
                    "priority_source": "bootstrap",
                    "timing": {
                        "completed_samples": 1,
                        "max_queue_wait_ms": 180,
                        "max_dns_probe_ms": 47,
                        "max_http_request_ms": 614,
                        "max_access_secondary_ms": None,
                    },
                },
                "internal": {
                    "completed": 12,
                    "timed_out": 0,
                    "evidence": {"coverage_percent": 20.9},
                },
            },
            "internal_services": [
                {"id": "garage"},
                {"id": "garage-admin"},
                {"id": "garage-webui"},
            ],
            "services": [
                {
                    "id": "garage-admin",
                    "internal_state": "ok",
                    "exposure_intent": "internal",
                    "unexpected_tunnel_route": True,
                    "url": "https://PRIVATE:NEVER_LEAK@example.invalid",
                    "authorization": "NEVER_LEAK",
                },
            ],
        },
    }
    result = _run(response)
    assert result.returncode == 0, result.stderr
    assert "NEVER_LEAK" not in result.stdout + result.stderr
    assert "PRIVATE" not in result.stdout
    summary = json.loads(result.stdout)
    assert summary["board_state"] == "stale"
    assert summary["probe_cache_source"] == "memory"
    assert summary["public"]["completed"] == 1
    assert summary["public"]["timed_out"] == 11
    assert summary["public"]["timing"]["max_queue_wait_ms"] == 180
    assert summary["internal"]["coverage_percent"] == 20.9
    assert summary["garage"]["garage-admin"]["internal_state"] == "ok"
    assert summary["garage"]["garage-admin"]["unexpected_tunnel_route"] is True
    assert "garage_admin_exposure_drift" in summary["warnings"]
    assert "public_fanout_deadline_not_service_down" in summary["warnings"]
    assert "cached_or_pending_evidence_not_fresh" in summary["warnings"]


def test_summary_handles_missing_or_untrusted_fields_conservatively() -> None:
    response = {
        "state": {"unexpected": "not a string"},
        "homelab": {
            "services": [{"id": {"bad": "key"}}],
            "internal_services": [{"id": ["garage"]}],
            "probe_summary": {
                "public": {
                    "completed": True,
                    "timed_out": 0,
                    "priority_source": ["catalog"],
                    "timing": {"max_queue_wait_ms": "unknown"},
                },
            },
        },
    }
    result = _run(response)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["board_state"] is None
    assert summary["public"]["completed"] is None
    assert summary["public"]["priority_source"] is None
    assert summary["public"]["timing"]["max_queue_wait_ms"] is None
    assert summary["garage"]["garage"]["lan_observed"] is False


def test_summary_streams_multiple_snapshots_without_retaining_credentials() -> None:
    result = _run({"state": "fresh", "homelab": {}}, {"state": "stale", "homelab": {}})
    assert result.returncode == 0
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [line["board_state"] for line in lines] == ["fresh", "stale"]


def test_summary_fails_closed_on_malformed_json_without_echoing_input() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input='{"secret":"NEVER_LEAK"',
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2
    assert "invalid JSON" in result.stderr
    assert "NEVER_LEAK" not in result.stderr


def test_aggregate_excludes_stale_and_retained_windows() -> None:
    """Counts fresh origin cycles, not a repeated cached health envelope."""

    def board(state: str, source: str, completed: int, timeout: int) -> dict:
        return {
            "state": state,
            "secret": "NEVER_LEAK",
            "homelab": {
                "probe_cache": {"source": source},
                "probe_summary": {
                    "public": {
                        "completed": completed,
                        "timed_out": timeout,
                        "timing": {
                            "completed_samples": completed,
                            "max_queue_wait_ms": 180 if completed == 1 else 24,
                        },
                    },
                    "internal": {"completed": 12, "timed_out": 0},
                },
                "internal_services": [{"id": key} for key in ("garage", "garage-admin", "garage-webui")],
                "services": [
                    {
                        "id": key,
                        "internal_state": "ok",
                        "unexpected_tunnel_route": key == "garage-admin",
                    }
                    for key in ("garage", "garage-admin", "garage-webui")
                ],
            },
        }

    snapshots = (
        board("fresh", "origin", 1, 11),
        board("stale", "memory", 12, 0),
        board("fresh", "memory", 12, 0),
        board("fresh", "origin", 11, 1),
    )
    output = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate"],
        input="\n".join(json.dumps(item) for item in snapshots) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert output.returncode == 0, output.stderr
    assert "NEVER_LEAK" not in output.stdout + output.stderr
    evidence = json.loads(output.stdout)
    assert evidence["total_snapshots"] == 4
    assert evidence["fresh_envelopes"] == 3
    assert evidence["stale_or_pending_envelopes"] == 1
    assert evidence["origin_cycles"] == 2
    assert evidence["public_completed_range"] == {"min": 1, "max": 11}
    assert evidence["public_deadline_range"] == {"min": 1, "max": 11}
    assert evidence["origin_cycles_with_public_deadlines"] == 2
    assert evidence["all_three_garage_lan_ok_origin_cycles"] == 2
    assert evidence["garage_admin_unexpected_route_seen"] is True
    assert evidence["observed_phase_maxima_ms"]["max_queue_wait_ms"] == 180
    assert evidence["interpretation"] == "variable_public_completion"


def test_aggregate_without_origin_is_inconclusive() -> None:
    output = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate"],
        input=json.dumps({"state": "stale", "homelab": {"probe_cache": {"source": "memory"}}}) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert output.returncode == 0, output.stderr
    evidence = json.loads(output.stdout)
    assert evidence["origin_cycles"] == 0
    assert evidence["public_completed_range"] == {"min": None, "max": None}
    assert evidence["interpretation"] == "insufficient_current_origin_evidence"


def test_aggregate_limits_input_and_does_not_echo_sensitive_payload() -> None:
    output = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate"],
        input=(json.dumps({"state": "fresh", "secret": "NEVER_LEAK"}) + "\n") * 65,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert output.returncode == 2
    assert "too many input snapshots" in output.stderr
    assert "NEVER_LEAK" not in output.stdout + output.stderr
