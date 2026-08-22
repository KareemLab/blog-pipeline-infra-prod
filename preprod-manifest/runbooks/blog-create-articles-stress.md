# Runbook — Création simultanée d’articles de stress

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/stress/blog-create-articles-stress.py
```

Ce script sert à générer une charge HTTP simultanée sur l’application Blog.

Il crée plusieurs articles avec une image par l’intermédiaire de l’API :

```text
POST /api/createArticle
```

Il permet notamment de mesurer :

```text
- le nombre de créations réussies ;
- le nombre d’erreurs ;
- la durée totale du test ;
- le débit en articles par seconde ;
- les latences MIN, P50, P95, P99 et MAX ;
- la durée de chaque connexion simulée.
```

Cas réel utilisé dans le lab :

```text
125 connexions HTTP simultanées
3 articles créés par connexion
375 articles attendus
7 replicas FPM
2 replicas Nginx
```

---

## 2. Emplacement du script

Depuis le bastion :

```bash
cd /home/masterdevops/rke2-lab
```

Le script est ici :

```bash
scripts/stress/blog-create-articles-stress.py
```

L’image utilisée par défaut est :

```bash
uploads-images/gpu-tpu.jpg
```

---

## 3. Périmètre et précautions

Le script écrit réellement dans l’application.

Il crée des articles portant un marqueur identifiable :

```text
[STRESS:<RUN_ID>:C<CONNEXION>:A<ARTICLE>]
```

Exemple :

```text
[STRESS:20260620-194201-99f1bf:C0001:A01]
```

Le marqueur complet `[STRESS:<RUN_ID>:C<CONNEXION>:A<ARTICLE>]` est ajouté au titre et au contenu.

Le nom du fichier image contient également le Run ID, le numéro de connexion et le numéro d’article, sous la forme :

```text
stress-<RUN_ID>-<CONNEXION>-<ARTICLE>.jpg
```

Le nom du fichier image ne contient pas le marqueur exact `STRESS:`.

Le script doit être utilisé sur un environnement de lab ou de préproduction
contrôlé.

Après chaque test, les articles doivent être supprimés avec :

```bash
scripts/stress/blog-clean-stress-articles.py
```

Le script de création ne supprime aucun article existant.

---

## 4. Prérequis

Les éléments suivants doivent être disponibles :

```text
- Python 3 ;
- le module Python requests ;
- une image JPEG lisible ;
- l’API Blog accessible ;
- l’adresse IP de l’ingress ;
- le Host HTTP attendu par l’ingress.
```

Vérification du module `requests` :

```bash
python3 -c 'import requests; print(requests.__version__)'
```

Résolution de l’IP d’ingress dans le lab :

```bash
INGRESS_IP="$(./scripts/stress/resolve-blog-ingress-ip.sh)"
echo "${INGRESS_IP}"
```

Le script de résolution vérifie également que l’application répond avec le
header :

```text
Host: blog.k8s.test
```

---

## 5. Fonctionnement interne

## 5.1 Validation des nombres

Les options suivantes doivent être des entiers strictement supérieurs à zéro :

```text
--connections
--articles-per-connection
--timeout
```

Une valeur nulle ou négative est refusée avant le lancement du test.

---

## 5.2 Chargement de l’image

L’image est lue une seule fois en mémoire avant la création des threads.

Pour chaque article, le script construit ensuite un nouveau fichier multipart
à partir des mêmes octets.

Cela évite de relire l’image sur disque pour chaque requête.

---

## 5.3 Connexions simultanées

Le script utilise :

```text
ThreadPoolExecutor
```

Le nombre maximal de workers Python est égal à la valeur de :

```text
--connections
```

Chaque connexion simulée possède sa propre session HTTP :

```python
requests.Session()
```

Cette session ajoute le header :

```text
Host: blog.k8s.test
```

Toutes les connexions simulées sont lancées en parallèle.

---

## 5.4 Articles créés dans une connexion

À l’intérieur d’une connexion simulée, les articles sont créés
séquentiellement.

Avec :

```text
--articles-per-connection 3
```

la connexion effectue :

```text
création article 1
puis création article 2
puis création article 3
```

La formule du nombre total d’articles attendus est :

```text
articles attendus =
connexions × articles par connexion
```

Exemple :

```text
125 × 3 = 375 articles
```

---

## 5.5 Signification d’une connexion simulée

Une connexion simulée ne représente pas toute la navigation d’un utilisateur.

Elle représente un thread qui crée plusieurs articles successivement, sans
temps humain de lecture, de saisie ou de réflexion.

Le test est donc plus sévère qu’un comportement utilisateur réel.

Un utilisateur réel mettrait du temps pour :

```text
- écrire le titre ;
- saisir le contenu ;
- sélectionner une image ;
- relire l’article ;
- lancer la publication ;
- commencer un autre article.
```

La métrique `CONNEXION_LATENCE` correspond à la durée totale nécessaire pour
créer tous les articles de cette connexion simulée.

---

## 5.6 Requête HTTP

Chaque article est envoyé vers :

```text
<BASE_URL>/api/createArticle
```

Le corps multipart contient :

| Champ | Contenu |
|---|---|
| `title` | Marqueur STRESS, texte de test et date |
| `content` | Marqueur STRESS, date du run et Lorem Ipsum |
| `image` | Fichier JPEG choisi pour le test |

Le code HTTP attendu est :

```text
201 Created
```

Tout autre code HTTP est considéré comme une erreur.

Une erreur réseau est enregistrée, mais le script poursuit les autres
créations prévues.

---

## 5.7 Identifiant du run

Sans option `--run-id`, le script génère automatiquement un identifiant sous
la forme :

```text
AAAAMMJJ-HHMMSS-XXXXXX
```

Exemple :

```text
20260620-194201-99f1bf
```

Cet identifiant permet de retrouver les articles appartenant à un même test.

---

## 6. Afficher l’aide

Commande :

```bash
python3 scripts/stress/blog-create-articles-stress.py --help
```

Cette commande affiche les options supportées par la version actuelle du
script.

---

## 7. Explication des options

| Option | Obligatoire | Valeur par défaut | Rôle |
|---|---:|---|---|
| `-h`, `--help` | non | aucune | Affiche l’aide puis quitte. |
| `--base-url` | oui | aucune | Adresse HTTP de l’application ou de l’ingress. |
| `--host-header` | non | `blog.k8s.test` | Valeur du header HTTP `Host`. |
| `--connections` | oui | aucune | Nombre de connexions simulées lancées en parallèle. |
| `--articles-per-connection` | non | `3` | Nombre d’articles créés séquentiellement par connexion. |
| `--image` | non | `uploads-images/gpu-tpu.jpg` | Image JPEG envoyée avec chaque article. |
| `--run-id` | non | généré automatiquement | Identifiant utilisé dans les marqueurs STRESS. |
| `--timeout` | non | `30` secondes | Timeout individuel de chaque requête HTTP. |
| `--summary-only` | non | désactivé | Masque les lignes de succès individuelles. Les erreurs restent visibles. |

---

## 8. Toutes les façons d’appeler le script

## 8.1 Test minimal

```bash
cd /home/masterdevops/rke2-lab

