#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "\${ROOT}"

warned=0

is_number() {
    [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

above() {
    awk -v value="$1" -v budget="$2" 'BEGIN { exit !(value > budget) }'
}

value_or_na() {
    if [[ -n "$1" ]]; then
        printf '%s' "$1"
    else
        printf 'n/a'
    fi
}

check_optional_budget() {
    local label="$1"
    local value="$2"
    local budget="$3"
    local unit="$4"

    if [[ -z "\${value}" || "\${value}" == "n/a" ]]; then
        printf 'ℹ️ %s: not measured for this scope\n' "\${label}"
        return 0
    fi
    if ! is_number "\${value}"; then
        printf '::warning::CI performance metric %s is invalid: %s\n' \
            "\${label}" "\${value}"
        warned=1
        return 0
    fi
    if [[ -z "\${budget}" ]]; then
        printf 'ℹ️ %s=%s%s (baseline only; no warning threshold configured)\n' \
            "\${label}" "\${value}" "\${unit}"
        return 0
    fi
    if ! is_number "\${budget}"; then
        printf '::warning::CI performance threshold for %s is invalid: %s\n' \
            "\${label}" "\${budget}"
        warned=1
        return 0
    fi
    if above "\${value}" "\${budget}"; then
        printf '::warning::CI performance regression candidate: %s=%s%s exceeds warning threshold %s%s\n' \
            "\${label}" "\${value}" "\${unit}" "\${budget}" "\${unit}"
        warned=1
    else
        printf '✅ %s=%s%s <= warning threshold %s%s\n' \
            "\${label}" "\${value}" "\${unit}" "\${budget}" "\${unit}"
    fi
}

check_optional_budget \
    "agent gate" "\${AGENT_GATE_SECONDS:-}" "\${AGENT_GATE_WARN_SECONDS:-}" "s"
check_optional_budget \
    "uv sync" "\${UV_SYNC_SECONDS:-}" "\${UV_SYNC_WARN_SECONDS:-}" "s"
check_optional_budget \
    "pytest" "\${PYTEST_SECONDS:-}" "\${PYTEST_WARN_SECONDS:-}" "s"
check_optional_budget \
    "uv build" "\${UV_BUILD_SECONDS:-}" "\${UV_BUILD_WARN_SECONDS:-}" "s"
check_optional_budget \
    ".venv" "\${VENV_MB:-}" "\${VENV_WARN_MB:-}" "MiB"
check_optional_budget \
    "dist" "\${DIST_MB:-}" "\${DIST_WARN_MB:-}" "MiB"

checkout_sha="$(git rev-parse HEAD 2>/dev/null || true)"
python_version="$(python --version 2>&1 || true)"
uv_version="$(uv --version 2>&1 || true)"
scope="\${CI_DEPENDENCY_MODE:-unknown}"

baseline_record="CI_PERF_BASELINE schema=1"
baseline_record+=" sha=$(value_or_na "\${checkout_sha}")"
baseline_record+=" event=$(value_or_na "\${GITHUB_EVENT_NAME:-}")"
baseline_record+=" run=$(value_or_na "\${GITHUB_RUN_ID:-}")"
baseline_record+=" attempt=$(value_or_na "\${GITHUB_RUN_ATTEMPT:-}")"
baseline_record+=" runner=$(value_or_na "\${RUNNER_OS:-}")-$(value_or_na "\${RUNNER_ARCH:-}")"
baseline_record+=" scope=$(value_or_na "\${scope}")"
baseline_record+=" python=$(value_or_na "\${python_version}")"
baseline_record+=" uv=$(value_or_na "\${uv_version}")"
baseline_record+=" agent_gate_s=$(value_or_na "\${AGENT_GATE_SECONDS:-}")"
baseline_record+=" uv_sync_s=$(value_or_na "\${UV_SYNC_SECONDS:-}")"
baseline_record+=" pytest_s=$(value_or_na "\${PYTEST_SECONDS:-}")"
baseline_record+=" uv_build_s=$(value_or_na "\${UV_BUILD_SECONDS:-}")"
baseline_record+=" venv_mb=$(value_or_na "\${VENV_MB:-}")"
baseline_record+=" dist_mb=$(value_or_na "\${DIST_MB:-}")"

printf '%s\n' "\${baseline_record}"

if [[ -n "\${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
        echo
        echo "### Python CI performance baseline"
        echo
        echo "- warning thresholds are optional and disabled by default"
        echo "- collect several exact-checkout baselines before setting thresholds"
        echo "- quality status remains non-blocking"
        echo
        printf '%s%s%s\n' "\`" "\${baseline_record}" "\`"
    } >>"\${GITHUB_STEP_SUMMARY}"
fi

if ((warned != 0)); then
    echo "⚠️ one or more CI performance measurements need review; quality remains non-blocking"
else
    echo "✅ CI performance baseline recorded"
fi
