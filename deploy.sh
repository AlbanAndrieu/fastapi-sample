#!/bin/bash
#set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-0-color.sh"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-1-os.sh"

# Install full project dependencies (not only fastapi[standard]) before deploy.
uv sync

echo "❯ uv run fastapi deploy"
uv run fastapi deploy

exit 0
