#!/bin/bash
#set -xve

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run py-psy ${NC}"

echo "https://github.com/benfred/py-spy"

pip install py-spy

py-spy top -- python main.py

exit 0
