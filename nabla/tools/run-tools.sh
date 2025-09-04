#!/bin/bash
set -xv

# shellcheck disable=SC2034
WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PYTHONPATH=. &&
  python3 ./nabla/tools/ssh.py

exit 0
