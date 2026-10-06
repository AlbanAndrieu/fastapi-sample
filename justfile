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
    uv run --no-sync pytest -q --disable-warnings --maxfail=1

# Run only pfSense observation, probe and tracing contracts.
test-pfsense:
    uv run --no-sync pytest -q --disable-warnings --maxfail=1 tests/unit/test_pfsense_auth_smoke.py tests/unit/test_pfsense_dns_observer.py tests/unit/test_pfsense_security_cache.py tests/unit/test_probe_headers.py tests/unit/test_probe_metrics.py

# Check Python lint without modifying sources.
lint:
    uv run --no-sync ruff check .

# Check Python formatting without modifying sources.
format-check:
    uv run --no-sync ruff format --check .

# Apply Ruff formatting deliberately (modifies sources).
format:
    uv run --no-sync ruff format .

# Scan the current working tree using the existing reviewed exclusions.
secrets:
    betterleaks dir . --config .gitleaks.toml --redact

# Scan only staged Git additions, matching the pre-commit hook.
secrets-staged:
    betterleaks git . --pre-commit --staged --config .gitleaks.toml --redact

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
