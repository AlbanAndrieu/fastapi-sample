#!/bin/bash
#set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rm -Rf "${WORKING_DIR}/.netlify"
rm -Rf "${WORKING_DIR}/.node_cache"
rm -Rf "${WORKING_DIR}/.ansible"
rm -Rf "${WORKING_DIR}/.direnv"
rm -Rf "${WORKING_DIR}/megalinter-reports"
rm -Rf "${WORKING_DIR}/node_modules"

exit 0
