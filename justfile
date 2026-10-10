# Local-first developer commands. Keep Makefile for legacy Docker/Sphinx tasks.
# All quality/publish checks delegate to the canonical repository scripts.
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# List available recipes (safe default; no build/deploy).
default:
    @just --list

# Install exactly the locked Python development environment.
sync:
    uv sync --frozen

# Run the local FastAPI development server.
dev:
    uv run fastapi dev --port 8080

# Run repository tests without resolving dependencies.
test:
    bash scripts/run-pytest-compact.sh

# Exercise the offline agent/source/pytest contracts without GitHub Actions.
# This is targeted L1 evidence; it does not replace quality/publish-check.
test-local-first:
    bash -n scripts/agent-source-snapshot.sh
    bash -n scripts/run-pytest-compact.sh
    bash -n scripts/agent-quality-gate.sh
    bash scripts/run-pytest-compact.sh tests/unit/test_agent_source_snapshot.py tests/unit/test_compact_pytest_runner.py tests/unit/test_quality_log_tail_contract.py

# Run only pfSense observation, probe and tracing contracts.
test-pfsense:
    bash scripts/run-pytest-compact.sh tests/unit/test_pfsense_auth_smoke.py tests/unit/test_pfsense_dns_observer.py tests/unit/test_pfsense_security_cache.py tests/unit/test_probe_headers.py tests/unit/test_probe_metrics.py

# Collect passive pfSense latency/protection evidence from Prometheus only.
pfsense-baseline window="30m":
    uv run --no-sync python scripts/collect_pfsense_probe_baseline.py --window "{{window}}"

# Check Python lint without modifying sources.
lint:
    uv run --no-sync ruff check .

# Check Python formatting without modifying sources.
format-check:
    uv run --no-sync ruff format --check .

# Apply Ruff formatting deliberately (modifies sources).
format:
    uv run --no-sync ruff format .

# Prefer Homebrew's versioned v1 binary; mise installs "betterleaks".
secrets:
    @if command -v betterleaks-v1 >/dev/null 2>&1; then betterleaks-v1 dir . --config .gitleaks.toml --redact; else betterleaks dir . --config .gitleaks.toml --redact; fi

# Scan only staged Git additions, matching the pre-commit hook.
secrets-staged:
    @if command -v betterleaks-v1 >/dev/null 2>&1; then betterleaks-v1 git . --pre-commit --staged --config .gitleaks.toml --redact; else betterleaks git . --pre-commit --staged --config .gitleaks.toml --redact; fi

# Apply deterministic fixes and run the canonical agent quality gate.
fix:
    bash scripts/agent-quality-gate.sh --fix

# Run the canonical agent quality gate (no GitHub Actions).
quality:
    bash scripts/agent-quality-gate.sh

# Validate the exact HEAD/base/toolchain publication proof; does not publish.
publish-check:
    bash scripts/agent-publish.sh

# Show the legacy Makefile help while migration remains additive.
make-help:
    make help

# Delegate the legacy documentation build to the unchanged Makefile.
docs:
    make doc

# Delegate the legacy Docker build to the unchanged Makefile.
docker-build:
    make build-docker

# Delegate the legacy container run target to the unchanged Makefile.
docker-up:
    make up

# Delegate any explicitly requested legacy target to Make.
# Example: just legacy test-semgrep
legacy target:
    make "{{target}}"
