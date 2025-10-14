#!/bin/bash
#set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -Rf "${WORKING_DIR}/.netlify"
rm -Rf "${WORKING_DIR}/.node_cache"
rm -Rf "${WORKING_DIR}/.ansible"
rm -Rf "${WORKING_DIR}/.direnv"
rm -Rf "${WORKING_DIR}/megalinter-reports"
rm -Rf "${WORKING_DIR}/node_modules"

rm -Rf _build/ build/ .eggs/ .toxs/ dist/ output/pytest-report.xml .coverage output/coverage.xml coverage.xml docs/_build/ .tox/ .scannerwork/ .pytest_cache/ pytest-report.xml output/htmlcov/ cprofile

find . -maxdepth 2 -mindepth 2 -regextype posix-egrep -type d -regex '.+/.*egg-info' -exec rm -rf {} \;
find . -maxdepth 2 -mindepth 2 -regextype posix-egrep -type d -regex '.*__pycache__.*' -exec rm -rf {} \;
find hooks -type f -name "*.pyc" -delete

rm -Rf output/ || true
mkdir output || true

exit 0
