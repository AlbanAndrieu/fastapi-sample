#!/usr/bin/env bash
# Refresh nabla/api/data/catalog-snapshot.json, the cold-start cache of the
# Backstage v2 catalog: a byte copy of nabla-compose
# catalog/generated/entities.json. Never edit the snapshot by hand.
# Usage: scripts/refresh-catalog-snapshot.sh [entities.json path or URL]
set -euo pipefail

SOURCE="${1:-https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/generated/entities.json}"
TARGET="$(cd "$(dirname "$0")/.." && pwd)/nabla/api/data/catalog-snapshot.json"

if [[ -f "${SOURCE}" ]]; then
  cp "${SOURCE}" "${TARGET}"
else
  curl -fsSL --proto '=https' "${SOURCE}" -o "${TARGET}"
fi
# tests/unit/test_catalog_routes.py verifies the catalogRevision digest.
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); sys.exit(d.get("schemaVersion") != 2 or d.get("model") != "backstage")' "${TARGET}"
printf 'catalog snapshot refreshed from %s\n' "${SOURCE}"
