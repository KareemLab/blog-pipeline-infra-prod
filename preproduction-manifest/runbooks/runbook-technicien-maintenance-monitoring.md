# Runbook technicien maintenance — `maintenance-monitoring`

## 1. Objectif

Ce document décrit le profil Kubernetes et bastion :

```text
maintenance-monitoring
```

Ce profil sert à faire de la maintenance applicative contrôlée sur l’application `blog-back`, sans donner de droits d’administration complète du cluster.

Il se situe entre :

```text
technicien-monitoring
→ lecture seule

maintenance-monitoring
→ lecture + maintenance applicative limitée

masterdevops
→ administration complète
```

---

## 2. Compte Linux bastion

Compte créé :

```text
maintenance-monitoring
```

Home :

```text
/home/maintenance-monitoring
```

Shell :

```text
/bin/bash
```

Groupes :

```text
maintenance-monitoring
users
```

Droits sudo :

```text
aucun
```

Validation effectuée :

```text
User maintenance-monitoring is not allowed to run sudo on bastion-cloud-local.
```

Le mot de passe Linux sert uniquement à ouvrir une session sur le bastion.
Les droits Kubernetes viennent du kubeconfig limité.

---

## 3. Kubeconfig limité

Fichier kubeconfig :

```text
/home/maintenance-monitoring/.kube/config
```

Droits attendus :

```text
owner: maintenance-monitoring
group: maintenance-monitoring
mode: 600
```

Contexte Kubernetes :

```text
maintenance-monitoring@rke2-lab
```

Namespace par défaut :

```text
lab-k8s
```

Commandes de vérification :

```bash
kubectl config current-context
kubectl -n lab-k8s get pods
```

Résultat attendu :

```text
maintenance-monitoring@rke2-lab
pods visibles dans lab-k8s
```

---

## 4. Périmètre autorisé

Namespace applicatif :

```text
lab-k8s
```

Application :

```text
blog-back
```

Deployments autorisés :

```text
blog-back-fpm
blog-back-nginx
```

Worker applicatif :

```text
rke2-worker-1
```

Label du worker applicatif :

```text
workload-role=app
```

---

## 5. Droits autorisés

### Lecture exploitation

Le profil peut lire :

```text
nodes
namespaces
pods
pods/log
services
endpoints
events
configmaps
persistentvolumeclaims
deployments
replicasets
statefulsets
daemonsets
jobs
cronjobs
ingresses
networkpolicies
endpointslices
metrics pods
metrics nodes
```

Exemples :

```bash
kubectl get nodes
kubectl -n lab-k8s get pods -o wide
kubectl -n lab-k8s get deploy
kubectl -n lab-k8s get events --sort-by=.lastTimestamp
kubectl -n lab-k8s logs deployment/blog-back-fpm
kubectl -n lab-k8s logs deployment/blog-back-nginx
```

---

### Lecture Argo CD et monitoring

Lecture autorisée dans `argocd` :

```text
applications.argoproj.io
appprojects.argoproj.io
```

Lecture autorisée dans `monitoring` :

```text
prometheusrules
servicemonitors
podmonitors
prometheuses
alertmanagers
```

Exemples :

```bash
kubectl -n argocd get applications
kubectl -n monitoring get prometheusrules
```

---

## 6. Actions de maintenance autorisées

Le profil peut agir uniquement sur ces deployments :

```text
deployment/blog-back-fpm
deployment/blog-back-nginx
```

Actions autorisées :

```text
patch deployment/blog-back-fpm
patch deployment/blog-back-nginx
get/patch/update deployment/blog-back-fpm scale
get/patch/update deployment/blog-back-nginx scale
```

### Redémarrer FPM

```bash
kubectl -n lab-k8s rollout restart deployment/blog-back-fpm
kubectl -n lab-k8s rollout status deployment/blog-back-fpm --timeout=180s
kubectl -n lab-k8s get pods -o wide
```

### Redémarrer Nginx

```bash
kubectl -n lab-k8s rollout restart deployment/blog-back-nginx
kubectl -n lab-k8s rollout status deployment/blog-back-nginx --timeout=180s
kubectl -n lab-k8s get pods -o wide
```

### Remettre les replicas attendus

Dans ce lab, les deployments applicatifs sont normalement à :

```text
replicas=1
```

Commandes :

```bash
kubectl -n lab-k8s scale deployment/blog-back-fpm --replicas=1
kubectl -n lab-k8s scale deployment/blog-back-nginx --replicas=1
```

---

## 7. Droits interdits

Le profil ne peut pas :

```text
lire les secrets
lire ou modifier les ServiceAccounts
lire ou modifier les Roles / RoleBindings
lire ou modifier les ClusterRoles / ClusterRoleBindings
créer ou supprimer des pods
exécuter une commande dans un pod avec pods/exec
créer, patcher ou supprimer des Jobs
créer, patcher ou supprimer des CronJobs
modifier PostgreSQL
supprimer des PVC
accéder librement à kube-system
modifier rke2-canal
redémarrer rke2-agent ou rke2-server
faire de la restauration PostgreSQL
être cluster-admin
```

---

## 8. PostgreSQL

Le profil peut observer certains objets PostgreSQL pour diagnostic, mais ne peut pas les modifier.

Interdit :

```text
restore PostgreSQL
backup manuel
patch job de restore
create/delete jobs
patch statefulset PostgreSQL
update statefulset PostgreSQL
delete PVC
pods/exec dans PostgreSQL
```

