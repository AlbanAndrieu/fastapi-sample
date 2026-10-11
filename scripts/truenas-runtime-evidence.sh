#!/usr/bin/env bash
# Read-only evidence from TrueNAS or an external workstation.
set -euo pipefail

runtime_url="${FASTAPI_RUNTIME_URL:-http://172.17.0.24:8091}"
mode=report
vantage=auto
while (($#)); do
  case "$1" in
    --strict) mode=strict ;;
    --vantage)
      [[ $# -ge 2 ]] || { echo '❌ --vantage requires a value' >&2; exit 2; }
      vantage="$2"
      shift ;;
    --help|-h)
      printf 'Usage: %s [--strict] [--vantage auto|truenas|workstation]\n' "$0"
      exit 0 ;;
    *) printf '❌ Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

case "$vantage" in
  auto)
    local_host="$(hostname -s 2>/dev/null || true)"
    if [[ "${local_host,,}" == "truenas" ]]; then
      vantage=truenas
    else
      vantage=workstation
    fi ;;
  truenas|workstation) ;;
  *) echo '❌ Invalid vantage' >&2; exit 2 ;;
esac

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
script="$root/scripts/diagnose-local-runtime-dependencies.py"
if [[ ! -f "$script" ]]; then
  echo '❌ FastAPI diagnostic script not found in this checkout.' >&2
  exit 2
fi

printf '📍 Observer=%s; target=TrueNAS (172.17.0.24)\n' "$vantage"
printf '\n🔎 FastAPI cached dependency evidence\n'
if [[ "$mode" == strict ]]; then
  python3 "$script" --url "$runtime_url" --wait-seconds 50 || exit $?
else
  python3 "$script" --url "$runtime_url" --wait-seconds 50 --report-only || exit $?
fi

if [[ "$vantage" != truenas ]]; then
  echo 'ℹ️ Workstation: Docker local is unrelated to TrueNAS; skipping container inspection.'
elif [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
  echo '⚠️ Explicit Docker host/context set: skipping ambiguous inventory.'
elif ! command -v docker >/dev/null 2>&1; then
  echo '⚠️ Docker CLI unavailable on TrueNAS.'
else
  printf '\n🐳 TrueNAS Docker inventory (metadata only)\n'
  if names="$(docker ps -a --format '{{.Names}}' 2>/dev/null)"; then
    for service in postgresql redis sentry gatus prometheus pyroscope; do
      case "$service" in
        postgresql) name=ix-postgres-postgres-1 ;;
        sentry) name=ix-sentry-sentry-web-1 ;;
        *) name="$service" ;;
      esac
      if ! grep -Fxq -- "$name" <<< "$names"; then
        printf '❔ %-12s %s not found\n' "$service" "$name"
        continue
      fi
      status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$name" 2>/dev/null || true)"
      printf '🐳 %-12s %-37s state=%s health=%s\n' "$service" "$name" "${status:-unknown}" "${health:-unknown}"
    done
  else
    echo '⚠️ Docker socket unavailable; no container evidence collected.'
  fi
fi

if command -v curl >/dev/null 2>&1; then
  printf '\n📡 TrueNAS network endpoints (read-only; from %s)\n' "$vantage"
  for item in 'gatus|http://172.17.0.24:8085/' 'prometheus|http://172.17.0.24:9090/-/ready' 'pyroscope|http://172.17.0.24:4040/ready'; do
    service="${item%%|*}"
    url="${item#*|}"
    status="$(curl -sS -o /dev/null --connect-timeout 2 --max-time 5 -w '%{http_code}' "$url" 2>/dev/null)" || status=000
    if [[ "$status" == 2* ]]; then symbol='✅'; else symbol='⚠️'; fi
    printf '%s %-12s HTTP=%s\n' "$symbol" "$service" "$status"
  done
fi
echo 'ℹ️ HTTP/container readiness cannot prove authenticated SQL/PING, Sentry ingestion, or Gatus history.'