INGRESS_IP="$(./scripts/stress/resolve-blog-ingress-ip.sh)"

python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 1
```

Résultat attendu :

```text
1 connexion
3 articles
3 succès si l’application fonctionne correctement
```

---

## 8.2 Test avec une seule création par connexion

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 10 \
  --articles-per-connection 1
```

Résultat attendu :

```text
10 connexions
10 articles
```

---

## 8.3 Test de référence du lab

```bash
cd /home/masterdevops/rke2-lab

INGRESS_IP="$(./scripts/stress/resolve-blog-ingress-ip.sh)"

python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --connections 125 \
  --articles-per-connection 3 \
  --summary-only
```

Volume attendu :

```text
CONNEXIONS=125
ARTICLES_PAR_CONNEXION=3
SUCCES=375
ERREURS=0
```

Configuration de référence associée :

```text
7 replicas FPM
2 replicas Nginx
```

---

## 8.4 Affichage détaillé de toutes les requêtes

Ne pas utiliser `--summary-only` :

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 5 \
  --articles-per-connection 3
```

Exemple de ligne :

```text
OK C0001 A01 HTTP=201 DUREE=0.852s
```

Ce mode est utile pour un petit test, mais produit beaucoup de lignes avec un
grand nombre de connexions.

---

## 8.5 Résumé uniquement

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 125 \
  --articles-per-connection 3 \
  --summary-only
```

