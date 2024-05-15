#!/bin/bash
#set -xv

#pip install coverage==4.5.3
#coverage --version || true

DEFAULT_COV_TARGET="--cov-report xml:reports/coverage.xml --cov-append"
DEFAULT_COV_ARGS="--cov-fail-under=70"

export DEFAULT_COV=${CI_PROJECT_NAME:-"nabla"}

COVERAGE_FILE=.coverage coverage run --rcfile=.coveragerc -m pytest --cov=$DEFAULT_COV $DEFAULT_COV_TARGET $DEFAULT_COV_ARGS ${DEFAULT_FORMAT_TARGET} ${DEFAULT_COV_TARGET}

exit 0
