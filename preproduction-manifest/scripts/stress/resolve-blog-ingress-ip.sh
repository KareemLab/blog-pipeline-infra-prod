#!/usr/bin/env bash
set -euo pipefail

KUBECTL_BIN="${KUBECTL_BIN:-kubectl}"
INGRESS_NODE="${INGRESS_NODE:-rke2-worker-2}"
BLOG_HOST="${BLOG_HOST:-blog.k8s.test}"
BLOG_PATH="${BLOG_PATH:-/articles}"

INGRESS_IP="$(
  "$KUBECTL_BIN" get node "$INGRESS_NODE" \
    -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}'
)"

if [ -z "$INGRESS_IP" ]; then
  echo "ERROR: impossible de récupérer l'IP InternalIP du node ${INGRESS_NODE}" >&2
  exit 1
fi

echo "INGRESS_NODE=${INGRESS_NODE}" >&2
echo "INGRESS_IP=${INGRESS_IP}" >&2
echo "BLOG_HOST=${BLOG_HOST}" >&2

curl -fsSI \
  --max-time 10 \
  -H "Host: ${BLOG_HOST}" \
  "http://${INGRESS_IP}${BLOG_PATH}" >/dev/null

echo "$INGRESS_IP"
