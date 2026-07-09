#!/bin/bash
#set -xve

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run python test ${NC}"

#pip install coverage==4.5.3
#coverage --version || true

# curl --head -H "Authorization: ${UNLEASH_API_TOKEN}" https://gitlab.com/api/v4/feature_flags/unleash/46788175

DEFAULT_COV="${CI_PROJECT_NAME:-nabla}"

mkdir -p reports

pytest_args=(
  "--cov=${DEFAULT_COV}"
  "--cov-report=term-missing"
  "--cov-report=xml:reports/coverage.xml"
  "--cov-fail-under=70"
)

pytest "${pytest_args[@]}"

echo "pytest -k test_redis_demo_items_one_second --timeout=5 --collect-only"

exit 0
