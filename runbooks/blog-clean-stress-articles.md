# Runbook — Nettoyage sécurisé des articles de stress

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/stress/blog-clean-stress-articles.py
```

Ce script sert à identifier puis supprimer les articles créés par les tests de
charge.

Il cible uniquement les articles dont le titre ou le contenu contient :

```text
STRESS:
```

Il protège les articles de référence en vérifiant leur nombre avant et après
le nettoyage.

Dans le lab, la référence attendue est :

```text
3 articles seed
```

---

## 2. Emplacement du script

Depuis le bastion :

```bash
cd /home/masterdevops/rke2-lab
```

Le script est ici :

```bash
scripts/stress/blog-clean-stress-articles.py
```

---

## 3. Périmètre de sécurité

Le script distingue deux groupes :

```text
articles STRESS
articles non-STRESS considérés comme articles seed
```

Un article est classé STRESS lorsque le marqueur suivant apparaît dans son
titre ou son contenu :

```text
STRESS:
```

Le script ne supprime pas les articles non-STRESS.

Avant toute suppression, il vérifie que le nombre d’articles non-STRESS
correspond à :

```text
--expected-seed-count
```

La valeur par défaut est :

```text
3
```

Si le nombre ne correspond pas, le script s’arrête sans supprimer d’article.

---

## 4. Avertissement important

Le nettoyage n’est pas limité à un seul Run ID.

Avec `--execute`, le script supprime tous les articles dont le titre ou le
contenu contient :

```text
STRESS:
```

Cela concerne tous les runs encore présents dans l’application.

Le script ne possède pas actuellement d’option :

```text
--run-id
```

Il faut donc toujours lancer la simulation et contrôler la liste
`CIBLE_STRESS` avant d’utiliser `--execute`.

---

## 5. Fonctionnement par défaut

Sans option `--execute`, le script fonctionne uniquement en simulation.

Il effectue les opérations suivantes :

```text
1. récupère tous les articles ;
2. sépare les articles STRESS et non-STRESS ;
3. vérifie le nombre d’articles seed ;
4. affiche les articles qui seraient supprimés ;
5. quitte sans effectuer de suppression.
```

Sortie attendue :

```text
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
```

---

## 6. Fonctionnement avec execute

Avec l’option :

```text
--execute
```

le script :

```text
1. vérifie le nombre d’articles seed avant nettoyage ;
2. affiche toutes les cibles STRESS ;
3. supprime chaque article STRESS par son identifiant ;
4. récupère à nouveau la liste des articles ;
5. vérifie qu’aucun article STRESS ne subsiste ;
6. vérifie que le nombre d’articles seed est toujours correct.
```

La suppression utilise :

```text
DELETE /api/articles/<ID>
```

Le code HTTP attendu est :

```text
200 OK
```

Tout autre code arrête immédiatement le nettoyage avec une erreur.

---

## 7. Afficher l’aide

```bash
python3 scripts/stress/blog-clean-stress-articles.py --help
```

Cette commande affiche les options supportées par la version actuelle du
script.

---

## 8. Explication des options

| Option | Obligatoire | Valeur par défaut | Rôle |
|---|---:|---|---|
| `-h`, `--help` | non | aucune | Affiche l’aide puis quitte. |
| `--base-url` | oui | aucune | Adresse HTTP de l’application ou de l’ingress. |
| `--host-header` | non | `blog.k8s.test` | Valeur du header HTTP `Host`. |
| `--expected-seed-count` | non | `3` | Nombre d’articles non-STRESS qui doivent être préservés. |
| `--timeout` | non | `30` secondes | Timeout individuel des requêtes GET et DELETE. |
| `--execute` | non | désactivé | Autorise les suppressions réelles. |

Remarque :

```text
--expected-seed-count et --timeout sont interprétés comme des entiers.
Le script ne leur applique pas actuellement le contrôle strictement positif
utilisé par le script de création.
```

---

## 9. Procédure recommandée complète

## 9.1 Se placer dans le dépôt

```bash
cd /home/masterdevops/rke2-lab
```

---

## 9.2 Résoudre l’IP de l’ingress

```bash
INGRESS_IP="$(./scripts/stress/resolve-blog-ingress-ip.sh)"
echo "${INGRESS_IP}"
```

---

## 9.3 Lancer la simulation

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --expected-seed-count 3
```

Vérifier particulièrement :

```text
ARTICLES_STRESS_AVANT
ARTICLES_SEED_AVANT
CIBLE_STRESS
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
```

---

## 9.4 Effectuer le nettoyage réel

Après validation de la simulation :

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --expected-seed-count 3 \
  --execute
```

---

## 9.5 Vérifier le résultat

Sortie finale attendue dans le lab :

```text
ARTICLES_SUPPRIMES=<NOMBRE>
ARTICLES_APRES=3
ARTICLES_STRESS_APRES=0
ARTICLES_SEED_APRES=3
VERIFICATION_SEED=OK
```

---

## 10. Toutes les façons d’appeler le script

## 10.1 Simulation avec les valeurs du lab

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}"
```

Valeurs implicites :

```text
HOST_HEADER=blog.k8s.test
EXPECTED_SEED_COUNT=3
TIMEOUT=30
MODE=SIMULATION
```

---

## 10.2 Simulation explicite

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --expected-seed-count 3 \
  --timeout 30
```

Aucune suppression n’est effectuée.

---

## 10.3 Nettoyage réel

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --expected-seed-count 3 \
  --execute
```

Cette commande supprime réellement toutes les cibles affichées.

---

