#!/usr/bin/env bash
# Shared deploy engine for scoutnet-membership-manager on the local k3s cluster.
#
# Most people run one of the two wrappers instead of this directly:
#   scripts/k8s-up-local.sh      build the image here, no registry (dev)
#   scripts/k8s-up-upstream.sh   run the prebuilt GHCR image, no Docker build
#
# Direct use (defaults to a local build):
#   scripts/k8s-up.sh [apikeys.conf]
# Image source is chosen by env vars, which the wrappers set:
#   IMAGE=…         image to run (default scoutnet-membership-manager:latest)
#   BUILD=1|0       docker build IMAGE locally first (default 1)
#   PULL_POLICY=…   container imagePullPolicy (default IfNotPresent)
#
# Blank values in the .conf disable that endpoint/action (the key is omitted, so
# the app reports the capability as unavailable). An existing database is reused
# and migrated when compatible; otherwise templates are preserved and the rest
# rebuilt (see db.bootstrap, run as an init step). POSIX-bash compatible (3.2+).
set -eu

NS=scoutnet-membership-manager
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
# Secrets (API keys + DB password) come from apikeys.conf; everything else is in
# the committed scoutnet-membership-manager.json.
CONF="${1:-apikeys.conf}"

[ -f "$CONF" ] || {
  echo "secrets file '$CONF' not found — copy apikeys.conf.example and fill it in." >&2
  exit 1
}

# Trimmed value for a key from the .conf (empty if blank or absent).
conf_val() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\(.*\)\$/\1/p" "$CONF" | tail -n1 | sed 's/[[:space:]]*$//'
}

PGDB=scoutnet-membership-manager
PGUSER=scoutnet-membership-manager
PGPASS="$(conf_val POSTGRES_PASSWORD)"; PGPASS="${PGPASS:-devpassword}"
DSN="$(conf_val SCOUTNET_DATABASE_URL)"
# CloudNativePG exposes the primary at <cluster>-rw (scoutnet-membership-manager-db-rw).
DSN="${DSN:-postgresql+psycopg://${PGUSER}:${PGPASS}@scoutnet-membership-manager-db-rw:5432/${PGDB}}"
MODE="$(conf_val SCOUTNET_MODE)"; MODE="${MODE:-read_only}"

# Image source: build locally (default) or run a prebuilt image (e.g. from GHCR).
IMAGE="${IMAGE:-scoutnet-membership-manager:latest}"
BUILD="${BUILD:-1}"
PULL_POLICY="${PULL_POLICY:-IfNotPresent}"

if [ "$BUILD" = 1 ]; then
  echo "==> building image $IMAGE"
  docker build -t "$IMAGE" "$HERE" >/dev/null
else
  echo "==> using prebuilt image $IMAGE (pull policy $PULL_POLICY)"
fi

# Create the namespace declaratively so it carries the apply annotation from the
# start. Doing this before the Secret lands in it (below) means the later
# `kubectl apply -f k8s/local/` re-applies the same object cleanly, instead of
# warning that an imperatively-created (`kubectl create ns`) namespace is missing
# last-applied-configuration. Idempotent: a no-op when the namespace exists.
kubectl apply -f k8s/local/00-namespace.yaml >/dev/null

# Secret from the .conf: DB creds + DSN, plus every non-empty SCOUTNET_* key.
set -- \
  --from-literal=POSTGRES_DB="$PGDB" \
  --from-literal=POSTGRES_USER="$PGUSER" \
  --from-literal=POSTGRES_PASSWORD="$PGPASS" \
  --from-literal=SCOUTNET_DATABASE_URL="$DSN"
scoutnet_keys=0
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"
  case "$line" in \#* | "") continue ;; esac
  case "$line" in *=*) : ;; *) continue ;; esac
  key="$(printf '%s' "${line%%=*}" | tr -d '[:space:]')"
  val="$(printf '%s' "${line#*=}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  case "$key" in
    SCOUTNET_DATABASE_URL | POSTGRES_*) ;;
    SCOUTNET_*)
      if [ -n "$val" ]; then
        set -- "$@" --from-literal="$key=$val"
        scoutnet_keys=$((scoutnet_keys + 1))
      fi
      ;;
  esac
done < "$CONF"
kubectl -n "$NS" create secret generic scoutnet-membership-manager-secrets "$@" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "==> secret applied (${scoutnet_keys} SCOUTNET_ key(s) set; blanks disabled), mode=${MODE}"

# CloudNativePG operator (installed once), so the DB is a managed CNPG Cluster.
CNPG_VERSION="${CNPG_VERSION:-1.24.1}"
CNPG_BRANCH="release-$(printf '%s' "$CNPG_VERSION" | cut -d. -f1-2)"
if ! kubectl get crd clusters.postgresql.cnpg.io >/dev/null 2>&1; then
  echo "==> installing CloudNativePG operator ${CNPG_VERSION}"
  kubectl apply --server-side -f \
    "https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/${CNPG_BRANCH}/releases/cnpg-${CNPG_VERSION}.yaml" >/dev/null
  kubectl -n cnpg-system rollout status deploy/cnpg-controller-manager --timeout=180s
fi

# The app-role password for the CNPG cluster — CNPG adopts the <cluster>-app secret.
kubectl -n "$NS" create secret generic scoutnet-membership-manager-db-app \
  --type=kubernetes.io/basic-auth \
  --from-literal=username="$PGUSER" \
  --from-literal=password="$PGPASS" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "==> applying manifests"
kubectl apply -f k8s/local/ >/dev/null
# Point the app container and the db-bootstrap init container at the chosen image
# (the manifest ships the local :latest tag; upstream runs override it here).
kubectl -n "$NS" set image deploy/scoutnet-membership-manager \
  scoutnet-membership-manager="$IMAGE" db-bootstrap="$IMAGE" >/dev/null
kubectl -n "$NS" patch deploy/scoutnet-membership-manager --type=json -p \
  "[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/imagePullPolicy\",\"value\":\"$PULL_POLICY\"},{\"op\":\"replace\",\"path\":\"/spec/template/spec/initContainers/1/imagePullPolicy\",\"value\":\"$PULL_POLICY\"}]" >/dev/null
# Force fresh pods so a rebuilt local :latest (unchanged tag) is actually picked up.
kubectl -n "$NS" rollout restart deploy/scoutnet-membership-manager >/dev/null 2>&1 || true

echo "==> waiting for Postgres (CNPG cluster)"
# Wait on the Cluster resource (present immediately after apply) rather than its
# pods, which the operator creates a moment later (a label wait would race).
kubectl -n "$NS" wait --for=condition=Ready cluster/scoutnet-membership-manager-db --timeout=300s
echo "==> waiting for app (db-bootstrap runs first)"
kubectl -n "$NS" rollout status deploy/scoutnet-membership-manager --timeout=180s

echo
echo "scoutnet-membership-manager is up in namespace '$NS'."
echo "  db-bootstrap log:  kubectl -n $NS logs deploy/scoutnet-membership-manager -c db-bootstrap"
echo "  open the app:      kubectl -n $NS port-forward svc/scoutnet-membership-manager 8000:80   # http://localhost:8000"
