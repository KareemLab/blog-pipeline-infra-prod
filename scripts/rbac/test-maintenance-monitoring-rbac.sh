#!/usr/bin/env bash
set -euo pipefail

SA="system:serviceaccount:monitoring:maintenance-monitoring"

PASS=0
FAIL=0

expect() {
  local label="$1"
  local expected="$2"
  shift 2

  local result
  result="$(kubectl auth can-i "$@" --as="$SA" 2>/dev/null | tail -1 || true)"

  if [ "$result" = "$expected" ]; then
    printf 'OK   %-70s => %s\n' "$label" "$result"
    PASS=$((PASS + 1))
  else
    printf 'FAIL %-70s => expected=%s got=%s\n' "$label" "$expected" "$result"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== maintenance-monitoring RBAC tests ==="
echo "SA=${SA}"
echo

echo "=== POSITIFS - LECTURE ==="
expect "get nodes" yes get nodes
expect "list pods lab-k8s" yes list pods -n lab-k8s
expect "get pods/log lab-k8s" yes get pods/log -n lab-k8s
expect "list Argo CD applications" yes list applications.argoproj.io -n argocd
expect "list PrometheusRules monitoring" yes list prometheusrules.monitoring.coreos.com -n monitoring

echo
echo "=== POSITIFS - MAINTENANCE APP CONTROLEE ==="
expect "patch deployment blog-back-fpm" yes patch deployment/blog-back-fpm -n lab-k8s
expect "patch deployment blog-back-nginx" yes patch deployment/blog-back-nginx -n lab-k8s
expect "get scale blog-back-fpm" yes get deployment/blog-back-fpm -n lab-k8s --subresource=scale
expect "patch scale blog-back-fpm" yes patch deployment/blog-back-fpm -n lab-k8s --subresource=scale
expect "update scale blog-back-fpm" yes update deployment/blog-back-fpm -n lab-k8s --subresource=scale
expect "get scale blog-back-nginx" yes get deployment/blog-back-nginx -n lab-k8s --subresource=scale
expect "patch scale blog-back-nginx" yes patch deployment/blog-back-nginx -n lab-k8s --subresource=scale
expect "update scale blog-back-nginx" yes update deployment/blog-back-nginx -n lab-k8s --subresource=scale

echo
echo "=== NEGATIFS - SECRETS / RBAC ==="
expect "get secrets lab-k8s" no get secrets -n lab-k8s
expect "list roles lab-k8s" no list roles -n lab-k8s
expect "list rolebindings lab-k8s" no list rolebindings -n lab-k8s
expect "list clusterroles" no list clusterroles
expect "list serviceaccounts monitoring" no list serviceaccounts -n monitoring

echo
echo "=== NEGATIFS - PODS / EXEC / JOBS ==="
expect "delete pods lab-k8s" no delete pods -n lab-k8s
expect "create pods/exec lab-k8s" no create pods/exec -n lab-k8s
expect "create jobs lab-k8s" no create jobs -n lab-k8s
expect "patch jobs lab-k8s" no patch jobs -n lab-k8s
expect "delete jobs lab-k8s" no delete jobs -n lab-k8s

echo
echo "=== NEGATIFS - POSTGRESQL / KUBE-SYSTEM ==="
expect "patch PostgreSQL statefulset" no patch statefulset/pg-lab-postgresql-primary -n lab-k8s
expect "update PostgreSQL statefulset" no update statefulset/pg-lab-postgresql-primary -n lab-k8s
expect "delete pvc lab-k8s" no delete pvc -n lab-k8s
expect "list pods kube-system" no list pods -n kube-system
expect "patch rke2-canal daemonset" no patch daemonset/rke2-canal -n kube-system

echo
echo "=== NEGATIFS - AUTRES DEPLOYMENTS ==="
expect "patch PostgreSQL deployment name" no patch deployment/pg-lab-postgresql-primary -n lab-k8s

echo
echo "=== RESULTAT ==="
echo "PASS=${PASS}"
echo "FAIL=${FAIL}"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi
