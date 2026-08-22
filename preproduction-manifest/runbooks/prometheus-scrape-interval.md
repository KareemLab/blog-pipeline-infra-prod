# Runbook — Gestion temporaire de l’intervalle de scrape Prometheus

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/stress/prometheus-scrape-interval.sh
```

Ce script sert à consulter ou modifier temporairement l’intervalle global de
collecte de Prometheus pendant les tests de charge applicatifs.

Dans le lab, les deux intervalles utilisés sont :

```text
5s  : intervalle temporaire pendant les tests de charge
30s : intervalle normal à restaurer après les tests
```

L’intervalle de `5s` permet d’obtenir davantage de points de mesure dans Grafana
pendant un test court.

L’intervalle de `30s` limite la charge normale de collecte lorsque les tests sont
terminés.

---

## 2. Emplacement du script

Depuis le bastion :

```bash
cd /home/masterdevops/rke2-lab
```

Le script est ici :

```bash
scripts/stress/prometheus-scrape-interval.sh
```

Il peut être exécuté directement :

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

ou explicitement avec Bash :

```bash
bash scripts/stress/prometheus-scrape-interval.sh status
```

---

## 3. Ressource Kubernetes modifiée

Le script agit sur la ressource Prometheus gérée par le Prometheus Operator.

Valeurs par défaut :

```text
Namespace  : monitoring
Prometheus : kube-prometheus-stack-prometheus
```

La ressource ciblée est équivalente à :

```bash
kubectl -n monitoring get prometheus kube-prometheus-stack-prometheus
```

Le champ consulté ou modifié est :

```text
.spec.scrapeInterval
```

Le script ne modifie pas directement un fichier YAML du dépôt.

Il applique un patch sur la ressource présente dans le cluster.

---

## 4. Périmètre de sécurité

Les actions `test` et `restore` fonctionnent en simulation par défaut.

Sans `--execute`, le script :

```text
- lit l’intervalle actuel ;
- prépare le patch ;
- réalise un dry-run côté serveur Kubernetes ;
- n’enregistre aucune modification dans le cluster.
```

Une modification réelle n’est effectuée que lorsque `--execute` est utilisé.

Exemple :

```bash
./scripts/stress/prometheus-scrape-interval.sh test --execute
```

Avant chaque modification réelle, le script effectue obligatoirement :

```text
--dry-run=server
```

Cela permet à l’API Kubernetes de valider le patch avant son application.

---

## 5. Avertissement important

L’intervalle de `5s` doit rester temporaire.

Un intervalle plus court augmente notamment :

```text
- le nombre de collectes ;
- les requêtes vers les targets ;
- le volume de séries stockées ;
- l’activité CPU de Prometheus ;
- les entrées/sorties disque ;
- la consommation de stockage dans le temps.
```

Après les tests, il faut toujours restaurer l’intervalle normal :

```bash
./scripts/stress/prometheus-scrape-interval.sh restore --execute
```

Puis vérifier :

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

Résultat attendu :

```text
SCRAPE_INTERVAL=30s
```

---

## 6. Prérequis

Le bastion doit disposer de :

```text
- kubectl ;
- un kubeconfig fonctionnel ;
- un contexte pointant vers le cluster RKE2 ;
- un accès en lecture à la ressource Prometheus ;
- un accès patch pour les actions avec --execute.
```

Vérifier le contexte Kubernetes :

```bash
kubectl config current-context
```

Vérifier la ressource Prometheus :

```bash
kubectl -n monitoring get prometheus
```

Vérifier la valeur actuelle sans passer par le script :

```bash
kubectl -n monitoring get prometheus \
  kube-prometheus-stack-prometheus \
  -o jsonpath='{.spec.scrapeInterval}{"\n"}'
