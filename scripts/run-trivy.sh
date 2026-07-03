#!/usr/bin/env bash
# shellcheck shell=bash

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run trivy ${NC}"

trivy --version

# trivy-sbom.json can be imported in DD as cycloneDX scan
echo -e "${magenta} trivy fs --config trivy-sbom.yaml --include-dev-deps --format cyclonedx . -o trivy-sbom.json ${NC}"

# # install CycloneDX SBOM generation tool for Python
# pip3 install cyclonedx-bom
#
# # install dependencies specified in pyproject.toml
# pip3 install .
#
# # generate CycloneDX SBOM
# python3 -m cyclonedx_py poetry --output-format json --outfile sbom.json

exit 0
