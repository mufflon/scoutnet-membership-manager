#!/usr/bin/env bash
# Deploy from a locally-built image — no registry, no pull. Best for development:
# your working tree is what runs. Thin wrapper over k8s-up.sh.
#
#   scripts/k8s-up-local.sh [apikeys.conf]
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD=1 IMAGE="scoutnet-membership-manager:latest" PULL_POLICY=IfNotPresent \
  exec "$HERE/k8s-up.sh" "$@"
