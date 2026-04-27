#!/bin/bash
set -eo pipefail

# See https://olivernguyen.io/w/direnv.run/

# shellcheck disable=SC2155
export RELATIVE_PATH=$(git rev-parse --show-prefix 2>/dev/null)

run-update-submodules() {
  git submodule update --init --recursive --remote
}

show-help() {
  items=()
  while IFS='' read -r line; do items+=("${line}"); done < \
    <(compgen -A "function" | grep "run-" | sed "s/run-//")
  printf -v items "\t%s\n" "${items[@]}"

  usage="USAGE: $(basename "$0") CMD [ARGUMENTS]
  CMD:\n${items}"
  # shellcheck disable=SC2059
  printf "${usage}"
}

NAME=$1
case "${NAME}" in
"" | "-h" | "--help" | "help")
  show-help
  ;;
*)
  shift
  if compgen -A "function" | grep "run-${NAME}" >/dev/null; then
    run-"${NAME}" "$@"
  else
    echo "ERROR: run-${NAME} not found."
    exit 123
  fi
  ;;
esac
