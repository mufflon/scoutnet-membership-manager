#!/usr/bin/env bash
# Teardown: remove the whole deployment, including the PVC and its stored data.
#
#   scripts/k8s-down.sh [--rmi]
#
# Deleting the namespace deletes the app, Postgres, service, secret and the
# PersistentVolumeClaim; the local-path volume (reclaim policy Delete) then
# removes the on-disk data. Pass --rmi to also drop the built image.
set -euo pipefail

NS=karverktyg

echo "==> deleting namespace '$NS' (app, db, service, secret, PVC + its data)"
kubectl delete namespace "$NS" --wait=true --ignore-not-found

# Belt and suspenders: if the PVC lingered outside the namespace for any reason.
kubectl delete pvc karverktyg-db-data -n "$NS" --ignore-not-found >/dev/null 2>&1 || true

if [ "${1:-}" = "--rmi" ]; then
  docker rmi karverktyg:latest >/dev/null 2>&1 || true
  echo "==> removed image karverktyg:latest"
fi

echo "==> teardown complete — no persistent state remains."