```

---

## 7. Afficher l’aide

Commande :

```bash
./scripts/stress/prometheus-scrape-interval.sh --help
```

Aide attendue :

```text
Usage: scripts/stress/prometheus-scrape-interval.sh \
{status|test|restore} [--execute]
```

Actions disponibles :

| Action | Effet |
|---|---|
| `status` | Affiche l’intervalle actuel sans modification. |
| `test` | Simule le passage temporaire à `5s`. |
| `test --execute` | Applique réellement l’intervalle temporaire de `5s`. |
| `restore` | Simule le retour à l’intervalle normal de `30s`. |
| `restore --execute` | Applique réellement le retour à `30s`. |

---

## 8. Arguments du script

Le script utilise des arguments positionnels.

Syntaxe :

```text
prometheus-scrape-interval.sh ACTION [MODE_EXECUTION]
```

| Position | Valeur | Rôle |
|---:|---|---|
| 1 | `status`, `test` ou `restore` | Action à effectuer. |
| 2 | `--execute` | Autorise une modification réelle. |
| aucune | aucune | L’action par défaut est `status`. |

Le seul mode d’exécution accepté en deuxième position est :

```text
--execute
```

Toute autre valeur en deuxième position provoque une erreur.

Exemple invalide :

```bash
./scripts/stress/prometheus-scrape-interval.sh test --apply
```

Sortie attendue :

```text
ERREUR: option inconnue: --apply
```

---

## 9. Variables d’environnement

Le script accepte trois variables d’environnement.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `KUBECTL_BIN` | `kubectl` | Commande kubectl à utiliser. |
| `NAMESPACE` | `monitoring` | Namespace de la ressource Prometheus. |
| `PROMETHEUS_NAME` | `kube-prometheus-stack-prometheus` | Nom de la ressource Prometheus. |

Ces variables permettent d’utiliser le même script sur un autre environnement
sans modifier son code.

---

## 10. Toutes les façons d’appeler le script

## 10.1 Afficher le statut actuel

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

Exemple après restauration :

```text
SCRAPE_INTERVAL=30s
```

Cette action ne modifie rien.

---

## 10.2 Utiliser l’action par défaut

Sans argument :

```bash
./scripts/stress/prometheus-scrape-interval.sh
```

Le script utilise automatiquement :

```text
ACTION=status
```

Le résultat est donc identique à :

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

---

## 10.3 Simuler le passage à 5 secondes

```bash
./scripts/stress/prometheus-scrape-interval.sh test
```

Le script :

```text
1. lit l’intervalle actuel ;
2. définit la cible à 5s ;
3. présente les valeurs actuelle et cible ;
4. valide le patch avec --dry-run=server ;
5. quitte sans modifier la ressource.
```

Exemple de sortie :

```text
PROMETHEUS=kube-prometheus-stack-prometheus
INTERVALLE_ACTUEL=30s
INTERVALLE_CIBLE=5s
prometheus.monitoring.coreos.com/kube-prometheus-stack-prometheus
MODE=SIMULATION
AUCUNE_MODIFICATION_EFFECTUEE
```

---

## 10.4 Appliquer temporairement 5 secondes

Après validation de la simulation :

```bash
./scripts/stress/prometheus-scrape-interval.sh test --execute
```

Cette commande modifie réellement :

```text
spec.scrapeInterval = 5s
```

Sortie attendue :

```text
PROMETHEUS=kube-prometheus-stack-prometheus
INTERVALLE_ACTUEL=30s
INTERVALLE_CIBLE=5s
prometheus.monitoring.coreos.com/kube-prometheus-stack-prometheus
prometheus.monitoring.coreos.com/kube-prometheus-stack-prometheus patched
INTERVALLE_APRES=5s
VERIFICATION=OK
```

Vérification indépendante :

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

Résultat attendu :

```text
SCRAPE_INTERVAL=5s
```

---

## 10.5 Simuler le retour à 30 secondes

```bash
./scripts/stress/prometheus-scrape-interval.sh restore
```

Le script prépare la cible :

```text
INTERVALLE_CIBLE=30s
```

Il effectue le dry-run serveur mais ne modifie pas la ressource.

Exemple de fin de sortie :

```text
MODE=SIMULATION
AUCUNE_MODIFICATION_EFFECTUEE
```

---

## 10.6 Restaurer réellement 30 secondes

```bash
./scripts/stress/prometheus-scrape-interval.sh restore --execute
```

Cette commande restaure réellement :

```text
spec.scrapeInterval = 30s
```

Exemple observé dans le lab :

```text
PROMETHEUS=kube-prometheus-stack-prometheus
INTERVALLE_ACTUEL=5s
INTERVALLE_CIBLE=30s
prometheus.monitoring.coreos.com/kube-prometheus-stack-prometheus
prometheus.monitoring.coreos.com/kube-prometheus-stack-prometheus patched
INTERVALLE_APRES=30s
VERIFICATION=OK
```

---

## 10.7 Utiliser un autre binaire kubectl

Exemple avec l’alias réel remplacé par une commande spécifique :

```bash
KUBECTL_BIN=/usr/local/bin/kubectl \
  ./scripts/stress/prometheus-scrape-interval.sh status
