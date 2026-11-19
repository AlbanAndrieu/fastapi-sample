#!/usr/bin/env bash
# Canonical cold-start cache refresh from the generated Compose Backstage V2 artifact.
# Usage: scripts/refresh-catalog-snapshot.sh [local entities.json with sibling operator-inventory.json]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${ROOT}/nabla/api/data/catalog-snapshot.json"
DEFAULT_URL="https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/generated/entities.json"
SOURCE="${1:-${DEFAULT_URL}}"
OPERATOR_TARGET="${ROOT}/nabla/api/data/operator-inventory.json"
TEMP="$(mktemp "${TARGET}.tmp.XXXXXX")"
OPERATOR_TEMP="$(mktemp "${OPERATOR_TARGET}.tmp.XXXXXX")"
trap 'rm -f "${TEMP}" "${OPERATOR_TEMP}"' EXIT

if [[ -f "${SOURCE}" ]]; then
  cp -- "${SOURCE}" "${TEMP}"
  cp -- "$(dirname "${SOURCE}")/operator-inventory.json" "${OPERATOR_TEMP}"
elif [[ "${SOURCE}" == "${DEFAULT_URL}" ]]; then
  curl --fail --silent --show-error --proto '=https' \
    --max-time 20 --max-filesize 2000000 "${SOURCE}" -o "${TEMP}"
  curl --fail --silent --show-error --proto '=https' \
    --max-time 20 --max-filesize 2000000 "${SOURCE%/*}/operator-inventory.json" -o "${OPERATOR_TEMP}"
else
  printf 'Unsupported source (provide a local file or the approved Compose URL)\n' >&2
  exit 2
fi

python3 - "${TEMP}" "${OPERATOR_TEMP}" <<'PY'
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
    operator = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    if operator.get("schemaVersion") != 2 or operator.get("model") != "backstage-operator-inventory":
        raise ValueError("invalid operator inventory schema")
    if operator.get("catalogRevision") != revision:
        raise ValueError("operator inventory catalog revision mismatch")
    material = {key: operator[key] for key in ("services", "nodes", "relations")}
    native_digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if operator.get("operatorRevision") != "sha256:" + native_digest:
        raise ValueError("operator inventory content revision mismatch")
    bindings = operator["identityBindings"]
    ids = {row["id"] for row in operator["services"]}
    if set(bindings) != ids or not set(bindings.values()) <= set(refs):
        raise ValueError("operator inventory identity crosswalk mismatch")
    if set(operator["operationalOnlyNodeIds"]) != {node["id"] for node in operator["nodes"]} - ids:
        raise ValueError("operator-only node classification mismatch")
except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
    raise SystemExit(f"Invalid catalog snapshot: {exc}") from exc
PY

if cmp -s "${TEMP}" "${TARGET}" && cmp -s "${OPERATOR_TEMP}" "${OPERATOR_TARGET}"; then
  printf 'catalog snapshot is already current\n'
  exit 0
fi

chmod 0644 "${TEMP}" "${OPERATOR_TEMP}"
mv -f -- "${TEMP}" "${TARGET}"
mv -f -- "${OPERATOR_TEMP}" "${OPERATOR_TARGET}"
printf 'catalog snapshot refreshed from %s\n' "${SOURCE}"
