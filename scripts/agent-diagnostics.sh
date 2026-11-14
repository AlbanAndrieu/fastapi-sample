#!/usr/bin/env bash
# Safe by default: no network, secrets or runtime access in API-only sessions.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${AGENT_EXECUTION_MODE:-offline}"
action=static
while (($#)); do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo 'ERROR: --mode needs offline|workstation' >&2; exit 2; }
      mode="$2"; shift ;;
    --static) action=static ;;
    --runtime) action=runtime ;;
    --dns-only) action=dns ;;
    --help|-h)
      echo "Usage: $0 [--mode offline|workstation] [--static|--runtime|--dns-only]"
      echo 'Default offline; runtime/DNS require explicit workstation access.'
      exit 0 ;;
    *) echo "ERROR: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ "$mode" == offline || "$mode" == workstation ]] || {
  echo 'ERROR: AGENT_EXECUTION_MODE must be offline or workstation' >&2; exit 2;
}
if [[ "$action" == static ]]; then
  exec bash "$root/scripts/agent-offline-check.sh"
fi
if [[ "$mode" != workstation ]]; then
  echo 'NOT_RUN: runtime and LAN DNS require explicit workstation mode' >&2
  exit 2
fi
if [[ "$action" == dns ]]; then
  exec bash "$root/scripts/truenas-runtime-evidence.sh" --vantage workstation --dns-only
fi
exec bash "$root/scripts/truenas-runtime-evidence.sh" --vantage workstation --quick
