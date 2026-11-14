#!/usr/bin/env bash
# Canonical cold-start cache refresh from the generated Compose Backstage V2 artifact.
# Usage: scripts/refresh-catalog-snapshot.sh [local entities.json]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${ROOT}/nabla/api/data/catalog-snapshot.json"
DEFAULT_URL="https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/generated/entities.json"
SOURCE="${1:-${DEFAULT_URL}}"
TEMP="$(mktemp "${TARGET}.tmp.XXXXXX")"
trap 'rm -f "${TEMP}"' EXIT

if [[ -f "${SOURCE}" ]]; then
  cp -- "${SOURCE}" "${TEMP}"
elif [[ "${SOURCE}" == "${DEFAULT_URL}" ]]; then
  curl --fail --silent --show-error --location --proto '=https' \
    --max-time 20 --max-filesize 2000000 "${SOURCE}" -o "${TEMP}"
else
  printf 'Unsupported source (provide a local file or the approved Compose URL)\n' >&2
  exit 2
fi

python3 - "${TEMP}" <<'PY'
import hashlib
import hmac
import json
import sys
from pathlib import Path

try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 2 or payload.get("model") != "backstage":
        raise ValueError("invalid Backstage V2 schema")
    entities = payload.get("entities")
    if not isinstance(entities, list) or not 0 < len(entities) <= 2000:
        raise ValueError("invalid Backstage entities")
    refs = [entity.get("entityRef") for entity in entities if isinstance(entity, dict)]
    if len(refs) != len(entities) or not all(isinstance(ref, str) and ref for ref in refs) or len(refs) != len(set(refs)):
        raise ValueError("missing or duplicate entity references")
    ordered = sorted(entities, key=lambda item: item["entityRef"])
    digest = hashlib.sha256(
        json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    revision = payload.get("catalogRevision")
    if not isinstance(revision, str) or not hmac.compare_digest(revision, "sha256:" + digest):
        raise ValueError("catalogRevision does not match entity content")
except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
    raise SystemExit(f"Invalid catalog snapshot: {exc}") from exc
PY

if cmp -s "${TEMP}" "${TARGET}"; then
  printf 'catalog snapshot is already current\n'
  exit 0
fi

chmod 0644 "${TEMP}"
mv -f -- "${TEMP}" "${TARGET}"
printf 'catalog snapshot refreshed from %s\n' "${SOURCE}"
