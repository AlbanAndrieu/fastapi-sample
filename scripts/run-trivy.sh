#!/usr/bin/env bash
# shellcheck shell=bash
#
# Local reproduction of the blocking MegaLinter REPOSITORY_TRIVY scan.
# The scope (production dependencies, fixed findings only, triaged
# .trivyignore.yaml) must stay identical to REPOSITORY_TRIVY_ARGUMENTS in
# .mega-linter.yml; tests/unit/test_trivy_baseline_contract.py enforces it.
# Trivy is pinned by mise.lock. The vulnerability DB is downloaded on demand,
# so a DB download failure is an infrastructure error, not a finding.

set -euo pipefail

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${WORKING_DIR}/.." && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/step-0-color.sh"

TRIVY_ARGS=(
  --scanners "vuln,misconfig,secret,license" --vuln-type "os,library" --ignore-unfixed
  --ignorefile .trivyignore.yaml --skip-dirs .direnv --skip-dirs .venv
  --skip-dirs code/.venv --skip-dirs megalinter-reports --skip-dirs node_modules
  --skip-dirs vue-client/node_modules --skip-dirs open-webui --skip-files pip.conf
  --skip-files Pipfile --skip-files Pipfile.lock --skip-files uv.lock
  --skip-files trivy-sbom.json --skip-files "*.tgz"
)

echo -e "${green} Run trivy (blocking repository scan) ${NC}"

cd "${REPO_ROOT}"
trivy --version
trivy fs --skip-version-check --exit-code 1 "${TRIVY_ARGS[@]}" "$@" .

# trivy-sbom.json can be imported in DD as cycloneDX scan:
# trivy fs --include-dev-deps --format cyclonedx . -o trivy-sbom.json
