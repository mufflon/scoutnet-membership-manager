#!/usr/bin/env bash
# Deploy the prebuilt image published to GHCR — no local Docker build. Best for
# just running the tool: another kår can deploy without a build toolchain. Thin
# wrapper over k8s-up.sh.
#
#   scripts/k8s-up-upstream.sh [apikeys.conf]
#   IMAGE_TAG=v0.1.0 scripts/k8s-up-upstream.sh   # pin a release (default: latest)
#
# The GHCR package must be pullable by the cluster: either public, or the node
# logged in to ghcr.io. First publish is private — flip it to Public once.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG="${IMAGE_TAG:-latest}"
BUILD=0 IMAGE="ghcr.io/mufflon/scoutnet-membership-manager:${TAG}" PULL_POLICY=Always \
  exec "$HERE/k8s-up.sh" "$@"
