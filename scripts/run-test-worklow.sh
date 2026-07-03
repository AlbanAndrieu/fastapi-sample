#!/usr/bin/env bash
# shellcheck shell=bash

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run Workflow test ${NC}"

curl -sS --max-time 95 -X POST "http://127.0.0.1:8091/run" \
  -H "Content-Type: application/json" \
  --data-binary '{"user_input":"Who is Alban Andrieu?"}'

exit 0
