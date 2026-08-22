# Runbook — Nettoyage sécurisé des lignes de stress BDD PostgreSQL

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/stress/postgres-db-stress-clean.py
```

Ce script sert à vérifier puis supprimer les lignes créées par les tests de
stress PostgreSQL directs.

Il cible uniquement la table de stress BDD :

```text
public.db_stress_articles
```

Il ne supprime pas les articles applicatifs de la table métier :

```text
public.article
```

Le nettoyage applicatif des articles créés via l'API HTTP est géré par un
autre script :

```bash
scripts/stress/blog-clean-stress-articles.py
```

---

## 2. Emplacement du script

Depuis le bastion :

```bash
cd /home/masterdevops/rke2-lab
```

Le script est ici :

```bash
scripts/stress/postgres-db-stress-clean.py
```

---

## 3. Périmètre de sécurité

Le script supprime uniquement les lignes correspondant au Run ID fourni :

```text
run_id = <RUN_ID>
```

Il ne réalise jamais de suppression globale sans filtre.

Le filtre SQL utilisé correspond au principe suivant :

```sql
DELETE FROM public.db_stress_articles
WHERE run_id = '<RUN_ID>';
```

Le champ `run_id` est donc obligatoire.

---

## 4. Table concernée

Table de stress :

```text
public.db_stress_articles
```

Cette table contient les écritures générées par :

```bash
scripts/stress/postgres-db-stress-writer.py
```

Chaque ligne représente un article équivalent utilisé pour mesurer la charge
d'écriture PostgreSQL.

Exemple de colonnes importantes :

```text
id
run_id
writer_id
writer_seq
payload_title
payload_content
payload_bytes
payload_title_bytes
payload_image_ref
payload_image_ref_bytes
created_at
```

---

## 5. Avertissement important

Le script est destructif uniquement avec l'option :

```text
--execute
```

Sans cette option, il fonctionne en simulation.

La procédure normale est toujours :

```text
1. lancer sans --execute ;
2. vérifier DB_STRESS_ROWS_AVANT ;
3. lancer avec --execute ;
4. relancer sans --execute pour vérifier le retour à zéro.
```

Ne jamais lancer directement `--execute` sans avoir vérifié le Run ID.

---

## 6. Fonctionnement par défaut

Sans option `--execute`, le script ne supprime rien.

Il affiche seulement le nombre de lignes BDD correspondant au Run ID.

Exemple :

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "20260630-165239-bdd-w20-agressif-x3"
```

Sortie attendue :

```text
RUN_ID=20260630-165239-bdd-w20-agressif-x3
NAMESPACE=lab-k8s
POD=pg-lab-postgresql-primary-0
CONTAINER=postgresql
TABLE=public.db_stress_articles
PGDATABASE=blogkubernetesdb
PGUSER=iksstudent
IS_REPLICA=false
DB_STRESS_ROWS_AVANT=37800
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
TEST_RC=0
```

---

## 7. Fonctionnement avec execute

Avec l'option :

```text
--execute
```

le script supprime les lignes du Run ID.

Exemple :

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "20260630-165239-bdd-w20-agressif-x3" \
  --execute
```

Sortie attendue :

```text
RUN_ID=20260630-165239-bdd-w20-agressif-x3
IS_REPLICA=false
DB_STRESS_ROWS_AVANT=37800
MODE=EXECUTION
DB_STRESS_ROWS_SUPPRIMEES=37800
DB_STRESS_ROWS_APRES=0
TEST_RC=0
```

---

## 8. Pourquoi vérifier `IS_REPLICA`

Le cleaner doit s'exécuter contre le PostgreSQL primary.

Dans le lab, le pod attendu est :

```text
pg-lab-postgresql-primary-0
```

Le script affiche :

```text
IS_REPLICA=false
```

Ce résultat confirme que la cible n'est pas une replica en lecture seule.

Si `IS_REPLICA=true`, il ne faut pas utiliser cette cible pour supprimer des
lignes.

---

## 9. Afficher l'aide

Commande :

```bash
python3 scripts/stress/postgres-db-stress-clean.py --help
```

Cette commande affiche les options supportées par la version actuelle du
script.

---

## 10. Explication des options

| Option | Obligatoire | Valeur par défaut | Rôle |
|---|---:|---|---|
| `-h`, `--help` | non | aucune | Affiche l'aide puis quitte. |
| `--namespace` | non | `lab-k8s` | Namespace Kubernetes contenant PostgreSQL. |
| `--pod` | non | `pg-lab-postgresql-primary-0` | Pod PostgreSQL cible. Doit être le primary pour supprimer. |
| `--container` | non | `postgresql` | Container PostgreSQL dans le pod. |
| `--table` | non | `public.db_stress_articles` | Table de stress à nettoyer. |
| `--pgdatabase` | non | `blogkubernetesdb` | Base PostgreSQL utilisée. |
| `--pguser` | non | `iksstudent` | Utilisateur PostgreSQL utilisé par `psql`. |
| `--run-id` | oui | aucune | Identifiant du run à vérifier ou nettoyer. |
| `--execute` | non | désactivé | Autorise la suppression réelle. |

---

## 11. Procédure recommandée complète

## 11.1 Se placer dans le dépôt

```bash
cd /home/masterdevops/rke2-lab
```

---

## 11.2 Définir le Run ID

Exemple :

```bash
BDD_RUN_ID="20260630-165239-bdd-w20-agressif-x3"
```

Le Run ID doit correspondre exactement à celui utilisé pendant le stress BDD.

---

## 11.3 Lancer la simulation

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID"
```