Décision :

```text
restauration PostgreSQL = admin uniquement
```

La restauration BDD reste réservée à `masterdevops`.

---

## 9. Canal / CNI

Le profil `maintenance-monitoring` ne répare pas Canal/Calico.

Il peut constater qu’un pod applicatif est bloqué, mais la réparation infrastructure reste réservée à `masterdevops`.

Interdit :

```text
kube-system
daemonset/rke2-canal
delete pod rke2-canal
restart rke2-agent
restart rke2-server
sudo sur les nodes
```

---

## 10. Scénario réel validé

Un scénario réel a été validé pendant la mise en place du profil.

### Action déclenchée par maintenance-monitoring

Commande exécutée :

```bash
kubectl -n lab-k8s rollout restart deployment/blog-back-fpm
```

Le nouveau pod FPM est resté bloqué :

```text
blog-back-fpm-89856bb54-xvpg4
STATUS=ContainerCreating
IP=<none>
NODE=rke2-worker-1
```

Le rollout a expiré :

```text
error: timed out waiting for the condition
```

### Diagnostic

Le diagnostic initial a indiqué :

```text
DIAGNOSTIC_PROBABLE=POD_ERROR_OTHER
RECOMMANDATION=inspecter les events du pod concerné avant action Canal
```

L’inspection du pod a confirmé une panne CNI :

```text
FailedCreatePodSandBox
plugin type="calico" failed (add)
error getting ClusterInformation: connection is unauthorized: Unauthorized
```

### Escalade admin

La réparation a été faite par `masterdevops` avec :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-1 --execute
```

Résultat :

```text
ancien pod Canal : rke2-canal-8nr4c
nouveau pod Canal : rke2-canal-drwqx
READY=2/2
STATUS=Running
RESTARTS=0
```

Le pod FPM a ensuite démarré :

```text
blog-back-fpm-89856bb54-xvpg4
READY=1/1
STATUS=Running
IP=10.42.1.111
NODE=rke2-worker-1
```

Validation finale :

```text
deployment "blog-back-fpm" successfully rolled out
HTTP/1.1 200 OK
DIAGNOSTIC_PROBABLE=NONE
AUCUN_POD_BLOQUE_DETECTE=OK
```

Conclusion :

```text
maintenance-monitoring peut déclencher une maintenance applicative contrôlée.
Si la panne est Canal/CNI, l’escalade vers masterdevops est obligatoire.
```

---

## 11. Règle de décision en incident

### Problème applicatif simple

Exemples :

```text
pod applicatif à redémarrer
rollout à vérifier
logs à consulter
replicas à remettre à 1
```

Action :

```text
maintenance-monitoring peut intervenir
```

### Problème image / registry

Symptômes :

```text
ImagePullBackOff
ErrImagePull
failed to pull image
Docker Hub 500
tag image absent
```

Action :

```text
vérifier image, tag, registry, Docker Hub, imagePullPolicy
ne pas réparer Canal en premier
```

### Problème Canal/CNI

Symptômes :

```text
FailedCreatePodSandBox
plugin type="calico"
ClusterInformation unauthorized
pod bloqué ContainerCreating avec IP=<none>
```

Action :

```text
maintenance-monitoring ne répare pas Canal
escalade vers masterdevops
masterdevops utilise repair-canal-node.py si confirmé
```

---

## 12. Script de validation RBAC

Script créé :

```text
scripts/rbac/test-maintenance-monitoring-rbac.sh
```

Résultat obtenu :

```text
PASS=29
FAIL=0
```

Tests positifs validés :

```text
get nodes
list pods lab-k8s
get pods/log lab-k8s
list Argo CD applications
list PrometheusRules monitoring
patch deployment blog-back-fpm
patch deployment blog-back-nginx
get/patch/update scale blog-back-fpm
get/patch/update scale blog-back-nginx
```

Tests négatifs validés :

```text
get secrets = no
list roles = no
list rolebindings = no
list clusterroles = no
list serviceaccounts = no
delete pods = no
create pods/exec = no
create jobs = no
patch jobs = no
delete jobs = no
patch PostgreSQL statefulset = no
update PostgreSQL statefulset = no
delete pvc = no
list pods kube-system = no
patch rke2-canal daemonset = no
patch autre deployment PostgreSQL = no
```

---

## 13. Limite du RBAC Kubernetes

Le droit :

```text
patch deployment/blog-back-fpm
patch deployment/blog-back-nginx
```

permet le `rollout restart`.

Mais Kubernetes RBAC ne limite pas finement le `patch` uniquement à l’annotation de restart.

Ce profil doit donc être présenté comme :

```text
maintenance applicative contrôlée
```

et non comme :

```text
restart-only strict
```

Pour un contrôle plus strict, il faudrait ajouter une couche complémentaire :

```text
script contrôlé
admission policy
OPA/Gatekeeper
Kyverno
outil d’orchestration interne
```

---

## 14. Conclusion

Le profil `maintenance-monitoring` valide une séparation claire des responsabilités :

```text
technicien-monitoring
→ lecture seule

maintenance-monitoring
→ lecture exploitation
→ restart/scale contrôlé FPM et Nginx

masterdevops
→ administration complète
→ réparation Canal/CNI
→ restauration PostgreSQL
```

Le scénario réel a confirmé le bon modèle :

```text
maintenance-monitoring intervient sur l’application
masterdevops intervient sur l’infrastructure
```