Effet :

```text
Les requêtes réussies individuelles ne sont pas affichées.
Les erreurs individuelles restent affichées.
Le résumé et les percentiles sont toujours affichés.
```

---

## 8.6 Utiliser une autre image

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 10 \
  --image "/home/masterdevops/rke2-lab/uploads-images/montagne.jpg"
```

Le script vérifie que le fichier existe avant de lancer la charge.

---

## 8.7 Définir manuellement le Run ID

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 10 \
  --run-id "test-preprod-prod-84"
```

Les articles porteront un marqueur similaire à :

```text
[STRESS:test-preprod-prod-84:C0001:A01]
```

Le Run ID doit rester unique pour faciliter la traçabilité.

---

## 8.8 Modifier le timeout

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --connections 125 \
  --timeout 45 \
  --summary-only
```

Le timeout s’applique à chaque requête de création d’article.

---

## 8.9 Utiliser un autre Host HTTP

```bash
python3 scripts/stress/blog-create-articles-stress.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.local" \
  --connections 10
```

Cette option est utile lorsqu’un ingress accepte plusieurs noms d’hôte.

---

## 9. Lecture des résultats

Le résumé principal ressemble à :

```text
===== RESUME =====
RUN_ID=20260620-194201-99f1bf
SUCCES=375
ERREURS=0
DUREE=12.208s
DEBIT=30.72 articles/s
```

| Métrique | Interprétation |
|---|---|
| `SUCCES` | Nombre de créations ayant retourné HTTP 201. |
| `ERREURS` | Nombre de créations en erreur réseau ou avec un autre code HTTP. |
| `DUREE` | Durée totale du test, toutes connexions comprises. |
| `DEBIT` | Nombre de créations réussies divisé par la durée totale. |

`DUREE` ne représente pas la latence d’un utilisateur individuel.

---

## 10. Lecture des latences articles

Exemple :

```text
===== LATENCES ARTICLES SUCCES =====
ARTICLE_SUCCES_LATENCE_COUNT=375
ARTICLE_SUCCES_LATENCE_MIN=0.689s
ARTICLE_SUCCES_LATENCE_P50=3.668s
ARTICLE_SUCCES_LATENCE_P95=5.034s
ARTICLE_SUCCES_LATENCE_P99=5.485s
ARTICLE_SUCCES_LATENCE_MAX=5.583s
```

| Métrique | Interprétation |
|---|---|
| `COUNT` | Nombre de valeurs mesurées. |
| `MIN` | Requête la plus rapide. |
| `P50` | 50 % des requêtes sont terminées sous cette valeur. |
| `P95` | 95 % des requêtes sont terminées sous cette valeur. |
| `P99` | 99 % des requêtes sont terminées sous cette valeur. |
| `MAX` | Requête la plus lente. |

Le script affiche deux séries :

```text
ARTICLE_LATENCE
ARTICLE_SUCCES_LATENCE
```

`ARTICLE_LATENCE` inclut toutes les tentatives.

`ARTICLE_SUCCES_LATENCE` inclut uniquement les créations réussies.

---

## 11. Lecture des latences connexions

Exemple :

```text
===== LATENCES CONNEXIONS SIMULEES =====
CONNEXION_LATENCE_COUNT=125
CONNEXION_LATENCE_P50=10.758s
CONNEXION_LATENCE_P95=12.060s
CONNEXION_LATENCE_P99=12.174s
```

Cette durée correspond à l’ensemble des créations séquentielles effectuées par
une connexion simulée.

Avec trois articles par connexion, elle représente donc le temps nécessaire
pour effectuer les trois créations.

---

## 12. Codes de sortie

| Code | Signification |
|---:|---|
| `0` | Toutes les créations ont réussi. |
| `1` | Au moins une création a échoué. |
| `2` | Image introuvable ou erreur de validation des arguments par `argparse`. |

Dans un pipeline CI/CD, un code différent de zéro doit faire échouer le job de
performance.

---

## 13. Vérification après un run

Pour vérifier les articles d’un Run ID :

```bash
curl -fsS \
  --max-time 10 \
  -H "Host: blog.k8s.test" \
  "http://${INGRESS_IP}/api/articles" |
