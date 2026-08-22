# Runbook — Accès Kubernetes limité du technicien monitoring

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/rbac/technicien-monitoring-access.py
```

Ce script facilite l’administration de l’accès Kubernetes limité du compte :

```text
technicien-monitoring
```

Il permet à l’administrateur DevOps de vérifier, tester et renouveler l’accès Kubernetes du technicien sans lui donner le kubeconfig admin.

---

## 2. Modèle d’accès

Le technicien utilise deux accès différents.

### 2.1 Accès au bastion Linux

```text
Utilisateur Linux : technicien-monitoring
Mot de passe      : défini par l’administrateur
```

Ce mot de passe sert uniquement à ouvrir une session sur le bastion.

### 2.2 Accès Kubernetes

```text
Kubeconfig limité    : /home/technicien-monitoring/.kube/config
Identité Kubernetes  : system:serviceaccount:monitoring:technicien-monitoring
Namespace par défaut : monitoring
RBAC                 : lecture seule contrôlée
```

Kubernetes n’utilise pas le mot de passe Linux du bastion.

Kubernetes utilise un token temporaire présent dans le kubeconfig limité du technicien.

---

## 3. Fichiers concernés

Script d’administration :

```bash
scripts/rbac/technicien-monitoring-access.py
```

Manifest RBAC :

```bash
rbac/technicien-monitoring-readonly.yaml
```

Kubeconfig admin :

```text
/home/masterdevops/.kube/config.yaml
```

Kubeconfig limité du technicien :

```text
/home/technicien-monitoring/.kube/config
```

Le kubeconfig admin n’est jamais copié vers le technicien.

Le script reprend seulement depuis le kubeconfig admin :

```text
- l’adresse de l’API Kubernetes ;
- le certificat CA du cluster.
```

Le token du technicien est généré séparément par Kubernetes pour le ServiceAccount :

```text
monitoring/technicien-monitoring
```

---

## 4. Périmètre de sécurité

Le technicien ne doit pas avoir :

```text
- accès sudo ;
- accès au dépôt Git ;
- accès au kubeconfig admin ;
- accès aux Secrets Kubernetes ;
- accès aux objets RBAC Kubernetes ;
- droit de création, modification ou suppression ;
- droit pods/exec ;
- droit de backup ou restauration PostgreSQL.
```

Le script ne doit jamais afficher le token Kubernetes.

L’action de renouvellement est en simulation par défaut.

Une modification réelle nécessite explicitement :

```text
--execute
```

---

## 5. Prérequis

Le bastion doit disposer de :

```text
- Python 3 ;
- kubectl ;
- sudo pour l’administrateur DevOps ;
- un kubeconfig admin fonctionnel pour masterdevops ;
- le compte Linux technicien-monitoring ;
- le ServiceAccount Kubernetes monitoring/technicien-monitoring ;
- le RBAC technicien-monitoring déjà appliqué.
```

Vérifier le contexte Kubernetes côté admin :

```bash
kubectl config current-context
```

Vérifier le ServiceAccount :

```bash
kubectl -n monitoring get serviceaccount technicien-monitoring
```

Vérifier le compte Linux :

```bash
id technicien-monitoring
```

---

## 6. Point important — variable KUBECONFIG admin

Le script est lancé par l’administrateur DevOps depuis le compte :

```text
masterdevops
```

Pour que les commandes `kubectl` administrateur fonctionnent, la variable `KUBECONFIG` de la session doit pointer vers le kubeconfig admin :

```text
/home/masterdevops/.kube/config.yaml
```

Avant d’utiliser le script, vérifier :

```bash
echo "$KUBECONFIG"
kubectl config current-context
```

Résultat attendu :

```text
/home/masterdevops/.kube/config.yaml
default
```

Si `KUBECONFIG` vaut autre chose, par exemple :

```text
OK
```

ou si `kubectl` affiche :

```text
error: current-context is not set
https://localhost:8080
```

alors la session shell est polluée ou mal configurée.

Réparer la session avec :

```bash
export KUBECONFIG=/home/masterdevops/.kube/config.yaml
cd /home/masterdevops/rke2-lab
kubectl config current-context
```

Résultat attendu :

```text
default
```

Ensuite seulement, relancer le script :

```bash
./scripts/rbac/technicien-monitoring-access.py status
```

Attention : ne jamais coller dans le terminal les sorties affichées par le script, comme :

```text
OWNER=technicien-monitoring GROUP=technicien-monitoring MODE=600
VERIFICATION=OK
MODE=SIMULATION
```

Ces lignes sont des résultats, pas des commandes.

Il faut copier uniquement les blocs de commandes Bash documentés dans ce runbook.

---

## 7. Afficher l’aide

Commande :

```bash
./scripts/rbac/technicien-monitoring-access.py --help
```

Actions disponibles :

| Action | Effet |
|---|---|
| `status` | Affiche l’état du compte et du kubeconfig technicien. |
| `show-config` | Affiche le kubeconfig avec le token masqué. |
| `test` | Teste les droits Kubernetes du technicien. |
| `renew` | Simule un renouvellement de token. |
| `renew --execute` | Génère un nouveau token et met à jour le kubeconfig. |

---

## 8. Vérifier l’état

Commande :

```bash
./scripts/rbac/technicien-monitoring-access.py status
```

Résultat attendu :

```text
TECH_USER=technicien-monitoring
TECH_HOME=/home/technicien-monitoring
KUBE_CONFIG=/home/technicien-monitoring/.kube/config
NAMESPACE=monitoring
SERVICE_ACCOUNT=technicien-monitoring
LINUX_USER=OK
SERVICE_ACCOUNT=OK
KUBECONFIG=OK
OWNER=technicien-monitoring GROUP=technicien-monitoring MODE=600
TOKEN_ISSUED_AT_UTC=2026-06-29T12:54:19Z
TOKEN_EXPIRES_AT_UTC=2026-07-29T12:54:19Z
TOKEN_REMAINING=29d 23h 56m 40s
```

Les dates exactes dépendent du dernier renouvellement du token.

Cette commande ne modifie rien et n’affiche jamais le token.

---

## 9. Comprendre l’expiration du token

Le kubeconfig limité du technicien contient un token Kubernetes temporaire.

Le script ne montre jamais ce token, mais il peut lire ses métadonnées d’expiration.

Champs affichés par `status` :

| Champ | Rôle |
|---|---|
| `TOKEN_ISSUED_AT_UTC` | Date de création du token en UTC. |
| `TOKEN_EXPIRES_AT_UTC` | Date d’expiration du token en UTC. |
| `TOKEN_REMAINING` | Durée restante avant expiration. |

Exemple :

```text
TOKEN_ISSUED_AT_UTC=2026-06-29T12:54:19Z
TOKEN_EXPIRES_AT_UTC=2026-07-29T12:54:19Z
TOKEN_REMAINING=29d 23h 56m 40s
```

Si `TOKEN_REMAINING` indique :

```text
EXPIRED
```

alors l’administrateur DevOps doit renouveler le token :

```bash
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h --execute
```

Le renouvellement reconstruit le kubeconfig limité avec un nouveau token temporaire, sans afficher ce token.

---

## 10. Afficher le kubeconfig sans token

Commande :

```bash
./scripts/rbac/technicien-monitoring-access.py show-config
```

Le token doit être masqué :

```text
token: ***REDACTED***
```

Ne jamais copier le token réel dans :

```text
- Git ;
- un ticket ;
- une documentation ;
- une capture publique ;
- un compte rendu ;
- une conversation.
```

---

## 11. Tester les droits du technicien

Commande :

```bash
./scripts/rbac/technicien-monitoring-access.py test
```

Tests autorisés attendus :

```text
get nodes
get pods -n monitoring
```

Tests interdits attendus :

```text
get secrets -n monitoring
get pods -n kube-system
```

Résultat final attendu :

```text
SECRET_FORBIDDEN=OK
KUBE_SYSTEM_FORBIDDEN=OK
VERIFICATION=OK
```

Cette commande permet de prouver que le technicien peut observer le cluster mais ne peut pas accéder aux zones sensibles.

---

## 12. Simuler un renouvellement de token

Commande :

```bash
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h
```

Cette commande ne génère pas de token et ne modifie pas le kubeconfig.

Résultat attendu :

```text
MODE=SIMULATION
AUCUN_TOKEN_GENERE
AUCUNE_MODIFICATION_EFFECTUEE
```

Le script indique aussi la commande à utiliser pour appliquer réellement le renouvellement.

---

## 13. Renouveler réellement l’accès Kubernetes

Commande :

```bash
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h --execute
```

Cette commande :

```text
1. vérifie le compte Linux technicien-monitoring ;
2. vérifie le ServiceAccount Kubernetes ;
3. récupère l’adresse de l’API Kubernetes ;
4. récupère le certificat CA du cluster ;
5. génère un nouveau token temporaire ;
6. reconstruit le kubeconfig limité ;
7. écrit /home/technicien-monitoring/.kube/config ;
8. applique les droits 600 ;
9. applique le propriétaire technicien-monitoring ;
10. relance les tests d’accès.
```

Résultat attendu :

```text
KUBECONFIG_UPDATED=OK
OWNER=technicien-monitoring GROUP=technicien-monitoring MODE=600
SECRET_FORBIDDEN=OK
KUBE_SYSTEM_FORBIDDEN=OK
VERIFICATION=OK
```

Après renouvellement, vérifier l’expiration :

```bash
./scripts/rbac/technicien-monitoring-access.py status
```

Résultat attendu :

```text
TOKEN_EXPIRES_AT_UTC=<date UTC future>
TOKEN_REMAINING=<durée restante>
```

---

## 14. Durées possibles

Exemples :

```bash
./scripts/rbac/technicien-monitoring-access.py renew --duration 24h
./scripts/rbac/technicien-monitoring-access.py renew --duration 168h
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h
```

Correspondance :

```text
24h  = 1 jour
168h = 7 jours
720h = 30 jours
```

Dans le lab, la durée recommandée pour démonstration est :

```text
720h
```

---

## 15. Variables d’environnement

Le script peut être adapté avec des variables d’environnement.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `KUBECTL_BIN` | `kubectl` | Commande kubectl à utiliser. |
| `NAMESPACE` | `monitoring` | Namespace du ServiceAccount. |
| `SERVICE_ACCOUNT` | `technicien-monitoring` | ServiceAccount Kubernetes. |
| `TECH_USER` | `technicien-monitoring` | Compte Linux du technicien. |
| `TECH_HOME` | `/home/technicien-monitoring` | Home du technicien. |
| `KUBE_CONFIG` | `/home/technicien-monitoring/.kube/config` | Kubeconfig limité. |
| `CLUSTER_ALIAS` | `rke2-lab` | Nom local du cluster dans le kubeconfig. |
| `DEFAULT_DURATION` | `720h` | Durée par défaut du token. |

Exemple :

```bash
DEFAULT_DURATION=168h ./scripts/rbac/technicien-monitoring-access.py renew
```

---

## 16. Vérifications indépendantes

Afficher les droits du kubeconfig :

```bash
sudo stat -c 'OWNER=%U GROUP=%G MODE=%a PATH=%n'   /home/technicien-monitoring/.kube/config
```

Résultat attendu :

```text
OWNER=technicien-monitoring GROUP=technicien-monitoring MODE=600
```

Tester le contexte du technicien :

```bash
sudo -u technicien-monitoring   KUBECONFIG=/home/technicien-monitoring/.kube/config   kubectl config current-context
```

Tester une lecture autorisée :

```bash
sudo -u technicien-monitoring   KUBECONFIG=/home/technicien-monitoring/.kube/config   kubectl get nodes
```

Tester une action interdite :

```bash
sudo -u technicien-monitoring   KUBECONFIG=/home/technicien-monitoring/.kube/config   kubectl get secrets -n monitoring
```

Résultat attendu :

```text
Forbidden
```

---

## 17. Codes de sortie

| Code | Signification |
|---:|---|
| `0` | Action réussie ou simulation validée. |
| `1` | Erreur de prérequis ou vérification non conforme. |
| `2` | Action ou option inconnue. |
| autre non nul | Erreur propagée par Python, sudo ou kubectl. |

---

## 18. Procédure recommandée

Vérifier l’état :

```bash
./scripts/rbac/technicien-monitoring-access.py status
```

Tester les droits :

```bash
./scripts/rbac/technicien-monitoring-access.py test
```

Simuler le renouvellement :

```bash
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h
```

Appliquer uniquement si nécessaire :

```bash
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h --execute
```

Revérifier :

```bash
./scripts/rbac/technicien-monitoring-access.py status
./scripts/rbac/technicien-monitoring-access.py test
```

---

## 19. Phrase de présentation jury

Le technicien monitoring se connecte au bastion avec un compte Linux dédié.

Il n’utilise pas le compte administrateur `masterdevops` et ne reçoit jamais le kubeconfig admin.

Son accès Kubernetes passe par un kubeconfig limité, généré par l’administrateur DevOps, contenant un token temporaire lié au ServiceAccount `monitoring/technicien-monitoring`.

Les droits sont contrôlés par RBAC : lecture utile autorisée, Secrets interdits, modifications interdites, backup et restauration interdits.

---

## 20. Résumé opérationnel

```bash
export KUBECONFIG=/home/masterdevops/.kube/config.yaml
cd /home/masterdevops/rke2-lab

./scripts/rbac/technicien-monitoring-access.py status
./scripts/rbac/technicien-monitoring-access.py show-config
./scripts/rbac/technicien-monitoring-access.py test
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h
./scripts/rbac/technicien-monitoring-access.py renew --duration 720h --execute
./scripts/rbac/technicien-monitoring-access.py status
./scripts/rbac/technicien-monitoring-access.py test
```

État final attendu :

```text
TOKEN_REMAINING=<durée restante>
VERIFICATION=OK
```