Vérifier :

```text
RUN_ID
IS_REPLICA=false
DB_STRESS_ROWS_AVANT
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
TEST_RC=0
```

---

## 11.4 Nettoyer réellement

Après validation de la simulation :

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID" \
  --execute
```

Vérifier :

```text
DB_STRESS_ROWS_SUPPRIMEES=<nombre attendu>
DB_STRESS_ROWS_APRES=0
TEST_RC=0
```

---

## 11.5 Vérifier après nettoyage

Relancer le cleaner sans `--execute` :

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID"
```

État attendu :

```text
DB_STRESS_ROWS_AVANT=0
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
TEST_RC=0
```

---

## 12. Toutes les façons d'appeler le script

## 12.1 Simulation minimale

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID"
```

Aucune suppression n'est effectuée.

---

## 12.2 Nettoyage réel

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID" \
  --execute
```

Supprime les lignes du Run ID uniquement.

---

## 12.3 Spécifier explicitement le namespace

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --namespace lab-k8s \
  --run-id "$BDD_RUN_ID"
```

---

## 12.4 Spécifier explicitement le pod PostgreSQL

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --namespace lab-k8s \
  --pod pg-lab-postgresql-primary-0 \
  --container postgresql \
  --run-id "$BDD_RUN_ID"
```

Cette forme est utile si plusieurs clusters ou namespaces sont utilisés.

---

## 12.5 Spécifier explicitement la base et l'utilisateur

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --pgdatabase blogkubernetesdb \
  --pguser iksstudent \
  --run-id "$BDD_RUN_ID"
```

---

## 12.6 Spécifier explicitement la table

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --table public.db_stress_articles \
  --run-id "$BDD_RUN_ID"
```

Ne modifier cette option que si une autre table de stress existe réellement.

---

## 12.7 Nettoyer un run qui n'a rien inséré

```bash
./scripts/stress/postgres-db-stress-clean.py \
  --run-id "$BDD_RUN_ID"
```

Sortie possible :

```text
DB_STRESS_ROWS_AVANT=0
MODE=SIMULATION
AUCUNE_SUPPRESSION_EFFECTUEE
TEST_RC=0
```

Dans ce cas, aucun `--execute` n'est nécessaire.

---

## 13. Lecture des sorties

| Sortie | Interprétation |
|---|---|
| `RUN_ID` | Run ciblé par la vérification ou suppression. |
| `NAMESPACE` | Namespace Kubernetes utilisé. |
| `POD` | Pod PostgreSQL ciblé. |
| `CONTAINER` | Container ciblé dans le pod. |
| `TABLE` | Table de stress concernée. |
| `PGDATABASE` | Base PostgreSQL utilisée. |
| `PGUSER` | Utilisateur PostgreSQL utilisé. |
| `IS_REPLICA` | Indique si le pod cible est une replica. Doit être `false` pour supprimer. |
| `DB_STRESS_ROWS_AVANT` | Nombre de lignes du Run ID avant suppression. |
| `MODE=SIMULATION` | Aucune suppression n'est effectuée. |
| `MODE=EXECUTION` | Les suppressions sont réellement effectuées. |
| `DB_STRESS_ROWS_SUPPRIMEES` | Nombre de lignes supprimées. |
| `DB_STRESS_ROWS_APRES` | Nombre de lignes restantes après suppression. Doit être `0`. |
| `TEST_RC` | Résultat fonctionnel du script. `0` indique une exécution validée. |

---

## 14. Codes de retour

