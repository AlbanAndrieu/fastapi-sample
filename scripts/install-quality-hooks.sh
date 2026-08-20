#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

git config core.hooksPath .githooks

echo "✅ Git hooks installed via core.hooksPath=.githooks"
echo "   Every git push will run scripts/pre-push-check.sh."
