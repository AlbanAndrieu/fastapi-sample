#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ERROR: pfSense diagnosis/recovery moved to AlbanAndrieu/nabla-compose.

fastapi-sample is an observation/runtime consumer and no longer owns pfSense
administration or recovery logic.

Use a nabla-compose checkout instead:

  scripts/pfsense/diagnose-recover.sh --check

For API-only evidence when SSH is intentionally unavailable:

  scripts/pfsense/diagnose-recover.sh --api-only

Canonical source:
  https://github.com/AlbanAndrieu/nabla-compose/tree/master/scripts/pfsense
EOF

exit 64
