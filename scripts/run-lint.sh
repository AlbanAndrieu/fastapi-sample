#!/usr/bin/env bash
# shellcheck shell=bash

shopt -s extglob

#set -ueo pipefail
set -eo pipefail

# shellcheck disable=SC2034
WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
# source "${WORKING_DIR}/docker-env.sh"

echo -e "${magenta} Lint helm generic-service ${NC}"

# echo "go install golang.stackrox.io/kube-linter/cmd/kube-linter@latest"
kube-linter lint charts/

# checkov

kubescape scan

kubescape list frameworks

kubescape fix

echo "go install github.com/sigstore/cosign/v3/cmd/cosign@latest"

exit 0