```

`KUBECTL_BIN` doit désigner une commande exécutable compatible avec kubectl.

---

## 10.8 Utiliser un autre namespace

```bash
NAMESPACE=observability \
  ./scripts/stress/prometheus-scrape-interval.sh status
```

Cette commande recherche la ressource Prometheus dans :

```text
observability
```

---

## 10.9 Utiliser un autre nom de ressource Prometheus

```bash
PROMETHEUS_NAME=prometheus-main \
  ./scripts/stress/prometheus-scrape-interval.sh status
```

Les variables peuvent être combinées :

```bash
NAMESPACE=observability \
PROMETHEUS_NAME=prometheus-main \
  ./scripts/stress/prometheus-scrape-interval.sh status
```

---

## 11. Fonctionnement interne du script

## 11.1 Mode strict Bash

Le script commence par :

```bash
set -euo pipefail
```

Cela signifie notamment :

```text
- arrêt lorsqu’une commande échoue ;
- erreur lorsqu’une variable non définie est utilisée ;
- propagation des erreurs dans les pipelines.
```

Une erreur kubectl interrompt donc le script.

---

## 11.2 Lecture de l’intervalle

La fonction `get_interval` exécute :

```bash
kubectl -n "$NAMESPACE" get prometheus "$PROMETHEUS_NAME" \
  -o jsonpath='{.spec.scrapeInterval}'
```

La valeur lue est utilisée pour :

```text
SCRAPE_INTERVAL
INTERVALLE_ACTUEL
INTERVALLE_APRES
```

---

## 11.3 Construction du patch

Pour l’action `test`, la cible est :

```text
5s
```

Pour l’action `restore`, la cible est :

```text
30s
```

Le patch JSON construit est équivalent à :

```json
{
  "spec": {
    "scrapeInterval": "5s"
  }
}
```

ou :

```json
{
  "spec": {
    "scrapeInterval": "30s"
  }
}
```

Le patch utilise le type :

```text
merge
```

---

## 11.4 Dry-run serveur obligatoire

Avant toute action réelle, le script exécute :

```bash
kubectl patch prometheus \
  --type=merge \
  --patch '<PATCH_JSON>' \
  --dry-run=server \
  -o name
