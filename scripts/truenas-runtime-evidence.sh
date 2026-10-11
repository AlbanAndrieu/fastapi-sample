#!/usr/bin/env bash
# Read-only TrueNAS runtime dependency triage; safe from any working directory.
set -euo pipefail

runtime_url="${FASTAPI_RUNTIME_URL:-http://172.17.0.24:8091}"
mode="report"
case "${1:-}" in
  "") ;;
  --strict) mode="strict" ;;
  --help|-h)
    printf 'Usage: %s [--strict]\n' "$0"
    printf 'Default: read-only report (missing evidence is non-blocking).\n'
    exit 0 ;;
  *) printf '❌ Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
script="$root/scripts/diagnose-local-runtime-dependencies.py"
if [[ ! -f "$script" ]]; then
  echo '❌ FastAPI diagnostic not installed; run from fastapi-sample checkout.' >&2
  exit 2
fi

printf '\n🔎 FastAPI dependency evidence from %s\n' "$runtime_url"
if [[ "$mode" == strict ]]; then
  python3 "$script" --url "$runtime_url" --wait-seconds 50 || exit $?
else
  python3 "$script" --url "$runtime_url" --wait-seconds 50 --report-only || exit $?
fi
if ! command -v docker >/dev/null 2>&1; then
  echo '⚠️ Docker CLI unavailable; container evidence not collected.'
  exit 0
fi

printf '\n🐳 Container evidence (no secrets)\n'
names="$(docker ps -a --format '{{.Names}}' 2>/dev/null)" || {
  echo '⚠️ Docker unavailable or permission denied; no container status proof.'
  exit 0
}
for service in postgresql redis sentry gatus prometheus pyroscope; do
  case "$service" in
    postgresql) pattern='^(ix-postgres-postgres-1|postgres)$' ;;
    redis) pattern='^redis$' ;;
    sentry) pattern='^ix-sentry-sentry-web-1$' ;;
    *) pattern="^$service$" ;;
  esac
  name="$(printf '%s\n' "$names" | grep -E "$pattern" | head -n 1 || true)"
  if [[ -z "$name" ]]; then
    printf '❔ %-12s container not found (not evidence of application DOWN)\n' "$service"
    continue
  fi
  status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$name" 2>/dev/null || true)"
  printf '🐳 %-12s %-37s state=%s health=%s\n' "$service" "$name" "${status:-unknown}" "${health:-unknown}"
done

if command -v curl >/dev/null 2>&1; then
  printf '\n📡 Read-only HTTP readiness (bounded)\n'
  for item in 'gatus|http://172.17.0.24:8085/' 'prometheus|http://172.17.0.24:9090/-/ready' 'pyroscope|http://172.17.0.24:4040/ready'; do
    service="${item%%|*}"
    url="${item#*|}"
    status="$(curl -sS -o /dev/null --connect-timeout 2 --max-time 5 -w '%{http_code}' "$url" 2>/dev/null)" || status=000
    printf '%s %-12s HTTP=%s\n' "$([[ "$status" =~ ^2 ]] && echo '✅' || echo '⚠️')" "$service" "$status"
  done
fi
printf '\nℹ️ Container health, HTTP and pg_isready never prove SQL, Redis authentication, Sentry ingestion or Gatus history.\n'
