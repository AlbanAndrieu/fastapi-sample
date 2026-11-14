#!/usr/bin/env bash
# Single read-only diagnostic entrypoint. Isolated agents never reach the LAN.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
profile="auto"
scope="runtime"
plan=0
while (( $# )); do
  case "${1}" in
    --profile)
      (( $# >= 2 )) || { echo "Missing --profile value" >&2; exit 2; }
      profile="${2}"
      shift
      ;;
    --scope)
      (( $# >= 2 )) || { echo "Missing --scope value" >&2; exit 2; }
      scope="${2}"
      shift
      ;;
    --plan) plan=1 ;;
    --help|-h)
      echo 'Usage: agent-diagnostics.sh [--profile auto|workstation|isolated] [--scope runtime|dns|metrics|metrics-both|offline] [--plan]'
      exit 0
      ;;
    *) echo "Unknown argument: ${1}" >&2; exit 2 ;;
  esac
  shift
done
case "${profile}" in auto|workstation|isolated) ;; *) echo "Invalid profile" >&2; exit 2 ;; esac
case "${scope}" in runtime|dns|metrics|metrics-both|offline) ;; *) echo "Invalid scope" >&2; exit 2 ;; esac
cd "${ROOT}"
# The stdlib-only router is the sole profile authority. It never probes the LAN.
resolved="$(python3 scripts/agent-task-context.py --task truenas --profile "${profile}" --json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("executionProfile", "isolated"))')"
if [[ "${resolved}" != workstation || "${scope}" == offline ]]; then
  echo "PROFILE=${resolved} L1=offline-only LIVE_RUNTIME=NOT_RUN"
  if (( plan )); then
    echo 'Would run: bash scripts/agent-offline-check.sh'
    exit 0
  fi
  exec bash scripts/agent-offline-check.sh
fi
case "${scope}" in
  runtime) command=(bash scripts/truenas-runtime-evidence.sh --vantage workstation --detail) ;;
  dns) command=(bash scripts/truenas-runtime-evidence.sh --vantage workstation --dns-only) ;;
  metrics) command=(python3 scripts/verify-prometheus-cloud-projection.py --check --scope lan) ;;
  metrics-both) command=(python3 scripts/verify-prometheus-cloud-projection.py --check --scope both) ;;
esac
echo "PROFILE=workstation LIVE_RUNTIME=REQUESTED scope=${scope}; access remains unverified until execution"
if (( plan )); then
  printf "Would run:"
  printf " %q" "${command[@]}"
  printf "\n"
  exit 0
fi
exec "${command[@]}"