```

Le dry-run serveur vérifie que la ressource, le patch et les permissions sont
acceptés par l’API Kubernetes sans enregistrer la modification.

---

## 11.5 Application réelle

Lorsque le deuxième argument est :

```text
--execute
```

le même patch est appliqué sans `--dry-run=server`.

Le script relit ensuite immédiatement :

```text
.spec.scrapeInterval
```

Si la valeur obtenue ne correspond pas à la cible, le script retourne une erreur.

---

## 12. Procédure recommandée pour un test de charge

## 12.1 Vérifier l’état initial

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

État normal attendu :

```text
SCRAPE_INTERVAL=30s
```

---

## 12.2 Simuler le passage à 5 secondes

```bash
./scripts/stress/prometheus-scrape-interval.sh test
```

Vérifier :

```text
INTERVALLE_CIBLE=5s
MODE=SIMULATION
AUCUNE_MODIFICATION_EFFECTUEE
```

---

## 12.3 Appliquer 5 secondes

```bash
./scripts/stress/prometheus-scrape-interval.sh test --execute
```

Vérifier :

```text
INTERVALLE_APRES=5s
VERIFICATION=OK
```

---

## 12.4 Vérifier avant le stress test

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

Résultat attendu :

```text
SCRAPE_INTERVAL=5s
```

Le test de charge peut ensuite être lancé.

---

## 12.5 Simuler la restauration après le test

```bash
./scripts/stress/prometheus-scrape-interval.sh restore
```

Vérifier :

```text
INTERVALLE_CIBLE=30s
MODE=SIMULATION
AUCUNE_MODIFICATION_EFFECTUEE
```

---

## 12.6 Restaurer l’intervalle normal

```bash
./scripts/stress/prometheus-scrape-interval.sh restore --execute
```

Vérifier :

```text
INTERVALLE_APRES=30s
VERIFICATION=OK
```

---

## 12.7 Contrôle final obligatoire

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

Résultat attendu :

```text
SCRAPE_INTERVAL=30s
```

---

## 13. Lecture des sorties

| Sortie | Interprétation |
|---|---|
| `SCRAPE_INTERVAL` | Intervalle actuellement configuré. |
| `PROMETHEUS` | Nom de la ressource Prometheus ciblée. |
| `INTERVALLE_ACTUEL` | Valeur lue avant le patch. |
| `INTERVALLE_CIBLE` | Valeur demandée par l’action. |
| `MODE=SIMULATION` | Aucun patch réel n’a été appliqué. |
| `AUCUNE_MODIFICATION_EFFECTUEE` | Confirmation du mode sans `--execute`. |
| `INTERVALLE_APRES` | Valeur relue après le patch réel. |
| `VERIFICATION=OK` | La valeur appliquée correspond à la cible. |

---

## 14. Codes de sortie

| Code | Signification |
|---:|---|
| `0` | Statut lu, simulation validée ou modification vérifiée. |
| `1` | L’intervalle relu après modification ne correspond pas à la cible. |
| `2` | Action inconnue ou option d’exécution inconnue. |
| autre non nul | Une commande kubectl a échoué et son code peut être propagé par le mode strict Bash. |

Exemple d’action inconnue :

```bash
./scripts/stress/prometheus-scrape-interval.sh enable
```

Sortie attendue :

```text
Usage: scripts/stress/prometheus-scrape-interval.sh \
{status|test|restore} [--execute]
```

---

## 15. Vérification indépendante avec kubectl

Consulter directement la ressource :

```bash
kubectl -n monitoring get prometheus \
  kube-prometheus-stack-prometheus \
  -o yaml
```

Afficher uniquement l’intervalle :

```bash
kubectl -n monitoring get prometheus \
  kube-prometheus-stack-prometheus \
  -o jsonpath='{.spec.scrapeInterval}{"\n"}'
```

Vérifier que l’objet existe :

```bash
kubectl -n monitoring get prometheus \
  kube-prometheus-stack-prometheus \
  -o name
```

---

## 16. Résultat final observé dans le lab

Après la campagne de tests de charge, la restauration a été réalisée avec :

```bash
./scripts/stress/prometheus-scrape-interval.sh restore --execute
```

Résultat observé :

```text
INTERVALLE_ACTUEL=5s
INTERVALLE_CIBLE=30s
INTERVALLE_APRES=30s
VERIFICATION=OK
```

Contrôle final :

```bash
./scripts/stress/prometheus-scrape-interval.sh status
```

Résultat :

```text
SCRAPE_INTERVAL=30s
```

L’état normal du lab est donc :

```text
Prometheus scrape interval = 30s
```

---

## 17. Scripts associés

Le changement temporaire d’intervalle est utilisé avec les scripts :

```text
scripts/stress/blog-create-articles-stress.py
scripts/stress/blog-clean-stress-articles.py
scripts/stress/resolve-blog-ingress-ip.sh
```

Runbooks associés :

```text
runbooks/blog-create-articles-stress.md
runbooks/blog-clean-stress-articles.md
```

---

## 18. Résumé opérationnel

Avant le test :

```bash
./scripts/stress/prometheus-scrape-interval.sh status
./scripts/stress/prometheus-scrape-interval.sh test
./scripts/stress/prometheus-scrape-interval.sh test --execute
./scripts/stress/prometheus-scrape-interval.sh status
```

Après le test :

```bash
./scripts/stress/prometheus-scrape-interval.sh restore
./scripts/stress/prometheus-scrape-interval.sh restore --execute
./scripts/stress/prometheus-scrape-interval.sh status
```

État final obligatoire :

```text
SCRAPE_INTERVAL=30s
```