## 10.4 Utiliser un autre Host HTTP

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.local"
```

La commande reste en simulation tant que `--execute` n’est pas ajouté.

---

## 10.5 Utiliser une autre référence seed

Exemple pour un environnement possédant cinq articles non-STRESS :

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --expected-seed-count 5
```

Ne pas modifier cette valeur uniquement pour contourner une erreur.

Il faut d’abord vérifier pourquoi le nombre d’articles non-STRESS diffère de
la référence attendue.

---

## 10.6 Modifier le timeout

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --expected-seed-count 3 \
  --timeout 45
```

La commande reste en simulation sans `--execute`.

---

## 10.7 Exécuter lorsqu’aucun article STRESS n’existe

En simulation :

```text
ARTICLES_STRESS_AVANT=0
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
```

Avec `--execute`, le script ne supprime rien puis effectue tout de même les
vérifications finales.

Résultat attendu :

```text
ARTICLES_SUPPRIMES=0
ARTICLES_STRESS_APRES=0
VERIFICATION_SEED=OK
```

---

## 11. Lecture des sorties avant nettoyage

| Sortie | Interprétation |
|---|---|
| `ARTICLES_AVANT` | Nombre total d’articles retournés par l’API. |
| `ARTICLES_STRESS_AVANT` | Nombre d’articles portant le marqueur STRESS. |
| `ARTICLES_SEED_AVANT` | Nombre d’articles ne portant pas le marqueur STRESS. |
| `CIBLE_STRESS` | Identifiant et titre d’un article qui serait supprimé. |

Le terme `seed` utilisé par le script signifie ici :

```text
tout article ne contenant pas le marqueur STRESS
```

Le script ne vérifie pas les titres ni les identifiants précis des articles
seed.

---

## 12. Lecture des sorties pendant le nettoyage

Pour chaque article supprimé :

```text
SUPPRIME ID=<IDENTIFIANT>
```

Exemple :

```text
SUPPRIME ID=124
```

Si une suppression retourne un code différent de HTTP 200, le script s’arrête
immédiatement.

Les articles précédemment supprimés restent supprimés ; le script ne réalise
pas de rollback.

---

## 13. Lecture des sorties après nettoyage

| Sortie | Interprétation |
|---|---|
| `ARTICLES_SUPPRIMES` | Nombre de suppressions HTTP réussies. |
| `ARTICLES_APRES` | Nombre total d’articles restant après nettoyage. |
| `ARTICLES_STRESS_APRES` | Nombre d’articles STRESS restant. Doit être égal à zéro. |
| `ARTICLES_SEED_APRES` | Nombre d’articles non-STRESS restant. |
| `VERIFICATION_SEED=OK` | Les contrôles finaux sont validés. |

Dans le lab, l’état propre attendu est :

```text
ARTICLES_APRES=3
ARTICLES_STRESS_APRES=0
ARTICLES_SEED_APRES=3
VERIFICATION_SEED=OK
```

---

## 14. Codes de sortie

| Code | Signification |
|---:|---|
| `0` | Simulation terminée ou nettoyage validé. |
| `1` | Erreur HTTP, réseau ou réponse JSON invalide. |
| `2` | Nombre d’articles seed incorrect avant nettoyage, ou erreur `argparse`. |
| `3` | Article STRESS sans identifiant. |
| `4` | Une requête DELETE n’a pas retourné HTTP 200. |
| `5` | Des articles STRESS existent encore après le nettoyage. |
| `6` | Le nombre d’articles seed a changé après le nettoyage. |

Dans un pipeline CI/CD, un code différent de zéro doit faire échouer le job
de nettoyage.

---

## 15. Exemple après un test de 125 connexions

Test effectué :

```text
125 connexions
3 articles par connexion
375 articles STRESS
```

Simulation attendue :

```text
ARTICLES_AVANT=378
ARTICLES_STRESS_AVANT=375
ARTICLES_SEED_AVANT=3
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
```

Après `--execute` :

```text
ARTICLES_SUPPRIMES=375
ARTICLES_APRES=3
ARTICLES_STRESS_APRES=0
ARTICLES_SEED_APRES=3
VERIFICATION_SEED=OK
```

---

## 16. Erreurs à ne pas contourner

Si le script affiche :

```text
ERREUR: nombre d'articles seed différent de la référence attendue
```

ne pas relancer immédiatement avec une autre valeur.

Il faut d’abord examiner les articles présents dans l’application.

Si le script affiche :

```text
ERREUR: des articles STRESS existent encore
```

vérifier les identifiants et les réponses HTTP avant toute nouvelle tentative.

Si le script s’arrête après plusieurs suppressions réussies, relancer d’abord
le mode simulation afin de connaître l’état restant.

---

## 17. Vérification indépendante

Après le nettoyage :

```bash
curl -fsS \
  --max-time 10 \
  -H "Host: blog.k8s.test" \
  "http://${INGRESS_IP}/api/articles" |
python3 -c '
import json
import sys

articles = json.load(sys.stdin)

stress_articles = [
    article for article in articles
    if "STRESS:" in (article.get("title") or "")
    or "STRESS:" in (article.get("content") or "")
]

print(f"ARTICLES_TOTAUX={len(articles)}")
print(f"ARTICLES_STRESS_TOTAL={len(stress_articles)}")
print(f"ARTICLES_SEED_PRESUMES={len(articles) - len(stress_articles)}")
'
```

État attendu :

```text
ARTICLES_TOTAUX=3
ARTICLES_STRESS_TOTAL=0
ARTICLES_SEED_PRESUMES=3
```

---

## 18. Script associé

Les articles STRESS sont générés par :

```text
scripts/stress/blog-create-articles-stress.py
```

Consulter également :

```text
runbooks/blog-create-articles-stress.md
```
