#!/bin/bash
#set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "WORKING_DIR: ${WORKING_DIR}"

rm -Rf "${WORKING_DIR}/../.netlify"
rm -Rf "${WORKING_DIR}/../.node_cache"
rm -Rf "${WORKING_DIR}/../node_modules"
rm -Rf "${WORKING_DIR}/../.ruff_cache"
rm -Rf "${WORKING_DIR}/../.npm"
rm -Rf "${WORKING_DIR}/../.ansible"
rm -Rf "${WORKING_DIR}/../.direnv"
rm -Rf "${WORKING_DIR}/../.venv"
rm -Rf "${WORKING_DIR}/../megalinter-reports"
rm -Rf "${WORKING_DIR}/../node_modules"
rm -Rf "${WORKING_DIR}/../vue-client/.nuxt"
rm -Rf "${WORKING_DIR}/../vue-client/.npm"
rm -Rf "${WORKING_DIR}/../vue-client/.node_cache"
rm -Rf "${WORKING_DIR}/../vue-client/node_modules"

cd "${WORKING_DIR}/.."

rm -Rf _build/ build/ .eggs/ .toxs/ dist/ output/pytest-report.xml .coverage output/coverage.xml coverage.xml docs/_build/ .tox/ .scannerwork/ .pytest_cache/ pytest-report.xml output/htmlcov/ cprofile

rm -Rf my-app/.netlify my-app/node_modules

find . -maxdepth 2 -mindepth 2 -regextype posix-egrep -type d -regex '.+/.*egg-info' -exec rm -rf {} \;
find . -maxdepth 2 -mindepth 2 -regextype posix-egrep -type d -regex '.*__pycache__.*' -exec rm -rf {} \;
find hooks -type f -name "*.pyc" -delete 2>/dev/null || true

rm -Rf output/ || true
mkdir output || true

echo "sudo docker system -prune"

exit 0
