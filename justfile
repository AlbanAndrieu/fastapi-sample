# Local-first developer commands. Keep Makefile for legacy Docker/Sphinx tasks.
# All quality/publish checks delegate to the canonical repository scripts.
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# List available recipes (safe default; no build/deploy).
default:
    @just --list

# Read-only Python 3.13 worktree environment check.
worktree-python-check:
    bash scripts/agent-worktree-python.sh --check

# Explicit locked installation, never in system Python or other worktrees.
worktree-python-sync:
    bash scripts/agent-worktree-python.sh --sync

# Install exactly the locked Python development environment.
sync:
    uv sync --frozen

# Install only distributions already available in the uv cache (no DNS/network).
offline-sync:
    UV_OFFLINE=true uv sync --frozen --offline

# Run the test suite using existing dependencies without network resolution.
# For targeted tests: UV_OFFLINE=true bash scripts/run-pytest-compact.sh tests/unit/test_dns_probe.py
offline-test:
    UV_OFFLINE=true bash scripts/run-pytest-compact.sh

# Run the local FastAPI development server.
dev:
    uv run fastapi dev --port 8080

# Start the service like `make up` (gunicorn); e.g. `just up PORT=8091 DATADOG_ENABLED=true`.
up *args:
    make up {{ args }}

# Run repository tests without resolving dependencies.
test:
    bash scripts/run-pytest-compact.sh

# Exercise the offline agent/source/pytest contracts without GitHub Actions.
# This is targeted L1 evidence; it does not replace quality/publish-check.
test-local-first:
    bash -n scripts/agent-source-snapshot.sh
    bash -n scripts/run-pytest-compact.sh
    bash -n scripts/agent-quality-gate.sh
    bash -n scripts/agent-offline-check.sh
    bash scripts/run-pytest-compact.sh tests/unit/test_agent_source_snapshot.py tests/unit/test_compact_pytest_runner.py tests/unit/test_quality_log_tail_contract.py tests/unit/test_quality_failure_log_retention.py tests/unit/test_dagger_pilot_preflight.py

# P1 Dagger pilot reference: native deterministic checks only, not a release gate.
# Record this baseline before implementing a pinned Dagger module.
p1-parity-native:
    just test-local-first
    just lint
    just format-check

# P1 readiness is read-only and fails closed until Dagger is configured.
p1-dagger-preflight:
    bash scripts/dagger-pilot-preflight.sh

# Post-reboot cached integration report (no direct provider fan-out).
truenas-check:
    python3 scripts/diagnose-local-runtime-dependencies.py --url http://172.17.0.24:8091 --report-only

# Strict post-reboot acceptance: all evidence must be complete to return 0.
truenas-acceptance:
    python3 scripts/diagnose-local-runtime-dependencies.py --url http://172.17.0.24:8091 --wait-seconds 50

# Read-only TrueNAS runtime triage; uses the script location, not current working directory.
truenas-evidence:
    bash scripts/truenas-runtime-evidence.sh

# Compare split DNS on the selected host. No probes or mutations.
# Run the workstation recipe on the workstation and the TrueNAS recipe on TrueNAS.
dns-evidence-workstation:
    bash scripts/truenas-runtime-evidence.sh --vantage workstation --dns-only

dns-evidence-truenas:
    bash scripts/truenas-runtime-evidence.sh --vantage truenas --dns-only

# Strict evidence acceptance; reports missing proofs as a nonzero exit.
truenas-evidence-strict:
    bash scripts/truenas-runtime-evidence.sh --strict

# Targeted runtime tests in the pinned uv environment (not the host Python).
test-runtime-evidence:
    bash scripts/run-pytest-compact.sh tests/unit/test_truenas_runtime_evidence_wrapper.py tests/unit/test_diagnose_homelab_dns.py tests/unit/test_local_runtime_dependency_report.py tests/unit/test_synthetic_probe_comparison.py tests/unit/test_platform_metrics.py

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

# Bababou parity: dependency-free syntax + draft-runner policy. Zero hosted minutes.
offline-l1:
    bash scripts/agent-offline-check.sh

# Explicit targeted P0 gate; requires dependencies already installed, never syncs.
p0:
    bash scripts/agent-offline-check.sh
    UV_OFFLINE=true bash scripts/run-pytest-compact.sh tests/unit/test_agent_offline_l1.py tests/unit/test_draft_workflow_budget_contract.py tests/unit/test_talos_manifest_contract.py

# Mandatory full workflow audit through the existing pinned pre-commit hooks.
workflow-audit:
    uv run --no-sync pre-commit run actionlint --all-files
    uv run --no-sync pre-commit run zizmor --all-files

# Offline Kubernetes rendering (no deploy, push, or GitHub CI).
k8s-render:
    kubectl kustomize deploy/talos

k8s-contracts:
    UV_OFFLINE=true bash scripts/run-pytest-compact.sh tests/unit/test_talos_manifest_contract.py

# No-install Cloud Python compatibility inventory; never modifies pyproject/uv.lock.
python-cloud-audit:
    python3 scripts/ci/check_fastapi_cloud_python_upgrade.py --candidate 3.14.9

# Explicit opt-in canary: uses a disposable directory and uv --dry-run.
# Offline by default; resolution may fail when Python 3.14/wheels are not cached.
python-cloud-probe:
    python3 scripts/ci/check_fastapi_cloud_python_upgrade.py --candidate 3.14.9 --probe

python-cloud-contracts:
    UV_OFFLINE=true bash scripts/run-pytest-compact.sh tests/unit/test_fastapi_cloud_python_upgrade.py

# No browser access or cloud credentials are required for the LAN-only test.
prometheus-lan-evidence:
    python3 scripts/verify-prometheus-cloud-projection.py --check --scope lan

# Comparison requires explicit access to the FastAPI Cloud snapshot.
prometheus-cloud-evidence:
    python3 scripts/verify-prometheus-cloud-projection.py --check --scope both

prometheus-projection-contracts:
    bash scripts/run-pytest-compact.sh tests/unit/test_verify_prometheus_cloud_projection.py

# Pure JS contracts: no browser, Cloud access, or CI needed.
service-catalog-ux-contracts:
    node --test tests/js/service-catalog-ux.mjs

# Standalone offline exposure semantics; preserve the full quality gate unchanged.
service-exposure-policy-contracts:
    node --test tests/js/service-exposure-policy.mjs


# Fast local JS-only contracts on agent Node 22/npm 10; no npm install and no CI.
# Production dependency installation still follows package.json (Node >=24).
node22-quick:
    @node -e 'if (Number(process.versions.node.split(".")[0]) !== 22) { console.error("Requires Node 22 for this compatibility check"); process.exit(2); }'
    @npm --version | grep -Eq '^10[.]' || { echo "Requires npm 10" >&2; exit 2; }
    node --test tests/js/service-catalog-ux.mjs tests/js/service-exposure-policy.mjs
