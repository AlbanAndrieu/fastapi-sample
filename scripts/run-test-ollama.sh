#!/bin/bash
#set -xve

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green} Run ollam test ${NC}"

uv add ollama

uv run python -c "import fastmcp; import ollama; print('✅ All packages installed')"

# https://dev.to/ajitkumar/building-your-first-agentic-ai-complete-guide-to-mcp-ollama-tool-calling-2o8g

export UNLEASH_ENABLED="false"
# make up-mcp
make up

echo "http://0.0.0.0:8091/llm/mcp"
# http://0.0.0.0:8091/v1/mcp/ops/servers

uv run python nabla/tools/client_ollama.py

exit 0
