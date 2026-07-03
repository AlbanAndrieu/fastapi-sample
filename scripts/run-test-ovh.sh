#!/usr/bin/env bash
# shellcheck shell=bash

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run OVH connection test ${NC}"

uv run python3 ./nabla/api/auth/openstack.py

exit 0
