#!/usr/bin/env bash
set -euo pipefail

KUBECTL_BIN="${KUBECTL_BIN:-kubectl}"
NAMESPACE="${NAMESPACE:-monitoring}"
PROMETHEUS_NAME="${PROMETHEUS_NAME:-kube-prometheus-stack-prometheus}"

ACTION="${1:-status}"
EXECUTION_MODE="${2:-}"

get_interval() {
  "$KUBECTL_BIN" -n "$NAMESPACE" get prometheus "$PROMETHEUS_NAME" \
    -o jsonpath='{.spec.scrapeInterval}'
}

show_help() {
  cat <<EOF
Usage: $0 {status|test|restore} [--execute]

Actions :
  status             Affiche l'intervalle actuel sans modification.
  test               Simule le passage temporaire a 5s.
  test --execute     Applique temporairement l'intervalle de 5s.
  restore            Simule le retour a 30s.
  restore --execute  Restaure l'intervalle normal de 30s.

Les actions test et restore effectuent toujours un dry-run serveur
avant une modification reelle.
EOF
}

case "$ACTION" in
  -h|--help|help)
    show_help
    exit 0
    ;;
  status)
    echo "SCRAPE_INTERVAL=$(get_interval)"
    exit 0
    ;;
  test)
    TARGET_INTERVAL="5s"
    ;;
  restore)
    TARGET_INTERVAL="30s"
    ;;
  *)
    echo "Usage: $0 {status|test|restore} [--execute]" >&2
    exit 2
    ;;
esac

if [ -n "$EXECUTION_MODE" ] && [ "$EXECUTION_MODE" != "--execute" ]; then
  echo "ERREUR: option inconnue: $EXECUTION_MODE" >&2
  exit 2
fi

CURRENT_INTERVAL="$(get_interval)"
PATCH_PAYLOAD="{\"spec\":{\"scrapeInterval\":\"${TARGET_INTERVAL}\"}}"

echo "PROMETHEUS=${PROMETHEUS_NAME}"
echo "INTERVALLE_ACTUEL=${CURRENT_INTERVAL}"
echo "INTERVALLE_CIBLE=${TARGET_INTERVAL}"

"$KUBECTL_BIN" -n "$NAMESPACE" patch prometheus "$PROMETHEUS_NAME" \
  --type=merge \
  --patch "$PATCH_PAYLOAD" \
  --dry-run=server \
  -o name

if [ "$EXECUTION_MODE" != "--execute" ]; then
  echo "MODE=SIMULATION"
  echo "AUCUNE_MODIFICATION_EFFECTUEE"
  exit 0
fi

"$KUBECTL_BIN" -n "$NAMESPACE" patch prometheus "$PROMETHEUS_NAME" \
  --type=merge \
  --patch "$PATCH_PAYLOAD"

VERIFIED_INTERVAL="$(get_interval)"
echo "INTERVALLE_APRES=${VERIFIED_INTERVAL}"

if [ "$VERIFIED_INTERVAL" != "$TARGET_INTERVAL" ]; then
  echo "ERREUR: intervalle non applique." >&2
  exit 1
fi

echo "VERIFICATION=OK"
