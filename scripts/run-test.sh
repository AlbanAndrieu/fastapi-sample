#!/bin/bash
#set -xve

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run test ${NC}"

#pip install coverage==4.5.3
#coverage --version || true

DEFAULT_COV_TARGET="--cov-report xml:reports/coverage.xml --cov-append"
DEFAULT_COV_ARGS="--cov-fail-under=70"

export DEFAULT_COV=${CI_PROJECT_NAME:-"nabla"}

COVERAGE_FILE=.coverage coverage run --rcfile=.coveragerc -m pytest --cov="${DEFAULT_COV}" "${DEFAULT_COV_TARGET} ${DEFAULT_COV_ARGS} ${DEFAULT_FORMAT_TARGET} ${DEFAULT_COV_TARGET}"

echo "pytest -k test_redis_demo_items_one_second --timeout=5 --collect-only"

exit 0
