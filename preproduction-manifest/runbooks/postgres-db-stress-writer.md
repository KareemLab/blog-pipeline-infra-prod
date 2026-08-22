# Runbook — Stress direct BDD PostgreSQL

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/stress/postgres-db-stress-writer.py
```

Ce script sert à générer une charge d’écriture directement dans PostgreSQL.

Il ne passe pas par l’API HTTP de l’application.

Il permet notamment de mesurer :

```text
- le nombre de lignes insérées en base ;
- le débit d’écriture en lignes par seconde ;
- le comportement du PostgreSQL primary ;
- l’impact sur les readers PostgreSQL ;
- l’impact sur les workers Kubernetes ;
- la limite CPU/RAM PostgreSQL avant alerte ou saturation.
```

Cas réel utilisé dans le lab :

```text
125 utilisateurs applicatifs de référence
3 articles créés par utilisateur via l’application
375 articles applicatifs présents pendant le stress BDD
```

Puis stress BDD direct :

```text
W20 agressif x3 = 37800 lignes BDD
W20 agressif x4 = 50600 lignes BDD
W20 agressif x5 = 62100 lignes BDD
```

La capacité nominale retenue est :

```text
37800 / 125 = 302.4 articles équivalents par utilisateur
```

Donc la valeur fonctionnelle recommandée est :

```text
300 articles par utilisateur
```

---

## 2. Emplacement du script

Depuis le bastion :

```bash
cd /home/masterdevops/rke2-lab
```

Le script est ici :

```bash
scripts/stress/postgres-db-stress-writer.py
```

---

## 3. Périmètre et précautions

Le script écrit réellement dans PostgreSQL.

Il insère des lignes dans :

```text
public.db_stress_articles
```

Chaque run est identifié par :

```text
RUN_ID
```

Le script ne supprime aucune donnée.

Après chaque test, les lignes doivent être supprimées avec :

```bash
scripts/stress/postgres-db-stress-clean.py
```

Le stress BDD doit être utilisé uniquement dans un environnement de lab ou de préproduction contrôlé.

---

## 4. Prérequis

Les éléments suivants doivent être disponibles :

```text
- Python 3 ;
- kubectl configuré ;
- accès au namespace lab-k8s ;
- pod PostgreSQL primary disponible ;
- table public.db_stress_articles existante ;
- utilisateur PostgreSQL iksstudent ;
- base PostgreSQL blogkubernetesdb.
```

Vérification du pod primary :

```bash
k -n lab-k8s get pod pg-lab-postgresql-primary-0 -o wide
```

Vérification des pods PostgreSQL :

```bash
k -n lab-k8s get pods -o wide | grep -E 'pg-lab-postgresql-primary|pg-lab-postgresql-read'
```

---

## 5. Table utilisée

La table de stress attendue est :

```sql
CREATE TABLE public.db_stress_articles (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  writer_id INTEGER NOT NULL,
  writer_seq BIGINT NOT NULL,
  payload_title TEXT NOT NULL,
  payload_content TEXT NOT NULL,
  payload_bytes INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload_title_bytes INTEGER NOT NULL DEFAULT 0,
  payload_image_ref TEXT NOT NULL DEFAULT '',
  payload_image_ref_bytes INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX db_stress_articles_run_id_idx
  ON public.db_stress_articles(run_id);
```

---

## 6. Modèle de ligne insérée

Chaque ligne insérée simule un article applicatif.

Elle contient :

```text
- un titre ;
- un contenu ;
- une référence image ;
- le Run ID ;
- le numéro du writer ;
- le numéro de séquence du writer ;
- des métadonnées de taille.
```

La ligne ne contient pas le binaire de l’image.

Dans l’application, l’image est stockée comme référence texte en base, pas comme fichier binaire dans PostgreSQL.

---

## 7. Taille simulée d’un article

Mesures de référence du lab :

```text
title_bytes     ≈ 58
content_bytes   ≈ 271
image_ref_bytes ≈ 30
pg_row_bytes    ≈ 405 pour un article applicatif seed
```

La ligne de stress BDD mesurée est légèrement plus lourde :

```text
pg_row_bytes ≈ 464
```

Cela vient des métadonnées ajoutées pour le stress :

```text
run_id
writer_id
writer_seq
payload_title_bytes
payload_image_ref_bytes
```

---

## 8. Fonctionnement interne du script Python

Le script Python orchestre le stress depuis le bastion.

Il ne se connecte pas directement à PostgreSQL depuis la machine locale.

Il utilise :

```text
kubectl exec
```

pour exécuter les commandes dans le pod :

```text
pg-lab-postgresql-primary-0
```

Le fonctionnement général est :

```text
1. lecture des options ;
2. validation des paramètres ;
3. lancement de plusieurs writers Python en parallèle ;
4. chaque writer exécute une boucle distante dans le pod PostgreSQL ;
5. chaque boucle insère des batchs de lignes via psql ;
6. le script collecte les résultats des writers ;
7. le script vérifie le nombre de lignes présentes pour le Run ID ;
8. le script affiche un résumé global.
```

Le parallélisme local est assuré par Python avec :

```text
ThreadPoolExecutor
```

Chaque writer représente une charge d’écriture indépendante.

---

## 9. Notion de writer

Un writer est un flux d’insertion.

Avec :

```text
--writers 20
```

le script lance 20 writers en parallèle.

Chaque writer insère des lignes par batch.

Un writer n’est pas un utilisateur applicatif.

Un writer représente une pression technique d’écriture sur PostgreSQL.

---

## 10. Notion de batch

L’option :

```text
--batch-size
```

définit le nombre de lignes insérées par batch.

Exemple :

```text
--batch-size 100
```

signifie :

```text
chaque batch insère 100 lignes
```

Ce n’est pas le nombre total de lignes du test.

Le nombre total réel dépend :

```text
- du nombre de writers ;
- de la durée du test ;
- du temps d’exécution de chaque batch ;
- de la charge PostgreSQL ;
- de la latence kubectl exec / psql ;
- d’une éventuelle limitation volontaire de débit.
```

---

## 11. Notion de durée

L’option :

```text
--duration
```

définit la durée cible de la boucle d’écriture de chaque writer.

Exemple :

```text
--duration 20
```

signifie :

```text
chaque writer essaie d’écrire pendant environ 20 secondes
```

La durée totale observée peut être supérieure, car le script doit attendre :

```text
- la fin des writers ;
- la collecte des sorties ;
- la vérification finale en base.
```

---

## 12. Limitation volontaire de débit

L’option :

```text
--target-rate-per-writer
```

permet de limiter volontairement le nombre de lignes par seconde et par writer.

Exemple :

```text
--target-rate-per-writer 10
```

signifie :

```text
chaque writer essaie de viser environ 10 lignes par seconde
```

Avec :

```text
--target-rate-per-writer 0
```

il n’y a pas de limitation volontaire.

C’est le mode agressif utilisé pour pousser PostgreSQL.

---

## 13. Afficher l’aide

Commande :

```bash
python3 scripts/stress/postgres-db-stress-writer.py --help
```

Cette commande affiche les options supportées par la version actuelle du script.

---

## 14. Explication des options

| Option | Obligatoire | Valeur par défaut | Rôle |
|---|---:|---|---|
| `-h`, `--help` | non | aucune | Affiche l’aide puis quitte. |
| `--namespace` | non | `lab-k8s` | Namespace Kubernetes contenant PostgreSQL. |
| `--pod` | non | `pg-lab-postgresql-primary-0` | Pod PostgreSQL cible. |
| `--container` | non | `postgresql` | Container PostgreSQL dans le pod. |
| `--table` | non | `public.db_stress_articles` | Table cible pour les insertions. |
| `--run-id` | oui | aucune | Identifiant unique du test. |
| `--writers` | oui | aucune | Nombre de writers lancés en parallèle. |
| `--duration` | oui | aucune | Durée cible du test en secondes. |
| `--batch-size` | oui | aucune | Nombre de lignes insérées par batch. |
| `--title-bytes` | non | `58` | Taille simulée du titre. |
| `--payload-bytes` | non | `271` | Taille simulée du contenu. |
| `--image-ref-bytes` | non | `30` | Taille simulée de la référence image. |
| `--target-rate-per-writer` | non | `0.0` | Débit cible par writer. `0` signifie sans limitation volontaire. |
| `--execute` | non | désactivé | Autorise les insertions réelles. Sans cette option, le script reste en simulation. |

---

## 15. Mode simulation

Sans `--execute`, le script n’insère pas de lignes.

Exemple :

```bash
BDD_RUN_ID="$(date -u +%Y%m%d-%H%M%S)-bdd-simulation"

python3 scripts/stress/postgres-db-stress-writer.py \
  --run-id "$BDD_RUN_ID" \
  --writers 1 \
  --duration 1 \
  --batch-size 1
```

Ce mode permet de vérifier les paramètres sans écrire dans PostgreSQL.

---

## 16. Smoke test

Un smoke test valide la chaîne minimale :

```text
writer -> primary PostgreSQL -> table -> cleaner
```

Commande :

```bash
BDD_RUN_ID="$(date -u +%Y%m%d-%H%M%S)-smoke-bdd-1"

python3 scripts/stress/postgres-db-stress-writer.py \
  --run-id "$BDD_RUN_ID" \
  --writers 1 \
  --duration 1 \
  --batch-size 1 \
  --title-bytes 58 \
  --payload-bytes 271 \
  --image-ref-bytes 30 \
  --target-rate-per-writer 1 \
  --execute
```

Résultat attendu :

```text
TOTAL_ROWS=1
ROWS_IN_DB_FOR_RUN_ID=1
TEST_RC=0
```

Nettoyage du smoke test :

```bash
python3 scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID" \
  --execute
```

---

## 17. Palier contrôlé

Exemple avec 20 writers, batchs de 10, et limitation de débit :

```bash
BDD_RUN_ID="$(date -u +%Y%m%d-%H%M%S)-bdd-w20"

python3 scripts/stress/postgres-db-stress-writer.py \
  --run-id "$BDD_RUN_ID" \
  --writers 20 \
  --duration 11 \
  --batch-size 10 \
  --title-bytes 58 \
  --payload-bytes 271 \
  --image-ref-bytes 30 \
  --target-rate-per-writer 10 \
  --execute
```

Ce mode est utile pour observer une montée progressive.

---

## 18. Palier agressif simple

Le palier agressif enlève la limitation volontaire :

```bash
BDD_RUN_ID="$(date -u +%Y%m%d-%H%M%S)-bdd-w20-agressif"

python3 scripts/stress/postgres-db-stress-writer.py \
  --run-id "$BDD_RUN_ID" \
  --writers 20 \
  --duration 20 \
  --batch-size 100 \
  --title-bytes 58 \
  --payload-bytes 271 \
  --image-ref-bytes 30 \
  --target-rate-per-writer 0 \
  --execute
```

Résultat observé dans le lab :

```text
TOTAL_ROWS=13000
ROWS_IN_DB_FOR_RUN_ID=13000
TOTAL_ROWS_PER_SECOND=541.53
TEST_RC=0
```

---

## 19. Plusieurs passes avec le même Run ID

Pour accumuler des lignes dans la table, il est possible de relancer plusieurs fois le même palier avec le même `RUN_ID`.

Exemple logique :

```text
pass 1 -> ajoute des lignes
pass 2 -> ajoute encore des lignes avec le même RUN_ID
pass 3 -> ajoute encore des lignes avec le même RUN_ID
```

Dans ce cas :

```text
ROWS_IN_DB_FOR_RUN_ID
```

devient cumulatif.

Attention :

```text
TEST_RC peut devenir 2
```

même si les insertions ont réussi, car le script compare le nombre de lignes du run courant avec le total déjà présent pour le même Run ID.

Dans ce cas, le total fiable à retenir est celui donné par le cleaner en simulation :

```bash
python3 scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID"
```

Sortie utilisée :

```text
DB_STRESS_ROWS_AVANT=<total réel cumulé>
```

---

## 20. Palier W20 agressif x3

Ce palier a été retenu comme capacité nominale.

Principe :

```text
3 passes W20 agressif
même RUN_ID
pas de nettoyage entre les passes
```

Résultat observé :

```text
PASS 1 = 12100 lignes
PASS 2 = 13100 lignes
PASS 3 = 12600 lignes
TOTAL  = 37800 lignes
```

Calcul fonctionnel :

```text
37800 / 125 = 302.4 articles équivalents par utilisateur
```

Conclusion :

```text
Capacité nominale retenue : 300 articles par utilisateur.
```

---

## 21. Palier W20 agressif x4

Ce palier représente une capacité limite.

Résultat observé :

```text
TOTAL = 50600 lignes
50600 / 125 = 404.8 articles équivalents par utilisateur
```

Ce palier passe en zone d’alerte côté dashboard.

Il n’est donc pas retenu comme capacité nominale.

Il sert à montrer la limite haute avant saturation plus forte.

---

## 22. Palier W20 agressif x5

Ce palier représente la saturation PostgreSQL.

Résultat observé :

```text
TOTAL = 62100 lignes
62100 / 125 = 496.8 articles équivalents par utilisateur
PostgreSQL primary CPU ≈ 98.8%
```

Ce palier n’est pas retenu comme capacité nominale.

Il sert à démontrer que le goulet d’étranglement est le PostgreSQL primary.

---

## 23. Pourquoi éviter W100

Un test avec 100 writers peut échouer avant de produire une charge utile propre.

Dans le lab, PostgreSQL était configuré avec :

```text
MAX_CONNECTIONS=100
CURRENT_CONNECTIONS≈10
```

Avec 100 writers, le test peut atteindre la limite de connexions ou la limite du mode `kubectl exec` / `psql`.

Un résultat W100 avec :

```text
TOTAL_ROWS=0
TEST_RC=1
```

ne signifie pas que PostgreSQL n’est pas chargé.

Il signifie surtout que le mode de test n’est pas adapté avec autant de writers simultanés.

La bonne approche observée est :

```text
moins de writers
plus de batch-size
plusieurs passes
```

---

## 24. Lecture du résumé global

Exemple :

```text
RUN_ID=20260630-155907-bdd-w20-agressif
WRITERS=20
DURATION_SECONDS=20
BATCH_SIZE=100
TITLE_BYTES=58
PAYLOAD_BYTES=271
IMAGE_REF_BYTES=30
TARGET_RATE_PER_WRITER=0.0
TOTAL_ROWS=13000
ROWS_IN_DB_FOR_RUN_ID=13000
TOTAL_DURATION=24.006s
TOTAL_ROWS_PER_SECOND=541.53
ERREURS_WRITERS=0
TEST_RC=0
```

| Métrique | Interprétation |
|---|---|
| `RUN_ID` | Identifiant du test. |
| `WRITERS` | Nombre de writers parallèles. |
| `DURATION_SECONDS` | Durée cible du test. |
| `BATCH_SIZE` | Nombre de lignes par batch. |
| `TITLE_BYTES` | Taille simulée du titre. |
| `PAYLOAD_BYTES` | Taille simulée du contenu. |
| `IMAGE_REF_BYTES` | Taille simulée de la référence image. |
| `TARGET_RATE_PER_WRITER` | Limitation volontaire de débit. |
| `TOTAL_ROWS` | Nombre de lignes insérées pendant cette exécution du script. |
| `ROWS_IN_DB_FOR_RUN_ID` | Nombre total de lignes présentes en base pour ce Run ID. |
| `TOTAL_DURATION` | Durée réelle mesurée par le script. |
| `TOTAL_ROWS_PER_SECOND` | Débit global observé. |
| `ERREURS_WRITERS` | Nombre de writers ayant échoué. |
| `TEST_RC` | Code fonctionnel retourné par le test. |

---

## 25. Lecture des sorties par writer

Exemple :

```text
--- WRITER 16 STDOUT ---
WRITER_ID=16
WRITER_BATCHES=7
WRITER_ROWS=700
WRITER_DURATION=20.999s
WRITER_ROWS_PER_SECOND=33.33
```

| Métrique | Interprétation |
|---|---|
| `WRITER_ID` | Numéro du writer. |
| `WRITER_BATCHES` | Nombre de batchs insérés par ce writer. |
| `WRITER_ROWS` | Nombre de lignes insérées par ce writer. |
| `WRITER_DURATION` | Durée observée pour ce writer. |
| `WRITER_ROWS_PER_SECOND` | Débit individuel du writer. |

---

## 26. Codes de sortie et interprétation

| Code | Interprétation |
|---:|---|
| `0` | Test valide, pas d’erreur writer, vérification cohérente. |
| `1` | Échec global ou erreur writer importante. |
| `2` | Vérification incohérente, souvent liée à un Run ID réutilisé sur plusieurs passes. |

Cas important :

```text
Avec plusieurs passes sur le même Run ID, TEST_RC=2 peut apparaître car ROWS_IN_DB_FOR_RUN_ID devient cumulatif.
```

Dans ce cas, vérifier le total réel avec le cleaner en simulation.

---

## 27. Nettoyage obligatoire

Après un run, ne pas supprimer manuellement les lignes SQL.

Utiliser :

```bash
python3 scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID"
```

Puis, après validation :

```bash
python3 scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID" \
  --execute
```

Consulter également :

```text
runbooks/postgres-db-stress-clean.md
```

---

## 28. Conclusion du lab

Le graphe global montre trois pics importants :

```text
W20 agressif x5 -> saturation PostgreSQL
W20 agressif x3 -> capacité nominale validée
W20 agressif x4 -> zone limite avec alerte
```

La valeur retenue est :

```text
W20 agressif x3 = 37800 lignes BDD
```

Pour 125 utilisateurs :

```text
37800 / 125 = 302.4
```

Conclusion fonctionnelle :

```text
prévoir 300 articles par utilisateur à l’inscription
```

Conclusion technique :

```text
le goulet d’étranglement principal est le PostgreSQL primary
```

Les workers Kubernetes et l’application restent sous les seuils critiques pour la capacité nominale retenue.