python3 -c '
import json
import sys

run_id = "REMPLACER_PAR_LE_RUN_ID"
articles = json.load(sys.stdin)

run_articles = [
    article for article in articles
    if run_id in (article.get("title") or "")
    or run_id in (article.get("content") or "")
]

stress_articles = [
    article for article in articles
    if "STRESS:" in (article.get("title") or "")
    or "STRESS:" in (article.get("content") or "")
]

print(f"ARTICLES_TOTAUX={len(articles)}")
print(f"ARTICLES_DU_RUN={len(run_articles)}")
print(f"ARTICLES_STRESS_TOTAL={len(stress_articles)}")
print(f"ARTICLES_SEED_PRESUMES={len(articles) - len(stress_articles)}")
'
```

Pour le test de référence, le résultat attendu avant nettoyage est :

```text
ARTICLES_TOTAUX=378
ARTICLES_DU_RUN=375
ARTICLES_STRESS_TOTAL=375
ARTICLES_SEED_PRESUMES=3
```

---

## 14. Nettoyage obligatoire après le test

Commencer par une simulation :

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --expected-seed-count 3
```

Après vérification des cibles, effectuer le nettoyage réel :

```bash
python3 scripts/stress/blog-clean-stress-articles.py \
  --base-url "http://${INGRESS_IP}" \
  --host-header "blog.k8s.test" \
  --expected-seed-count 3 \
  --execute
```

Consulter également :

```text
runbooks/blog-clean-stress-articles.md
```

---

## 15. Résultat de référence du lab

Configuration :

```text
7 FPM
2 Nginx
125 connexions simultanées
3 articles par connexion
```

Résultat observé :

```text
SUCCES=375
ERREURS=0
DUREE=12.208s
DEBIT=30.72 articles/s
ARTICLE_SUCCES_LATENCE_P95=5.034s
ARTICLE_SUCCES_LATENCE_P99=5.485s
CONNEXION_LATENCE_P95=12.060s
CONNEXION_LATENCE_P99=12.174s
```

Ce résultat constitue la référence actuelle du lab.

Il doit être comparé aux prochains tests de préproduction afin d’identifier
une éventuelle régression applicative.

---

## 16. Limites techniques CD APP125

Le job CD APP125 doit respecter les contraintes bloquantes suivantes :

| Contrôle | Limite technique |
|---|---:|
| Succès | = 375 |
| Erreurs | = 0 |
| Latences articles mesurées | = 375 |
| Durée totale | ≤ 15 s |
| Débit | ≥ 25 articles/s |
| Latence article P95 | ≤ 6.5 s |
| Latence article P99 | ≤ 7 s |
| Latence connexion P95 | ≤ 15 s |
| Latence connexion P99 | ≤ 15 s |
| CPU maximal du worker `rke2-worker-1` | ≤ 80 % |
| RAM maximale du worker `rke2-worker-1` | ≤ 80 % |

Ces limites sont dérivées du résultat manuel de référence du lab.

La marge retenue absorbe les variations normales de l’infrastructure tout en
restant suffisamment stricte pour détecter une régression applicative.

La durée maximale et le débit minimal sont cohérents : 375 articles créés en
15 secondes correspondent à un débit minimal de 25 articles par seconde.

Le CPU et la RAM du worker sont échantillonnés pendant toute l’exécution
APP125 avec `kubectl top node rke2-worker-1 --no-headers`.

Le job conserve les maxima observés. Ces pourcentages correspondent aux valeurs
fournies pour le nœud Kubernetes, et non aux métriques de l’hôte VirtualBox.

Le dépassement d’une seule limite doit faire échouer le job CD APP125.
