#!/usr/bin/env bash
# Build-up: deploy karverktyg to the local k3s cluster from a .conf of API keys.
#
#   scripts/k8s-up.sh [karverktyg.conf]
#
# Blank values in the .conf disable that endpoint/action (the key is omitted, so
# the app reports the capability as unavailable). An existing database is reused
# and migrated when compatible; otherwise templates are preserved and the rest
# rebuilt (see db.bootstrap, run as an init step). POSIX-bash compatible (3.2+).
set -eu

NS=karverktyg
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
# Secrets (API keys + DB password) come from apikeys.conf; everything else is in
# the committed karverktyg.json.
CONF="${1:-apikeys.conf}"

[ -f "$CONF" ] || {
  echo "secrets file '$CONF' not found — copy apikeys.conf.example and fill it in." >&2
  exit 1
}

# Trimmed value for a key from the .conf (empty if blank or absent).
conf_val() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\(.*\)\$/\1/p" "$CONF" | tail -n1 | sed 's/[[:space:]]*$//'
}

PGDB=karverktyg
PGUSER=karverktyg
PGPASS="$(conf_val POSTGRES_PASSWORD)"; PGPASS="${PGPASS:-devpassword}"
DSN="$(conf_val SCOUTNET_DATABASE_URL)"
# CloudNativePG exposes the primary at <cluster>-rw (karverktyg-db-rw).
DSN="${DSN:-postgresql+psycopg://${PGUSER}:${PGPASS}@karverktyg-db-rw:5432/${PGDB}}"
MODE="$(conf_val SCOUTNET_MODE)"; MODE="${MODE:-read_only}"

echo "==> building image karverktyg:latest"
docker build -t karverktyg:latest "$HERE" >/dev/null

kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS" >/dev/null

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
kubectl -n "$NS" create secret generic karverktyg-secrets "$@" \
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
kubectl -n "$NS" create secret generic karverktyg-db-app \
  --type=kubernetes.io/basic-auth \
  --from-literal=username="$PGUSER" \
  --from-literal=password="$PGPASS" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "==> applying manifests"
kubectl apply -f k8s/local/ >/dev/null
kubectl -n "$NS" rollout restart deploy/karverktyg >/dev/null 2>&1 || true

echo "==> waiting for Postgres (CNPG cluster)"
# Wait on the Cluster resource (present immediately after apply) rather than its
# pods, which the operator creates a moment later (a label wait would race).
kubectl -n "$NS" wait --for=condition=Ready cluster/karverktyg-db --timeout=300s
echo "==> waiting for app (db-bootstrap runs first)"
kubectl -n "$NS" rollout status deploy/karverktyg --timeout=180s

echo
echo "karverktyg is up in namespace '$NS'."
echo "  db-bootstrap log:  kubectl -n $NS logs deploy/karverktyg -c db-bootstrap"
echo "  open the app:      kubectl -n $NS port-forward svc/karverktyg 8000:80   # http://localhost:8000"
