#!/bin/bash
#set -eu

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run Test ${NC}"

# shellcheck disable=SC2086
${WORKING_DIR}/../nabla/get_data.py

cd "${WORKING_DIR}/../nabla" || exit
# ./get_data.py

# dd.dd_api_exporter.get_products -v
# python3 -m dd.dd_api_exporter.get_products -t XXXX -v
cd "${WORKING_DIR}" || exit

# python -m pytest nabla
# python -m pytest tests

exit 0
