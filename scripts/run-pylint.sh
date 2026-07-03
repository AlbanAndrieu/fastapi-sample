#!/usr/bin/env bash
# shellcheck shell=bash

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run Pylint ${NC}"

pylint --version

mkdir "${WORKING_DIR}/../output" || true

# shellcheck source=/dev/null
#source /opt/ansible/env38/bin/activate
echo -e "${magenta} pylint ${WORKING_DIR}/../nabla/ --output-format=parseable > ${WORKING_DIR}/../output/pylint.txt ${NC}"
pylint "${WORKING_DIR}/../nabla/*" --output-format=parseable >"${WORKING_DIR}/../output/pylint.txt"

echo -e "${magenta} pylint $(find ./nabla -name "*.py" -type f -print0 | xargs) ${NC}"

exit 0