| Code | Signification |
|---:|---|
| `0` | Simulation ou nettoyage validé. |
| `1` | Erreur d'exécution, erreur `kubectl`, erreur `psql` ou vérification non conforme. |
| `2` | Erreur de validation des arguments par `argparse`. |

Dans un pipeline CI/CD, un code différent de zéro doit faire échouer le job de
nettoyage.

---

## 15. Exemples de nettoyage observés dans le lab

## 15.1 Nettoyage W20 agressif x3

Run :

```text
20260630-165239-bdd-w20-agressif-x3
```

Volume :

```text
DB_STRESS_ROWS_AVANT=37800
DB_STRESS_ROWS_SUPPRIMEES=37800
DB_STRESS_ROWS_APRES=0
```

Ce run correspond à la capacité nominale retenue :

```text
37800 / 125 = 302.4 articles équivalents par utilisateur
```

---

## 15.2 Nettoyage W20 agressif x4

Run :

```text
20260630-171006-bdd-w20-agressif-x4
```

Volume :

```text
DB_STRESS_ROWS_AVANT=50600
DB_STRESS_ROWS_SUPPRIMEES=50600
DB_STRESS_ROWS_APRES=0
```

Ce run correspond à une capacité limite avec alerte PostgreSQL.

---

## 15.3 Nettoyage W20 agressif x5

Run :

```text
20260630-164031-bdd-w20-agressif-x5
```

Volume :

```text
DB_STRESS_ROWS_AVANT=62100
DB_STRESS_ROWS_SUPPRIMEES=62100
DB_STRESS_ROWS_APRES=0
```

Ce run correspond à une saturation PostgreSQL primary.

---

## 15.4 Nettoyage de lignes résiduelles après un échec W100

Run :

```text
20260630-154901-bdd-w100
```

Le writer a échoué globalement, mais le cleaner a trouvé des lignes
résiduelles :

```text
DB_STRESS_ROWS_AVANT=50
DB_STRESS_ROWS_SUPPRIMEES=50
DB_STRESS_ROWS_APRES=0
```

Ce cas montre pourquoi il faut toujours vérifier avec le cleaner après un
échec du writer.

---

## 15.5 Nettoyage de lignes résiduelles après un échec W40 agressif

Run :

```text
20260630-162320-bdd-w40-agressif
```

Le writer a échoué globalement, mais le cleaner a trouvé :

```text
DB_STRESS_ROWS_AVANT=900
DB_STRESS_ROWS_SUPPRIMEES=900
DB_STRESS_ROWS_APRES=0
```

---

## 16. Erreurs à ne pas contourner

Si le script affiche :

```text
IS_REPLICA=true
```

ne pas forcer la suppression. La cible n'est pas le primary.

Si le script affiche :

```text
DB_STRESS_ROWS_APRES=<valeur supérieure à 0>
```

ne pas considérer le nettoyage comme terminé.

Si `TEST_RC` est différent de `0`, il faut examiner l'erreur avant de relancer.

Si le Run ID est incertain, ne pas exécuter `--execute`.

---

## 17. Vérification indépendante optionnelle

Le cleaner suffit normalement pour valider l'état.

Si une vérification SQL indépendante est nécessaire, elle peut être faite avec
`kubectl exec` sur le primary.

Exemple :

```bash
k -n lab-k8s exec pg-lab-postgresql-primary-0 -c postgresql -- \
  psql -U iksstudent -d blogkubernetesdb -tAc \
  "SELECT count(*) FROM public.db_stress_articles WHERE run_id='${BDD_RUN_ID}';"
```

Résultat attendu après nettoyage :

```text
0
```

Cette vérification n'est pas nécessaire pendant les paliers de stress si la
sortie du cleaner est déjà correcte.

---

## 18. Moment du nettoyage dans la procédure de stress

Pendant une campagne de stress BDD :

```text
1. lancer un palier ;
2. attendre la fin du writer ;
3. faire les screenshots Grafana ;
4. nettoyer le Run ID BDD ;
5. vérifier que le Run ID revient à zéro ;
6. passer au palier suivant.
```

Ne pas nettoyer avant les screenshots Grafana.

---

## 19. Script associé

Les lignes nettoyées par ce script sont générées par :

```text
scripts/stress/postgres-db-stress-writer.py
```

Consulter également :

```text
runbooks/postgres-db-stress-writer.md
```

---

## 20. Résultat attendu après la campagne

À la fin de la campagne :

```text
public.db_stress_articles = 0 ligne
articles STRESS applicatifs = 0
articles seed applicatifs = 3
Prometheus scrape interval = 30s
replicas applicatifs restaurés
replicas PostgreSQL read restaurés
```

Le lab doit revenir dans un état propre avant commit.
