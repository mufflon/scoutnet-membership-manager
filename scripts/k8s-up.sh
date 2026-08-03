#!/usr/bin/env bash
# Build-up: deploy karverktyg to the local k3s cluster from a .conf of API keys.
#
#   scripts/k8s-up.sh [karverktyg.conf]
#
# Blank values in the .conf disable that endpoint/action (the key is omitted, so
# the app reports the capability as unavailable). An existing database is reused
# and migrated when compatible; otherwise templates are preserved and the rest
# rebuilt (see db.bootstrap, run as an init step).
set -euo pipefail

NS=karverktyg
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
CONF="${1:-karverktyg.conf}"

[ -f "$CONF" ] || {
  echo "config '$CONF' not found — copy karverktyg.conf.example and fill it in." >&2
  exit 1
}

# --- parse the .conf (KEY=value; # comments; blank value => omitted) ----------
declare -A CFG
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  [[ "$line" != *=* ]] && continue
  key="$(printf '%s' "${line%%=*}" | xargs)"
  val="$(printf '%s' "${line#*=}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -n "$key" ] && CFG["$key"]="$val"
done < "$CONF"

PGDB=karverktyg
PGUSER=karverktyg
PGPASS="${CFG[POSTGRES_PASSWORD]:-devpassword}"
DSN="${CFG[SCOUTNET_DATABASE_URL]:-postgresql+psycopg://${PGUSER}:${PGPASS}@karverktyg-db:5432/${PGDB}}"

echo "==> building image karverktyg:latest"
docker build -t karverktyg:latest "$HERE" >/dev/null

kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS" >/dev/null

# --- secret from the .conf (only non-empty SCOUTNET_* keys are included) -------
args=(
  --from-literal=POSTGRES_DB="$PGDB"
  --from-literal=POSTGRES_USER="$PGUSER"
  --from-literal=POSTGRES_PASSWORD="$PGPASS"
  --from-literal=SCOUTNET_DATABASE_URL="$DSN"
)
scoutnet_keys=0
for k in "${!CFG[@]}"; do
  case "$k" in
    SCOUTNET_DATABASE_URL | POSTGRES_*) ;;  # handled above
    SCOUTNET_*)
      if [ -n "${CFG[$k]}" ]; then
        args+=(--from-literal="$k=${CFG[$k]}")
        scoutnet_keys=$((scoutnet_keys + 1))
      fi
      ;;
  esac
done
kubectl -n "$NS" create secret generic karverktyg-secrets "${args[@]}" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "==> secret applied (${scoutnet_keys} SCOUTNET_ key(s) set; blanks disabled), mode=${CFG[SCOUTNET_MODE]:-read_only}"

echo "==> applying manifests"
kubectl apply -f k8s/local/ >/dev/null
# Pick up a freshly built image on re-runs (same :latest tag).
kubectl -n "$NS" rollout restart deploy/karverktyg >/dev/null 2>&1 || true

echo "==> waiting for Postgres"
kubectl -n "$NS" rollout status deploy/karverktyg-db --timeout=120s
echo "==> waiting for app (db-bootstrap runs first)"
kubectl -n "$NS" rollout status deploy/karverktyg --timeout=180s

echo
echo "karverktyg is up in namespace '$NS'."
echo "  db-bootstrap log:  kubectl -n $NS logs deploy/karverktyg -c db-bootstrap"
echo "  open the app:      kubectl -n $NS port-forward svc/karverktyg 8000:80   # http://localhost:8000"
