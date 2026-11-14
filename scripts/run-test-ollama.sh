#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/../scripts/step-0-color.sh"

echo -e "${green:-} Run Ollama test ${NC:-}"

echo -e "${magenta:-} uv add ollama ${NC:-}"

echo -e "${magenta:-} uv run python -c \"import fastmcp; import ollama; print('✅ All packages installed')\" ${NC:-}"

# https://dev.to/ajitkumar/building-your-first-agentic-ai-complete-guide-to-mcp-ollama-tool-calling-2o8g

export UNLEASH_ENABLED="false"
# make up-mcp
echo -e "${magenta:-} make up ${NC:-}"

echo "http://0.0.0.0:8091/llm/mcp"
# http://0.0.0.0:8091/v1/mcp/ops/servers

export OLLAMA_HOST="${OLLAMA_HOST:-http://172.17.0.57:11434}"
export DEFAULT_MODEL="${DEFAULT_MODEL:-bonsai-2:9b}"

# Reuse the installed GPU model instead of downloading it on every run.
if ! ollama show "${DEFAULT_MODEL}" >/dev/null 2>&1; then
  ollama pull "${DEFAULT_MODEL}"
fi

echo -e "${magenta:-} sudo journalctl -n 50 -fu ollama ${NC:-}"

uv run python nabla/tools/client_ollama.py

