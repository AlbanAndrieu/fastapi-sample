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
                "checked_at": f"2026-10-18T00:00:{completed:02d}Z",
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


def test_aggregate_whitelists_deadline_phase_totals_without_exposing_targets() -> None:
    snapshots = [
        {
            "state": "fresh",
            "homelab": {
                "checked_at": "2026-10-18T00:00:01Z",
                "probe_cache": {"source": "origin"},
                "probe_summary": {
                    "public": {
                        "completed": 2,
                        "timed_out": 10,
                        "deadline_phase_counts": {
                            "not_started": 0,
                            "waiting_on_semaphore": 3,
                            "dns_in_progress": 5,
                            "head_get_in_progress": 1,
                            "access_secondary_in_progress": 1,
                            "tcp_in_progress": 0,
                            "Authorization": "Bearer NEVER_LEAK",
                            "url": "https://PRIVATE.example.invalid",
                        },
                    }
                },
            },
        },
        {
            "state": "stale",
            "homelab": {
                "probe_cache": {"source": "memory"},
                "probe_summary": {
                    "public": {
                        "completed": 0,
                        "timed_out": 12,
                        "deadline_phase_counts": {"dns_in_progress": 12},
                    }
                },
            },
        },
    ]
    output = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate"],
        input="\n".join(json.dumps(row) for row in snapshots) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert output.returncode == 0, output.stderr
    assert "NEVER_LEAK" not in output.stdout + output.stderr
    assert "PRIVATE" not in output.stdout + output.stderr
    evidence = json.loads(output.stdout)
    assert evidence["origin_cycles"] == 1
    assert evidence["deadline_phase_totals"] == {
        "not_started": 0,
        "waiting_on_semaphore": 3,
        "dns_in_progress": 5,
        "head_get_in_progress": 1,
        "access_secondary_in_progress": 1,
        "tcp_in_progress": 0,
    }


def test_aggregate_deduplicates_repeated_fresh_origin_health_boards() -> None:
    """Re-reading one cached board must not invent independent probe waves."""
    first = {
        "state": "fresh",
        "generated_at": "2026-10-18T00:00:02Z",
        "homelab": {
            "checked_at": "2026-10-18T00:00:01.123456Z",
            "probe_cache": {"source": "origin"},
            "probe_summary": {
                "public": {
                    "completed": 2,
                    "timed_out": 10,
                    "deadline_phase_counts": {"dns_in_progress": 7},
                },
            },
        },
    }
    repeated = json.loads(json.dumps(first))
    # The envelope can be newer without refreshing homelab probes.
    repeated["generated_at"] = "2026-10-18T00:00:40Z"
    repeated["homelab"]["probe_summary"]["public"]["completed"] = 12
    distinct = json.loads(json.dumps(first))
    distinct["homelab"]["checked_at"] = "2026-10-18T00:01:01Z"
    distinct["homelab"]["probe_summary"]["public"]["completed"] = 12
    distinct["homelab"]["probe_summary"]["public"]["timed_out"] = 0
    distinct["homelab"]["probe_summary"]["public"]["deadline_phase_counts"] = {}
    missing_identity = json.loads(json.dumps(first))
    del missing_identity["homelab"]["checked_at"]
    missing_identity["secret"] = "NEVER_LEAK"
    untrusted_identity = json.loads(json.dumps(first))
    untrusted_identity["homelab"]["checked_at"] = "https://NEVER_LEAK.example.invalid"

    snapshots = [first, repeated, distinct, missing_identity, untrusted_identity]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate"],
        input="\n".join(json.dumps(item) for item in snapshots) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "NEVER_LEAK" not in result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert output["origin_candidate_envelopes"] == 5
    assert output["origin_cycles"] == 2
    assert output["duplicate_origin_envelopes"] == 1
    assert output["unattributed_origin_envelopes"] == 2
    assert output["three_distinct_origin_cycles_observed"] is False
    assert output["public_completed_range"] == {"min": 2, "max": 12}
    assert output["public_deadline_range"] == {"min": 0, "max": 10}
    assert output["deadline_phase_totals"]["dns_in_progress"] == 7


def test_aggregate_requires_valid_wave_identity_even_for_fresh_origin() -> None:
    bad = {
        "state": "fresh",
        "homelab": {
            "checked_at": "2026-99-88T99:99:99Z",
            "probe_cache": {"source": "origin"},
            "probe_summary": {"public": {"completed": 12, "timed_out": 0}},
        },
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate"],
        input=json.dumps(bad) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["origin_cycles"] == 0
    assert report["unattributed_origin_envelopes"] == 1
    assert report["interpretation"] == "missing_probe_wave_identity"


def test_aggregate_three_distinct_origin_waves_passes_sample_count() -> None:
    snapshots = [
        {
            "state": "fresh",
            "homelab": {
                "checked_at": f"2026-10-18T00:0{minute}:01Z",
                "probe_cache": {"source": "origin"},
                "probe_summary": {
                    "public": {"completed": 12 - minute, "timed_out": minute},
                },
            },
        }
        for minute in range(3)
    ]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate", "--require-three-origin-cycles"],
        input="\n".join(json.dumps(item) for item in snapshots) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["origin_cycles"] == 3
    assert report["duplicate_origin_envelopes"] == 0
    assert report["three_distinct_origin_cycles_observed"] is True
    assert report["interpretation"] == "variable_public_completion"


def test_aggregate_insufficient_unique_waves_exits_three_with_safe_report() -> None:
    snapshot = {
        "state": "fresh",
        "homelab": {
            "checked_at": "2026-10-18T00:00:01Z",
            "probe_cache": {"source": "origin"},
            "probe_summary": {"public": {"completed": 12, "timed_out": 0}},
        },
        "url": "https://NEVER_LEAK.example.invalid",
    }
    # A repeated healthy-looking board is not three distinct measurements.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--aggregate", "--require-three-origin-cycles"],
        input="\n".join(json.dumps(snapshot) for _ in range(3)) + "\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 3
    assert "NEVER_LEAK" not in result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["origin_cycles"] == 1
    assert report["duplicate_origin_envelopes"] == 2
    assert report["three_distinct_origin_cycles_observed"] is False
