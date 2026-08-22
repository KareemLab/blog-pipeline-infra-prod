# Runbook — Méthode de réplication PostgreSQL avec Argo CD `pg-lab`

## 1. Objectif

Ce runbook explique la méthode propre pour augmenter ou modifier la réplication PostgreSQL dans le lab RKE2.

Application Argo CD concernée :

```text
pg-lab
```

Namespace Kubernetes :

```text
lab-k8s
```

Chemin GitOps :

```text
apps/postgresql-preprod
```

Fichier principal à modifier :

```text
apps/postgresql-preprod/values.yaml
```

Release Helm :

```text
pg-lab
```

Chart Helm :

```text
bitnami/postgresql
```

Version actuelle du chart :

```text
18.6.7
```

Version PostgreSQL :

```text
18.4.0
```

L’objectif est de modifier la réplication PostgreSQL sans casser la base, sans supprimer de PVC, et sans appliquer un changement non vérifié.

La règle principale est :

```text
hors Argo CD = simulation, audit, diff, validation
dans Argo CD = application réelle via GitOps
```

---

## 2. Situation actuelle

PostgreSQL est maintenant visible dans Argo CD via l’application séparée :

```text
pg-lab
```

État attendu :

```text
pg-lab   Synced   Healthy
```

La base actuelle utilise une architecture avec réplication :

```yaml
postgresql:
  architecture: replication
```

État PostgreSQL actuel :

```text
primary : 1 pod
read replicas : 2 pods
```

Ressources attendues :

```text
statefulset.apps/pg-lab-postgresql-primary   1/1
statefulset.apps/pg-lab-postgresql-read      2/2

pod/pg-lab-postgresql-primary-0              2/2 Running
pod/pg-lab-postgresql-read-0                 2/2 Running
pod/pg-lab-postgresql-read-1                 2/2 Running
```

Placement actuel :

```text
primary sur rke2-worker-2
read replica 0 sur rke2-worker-1
read replica 1 sur rke2-worker-2
```

PVC actuels :

```text
data-pg-lab-postgresql-primary-0
data-pg-lab-postgresql-read-0
data-pg-lab-postgresql-read-1
```

---

## 3. Principe important : pourquoi travailler en deux temps

Depuis que PostgreSQL est géré par Argo CD, il ne faut plus faire un changement direct avec :

```bash
helm upgrade pg-lab ...
```

ou avec :

```bash
kubectl patch statefulset ...
```

Pourquoi ?

Parce que cela créerait un drift entre :

```text
l’état réel du cluster
```

et :

```text
l’état désiré dans Git / Argo CD
```

La bonne méthode est donc en deux temps.

### Temps 1 — Hors Argo CD

Objectif :

```text
préparer le changement
simuler le rendu Helm
comparer avec l’existant
vérifier les risques
ne rien appliquer au cluster
```

Outils utilisés :

```text
copie temporaire des values
helm template
kubectl diff
analyse du diff
vérification des pods/PVC
```

### Temps 2 — Dans Argo CD

Objectif :

```text
modifier Git
commit/push
laisser Argo CD détecter OutOfSync
vérifier le diff dans Argo CD
sync manuel
surveiller PostgreSQL
valider l’application Symfony
```

---

## 4. Ce qu’il ne faut pas faire

Ne pas faire :

```bash
helm upgrade pg-lab bitnami/postgresql ...
```

Ne pas faire :

```bash
kubectl scale statefulset pg-lab-postgresql-read --replicas=3
```

Ne pas faire :

```bash
kubectl patch statefulset pg-lab-postgresql-read ...
```

Ne pas faire :

```text
Sync Argo CD avec prune activé sans analyse
```

Ne pas faire :

```text
supprimer un PVC PostgreSQL
```

Ne pas faire :

```text
modifier le Secret PostgreSQL sans procédure
```

Ne pas faire :

```text
changer storageClass sans procédure
```

La réplication PostgreSQL est une opération stateful. Elle doit rester contrôlée par `masterdevops`.

---

## 5. Point critique : nombre de nodes et anti-affinity

La configuration actuelle des read replicas contient une anti-affinity stricte :

```yaml
readReplicas:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app.kubernetes.io/component: read
            app.kubernetes.io/instance: pg-lab
            app.kubernetes.io/name: postgresql
        topologyKey: kubernetes.io/hostname
```

Cela veut dire :

```text
Kubernetes ne doit pas placer deux read replicas PostgreSQL sur le même hostname.
```

La configuration actuelle autorise les read replicas uniquement sur :

```text
rke2-worker-1
rke2-worker-2
```

Donc avec seulement deux hostnames autorisés, cette configuration convient pour :

```text
replicaCount: 2
```

Mais elle pose problème pour :

```text
replicaCount: 3
```

Pourquoi ?

Parce qu’il faudrait placer 3 pods read replicas sur seulement 2 hostnames, avec interdiction stricte de mettre deux read replicas sur le même hostname.

Résultat probable :

```text
le troisième pod reste Pending
```

---

## 6. Choix d’architecture avant d’augmenter les replicas

Avant de passer de 2 à 3 read replicas, il faut choisir une stratégie.

### Option A — Ajouter un troisième worker PostgreSQL

C’est la meilleure option pour la haute disponibilité.

Exemple :

```text
rke2-worker-1
rke2-worker-2
rke2-worker-3
```

On ajoute ensuite `rke2-worker-3` dans la nodeAffinity.

Avantages :

```text
meilleure répartition
vraie tolérance de placement
anti-affinity stricte conservée
moins de risque de Pending
```

Inconvénients :

```text
il faut ajouter un node
il faut préparer stockage local-path
il faut valider monitoring et réseau
```

### Option B — Relâcher l’anti-affinity

On passe de :

```text
requiredDuringSchedulingIgnoredDuringExecution
```

à :

```text
preferredDuringSchedulingIgnoredDuringExecution
```

Avantages :

```text
possible avec deux workers
le troisième pod peut être schedulé
```

Inconvénients :

```text
moins bonne haute disponibilité
deux read replicas peuvent se retrouver sur le même node
risque concentré en cas de panne node
```

### Option C — Rester à 2 read replicas

C’est l’option la plus stable actuellement.

Avantages :

```text
configuration déjà validée
pods Running
PVC Bound
Argo CD Synced/Healthy
pas de risque supplémentaire
```

Inconvénients :

```text
pas d’augmentation de capacité read
```

---

## 7. Pré-requis avant toute modification

Avant de modifier la réplication, vérifier l’état Git :

```bash
cd /home/masterdevops/rke2-lab
git status -sb
```

Résultat attendu :

```text
## main...origin/main
```

Vérifier Argo CD :

```bash
kubectl -n argocd get application pg-lab -o wide
```

Résultat attendu :

```text
pg-lab   Synced   Healthy
```

Vérifier PostgreSQL :

```bash
kubectl -n lab-k8s get sts,pods,svc,pvc | grep -E 'pg-lab|postgresql'
```

Résultat attendu :

```text
primary 1/1
read 2/2
pods Running
PVC Bound
```

Vérifier l’application Symfony :

```bash
curl -I http://blog.k8s.test/articles | head -n 1
```

Résultat attendu :

```text
HTTP/1.1 200 OK
```

---

## 8. Sauvegarde avant changement

Avant toute modification PostgreSQL réelle, vérifier qu’un backup existe.

Vérifier le PVC de backup :

```bash
kubectl -n lab-k8s get pvc postgresql-logical-backups
```

Vérifier les jobs de backup récents :

```bash
kubectl -n lab-k8s get jobs | grep -E 'postgresql|backup'
```

Vérifier les pods de backup :

```bash
kubectl -n lab-k8s get pods | grep -E 'postgresql-logical-backup|backup'
```

Si aucun backup récent n’est confirmé, ne pas continuer.

Règle :

```text
pas de modification PostgreSQL sans backup vérifié
```

---

## 9. Temps 1 — Préparer hors Argo CD

Le but est de tester le changement localement sans modifier le cluster.

Créer un dossier de travail temporaire :

```bash
mkdir -p /tmp/pg-lab-replication-test
```

Copier les values actuelles :

```bash
cp /home/masterdevops/rke2-lab/apps/postgresql-preprod/values.yaml /tmp/pg-lab-replication-test/values.yaml
```

Exporter le manifest actuel du cluster :

```bash
helm get manifest pg-lab -n lab-k8s > /tmp/pg-lab-replication-test/manifest-current.yaml
```

Rendre le manifest actuel depuis Git :

```bash
cd /home/masterdevops/rke2-lab
helm template pg-lab apps/postgresql-preprod   --namespace lab-k8s   > /tmp/pg-lab-replication-test/manifest-from-git.yaml
```

Comparer :

```bash
diff -u /tmp/pg-lab-replication-test/manifest-current.yaml   /tmp/pg-lab-replication-test/manifest-from-git.yaml | head -120
```

Résultat attendu avant modification :

```text
aucune différence dangereuse
```

---

## 10. Exemple : passer de 2 à 3 read replicas avec un troisième worker

Cette section décrit la méthode recommandée si un troisième worker PostgreSQL existe.

Exemple de worker ajouté :

```text
rke2-worker-3
```

Modifier temporairement la copie :

```bash
cp apps/postgresql-preprod/values.yaml /tmp/pg-lab-replication-test/values-3-replicas.yaml
```

Modifier la copie temporaire pour obtenir :

```yaml
postgresql:
  readReplicas:
    replicaCount: 3
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
          - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
              - rke2-worker-1
              - rke2-worker-2
              - rke2-worker-3
```

Le point important est :

```text
replicaCount passe à 3
rke2-worker-3 est ajouté dans les hostnames autorisés
anti-affinity stricte conservée
```

Rendre le manifest avec cette copie.

Comme le fichier temporaire contient déjà la clé `postgresql:`, on peut tester avec une copie du chart Git :

```bash
cp -r apps/postgresql-preprod /tmp/pg-lab-replication-test/chart-test
cp /tmp/pg-lab-replication-test/values-3-replicas.yaml /tmp/pg-lab-replication-test/chart-test/values.yaml

helm template pg-lab /tmp/pg-lab-replication-test/chart-test   --namespace lab-k8s   > /tmp/pg-lab-replication-test/manifest-3-replicas.yaml
```

Comparer avec l’état actuel :

```bash
diff -u /tmp/pg-lab-replication-test/manifest-current.yaml   /tmp/pg-lab-replication-test/manifest-3-replicas.yaml | head -220
```

À vérifier dans le diff :

```text
StatefulSet read replicas passe de 2 à 3
nodeAffinity contient rke2-worker-3
pas de suppression de PVC
pas de changement storageClass
pas de changement selector
pas de changement du primary
pas de changement du secret
pas de changement du service principal
```

Ensuite faire un diff contre le cluster :

```bash
kubectl diff -f /tmp/pg-lab-replication-test/manifest-3-replicas.yaml | sed -n '1,220p' || true
```

Ce diff doit être compris avant toute application GitOps.

---

## 11. Exemple : passer de 2 à 3 replicas sans troisième worker

Cette option est moins recommandée.

Elle nécessite de relâcher l’anti-affinity stricte.

On passerait de :

```text
requiredDuringSchedulingIgnoredDuringExecution
```

à :

```text
preferredDuringSchedulingIgnoredDuringExecution
```

Conséquence :

```text
Kubernetes peut placer deux read replicas sur le même node si nécessaire
```

Avantage :

```text
le troisième pod peut être schedulé avec seulement deux workers
```

Inconvénient :

```text
moins bonne haute disponibilité
répartition moins stricte
```

Cette option doit être validée explicitement avant modification.

Elle ne doit pas être faite automatiquement.

---

## 12. Temps 2 — Changement réel via GitOps

Une fois la simulation validée, on modifie le fichier Git réel :

```text
apps/postgresql-preprod/values.yaml
```

Exemple pour 3 replicas avec troisième worker :

```yaml
postgresql:
  readReplicas:
    replicaCount: 3
```

et dans la nodeAffinity :

```yaml
values:
- rke2-worker-1
- rke2-worker-2
- rke2-worker-3
```

Ensuite vérifier :

```bash
cd /home/masterdevops/rke2-lab
git diff apps/postgresql-preprod/values.yaml
```

Vérifier qu’il n’y a pas de secret :

```bash
grep -RInEi 'password:|postgresPassword|replicationPassword|adminPassword|userPassword|token:|client-key-data|client-certificate-data|BEGIN .*PRIVATE KEY'   apps/postgresql-preprod/values.yaml || true
```

Les seules lignes acceptables sont les noms de clés :

```text
adminPasswordKey: POSTGRES_PASSWORD
replicationPasswordKey: POSTGRES_REPLICATION_PASSWORD
userPasswordKey: POSTGRES_PASSWORD
```

---

## 13. Commit et push

Vérifier le status :

```bash
git status --short
```

Ajouter le fichier :

```bash
git add apps/postgresql-preprod/values.yaml
```

Vérifier le diff staged :

```bash
GIT_PAGER=cat git diff --cached --check
GIT_PAGER=cat git diff --cached --stat
```

Commit :

```bash
git commit -m "feat(postgresql): adjust read replicas for pg-lab"
```

Avant push :

```bash
git fetch origin
git status -sb
```

Si le repo est seulement ahead :

```bash
git push
```

Si le repo est ahead et behind :

```bash
git rebase origin/main
git push
```

---

## 14. Vérification Argo CD avant sync

Après push, Argo CD doit voir l’application `pg-lab` en OutOfSync :

```bash
kubectl -n argocd get application pg-lab -o wide
```

Résultat attendu :

```text
pg-lab   OutOfSync   Healthy
```

Vérifier la révision :

```bash
kubectl -n argocd get application pg-lab -o jsonpath='{.status.sync.revision}{"
"}'
```

Vérifier les ressources OutOfSync :

```bash
kubectl -n argocd get application pg-lab -o jsonpath='{range .status.resources[*]}{.kind}{"	"}{.namespace}{"	"}{.name}{"	"}{.status}{"	"}{.health.status}{"
"}{end}'
```

Lire le diff dans l’interface Argo CD avant sync.

---

## 15. Sync manuel Argo CD

Le sync doit rester manuel.

Ne pas activer :

```text
prune automatique
selfHeal automatique
sync automatique
```

Si le CLI Argo CD n’est pas installé, on peut déclencher un sync manuel via Kubernetes :

```bash
kubectl -n argocd patch application pg-lab --type merge -p '{"operation":{"sync":{"prune":false,"syncStrategy":{"hook":{}}}}}'
```

Ce sync est volontairement :

```text
sans prune
manuel
contrôlé
```

---

## 16. Surveillance après sync

Surveiller l’application Argo CD :

```bash
kubectl -n argocd get application pg-lab -o wide
```

Résultat attendu final :

```text
pg-lab   Synced   Healthy
```

Surveiller les StatefulSets :

```bash
kubectl -n lab-k8s get statefulset pg-lab-postgresql-primary
kubectl -n lab-k8s get statefulset pg-lab-postgresql-read
```

Surveiller les pods :

```bash
kubectl -n lab-k8s get pods -o wide | grep -E 'pg-lab|postgresql'
```

Pour 3 read replicas, résultat attendu :

```text
pg-lab-postgresql-read-0   2/2 Running
pg-lab-postgresql-read-1   2/2 Running
pg-lab-postgresql-read-2   2/2 Running
```

Surveiller les PVC :

```bash
kubectl -n lab-k8s get pvc | grep -E 'pg-lab|postgresql'
```

Un nouveau PVC attendu pour la nouvelle replica serait :

```text
data-pg-lab-postgresql-read-2
```

Il doit être :

```text
Bound
```

---

## 17. Validation applicative

Après sync PostgreSQL, vérifier que l’application Symfony répond toujours :

```bash
curl -I http://blog.k8s.test/articles | head -n 1
```

Résultat attendu :

```text
HTTP/1.1 200 OK
```

Vérifier les pods applicatifs :

```bash
kubectl -n lab-k8s get pods -o wide | grep -E 'blog-back-fpm|blog-back-nginx'
```

Résultat attendu :

```text
FPM Running
Nginx Running
```

---

## 18. Si un pod read replica reste Pending

Vérifier les events :

```bash
kubectl -n lab-k8s describe pod <pod-read-pending> | sed -n '/Events:/,$p'
```

Causes possibles :

```text
anti-affinity trop stricte
pas assez de nodes autorisés
PVC non provisionné
stockage local-path indisponible
nodeSelector incorrect
node non Ready
```

Si le message parle d’anti-affinity ou de hostname insuffisant, il faut revoir :

```text
readReplicas.affinity
nodeAffinity
podAntiAffinity
replicaCount
```

Ne pas supprimer les PVC sans analyse.

---

## 19. Si Argo CD reste OutOfSync

Vérifier les ressources :

```bash
kubectl -n argocd get application pg-lab -o jsonpath='{range .status.resources[*]}{.kind}{"	"}{.namespace}{"	"}{.name}{"	"}{.status}{"	"}{.health.status}{"
"}{end}'
```

Faire un diff local :

```bash
helm template pg-lab apps/postgresql-preprod   --namespace lab-k8s   > /tmp/pg-lab-replication-test/render-current-git.yaml

kubectl diff -f /tmp/pg-lab-replication-test/render-current-git.yaml | sed -n '1,220p' || true
```

Si `kubectl diff` ne montre rien mais Argo CD reste OutOfSync, il peut s’agir de métadonnées ou de suivi Argo CD.

Dans ce cas, analyser dans l’interface Argo CD avant toute action.

---

## 20. Rollback

Si le changement pose problème, le rollback doit se faire par Git.

Revenir au commit précédent :

```bash
git log --oneline -5
```

Revert du commit :

```bash
git revert <commit_id>
```

Push :

```bash
git push
```

Puis sync manuel Argo CD `pg-lab` sans prune.

Ne pas faire de rollback en supprimant les PVC.

Ne pas faire de suppression manuelle de StatefulSet sans procédure.

---

## 21. Règles de sécurité finales

Toujours respecter :

```text
pas de modification directe avec helm upgrade
pas de patch direct du StatefulSet
pas de prune automatique
pas de selfHeal automatique au début
pas de suppression de PVC
pas de changement storageClass sans procédure
pas de modification secret en clair
backup vérifié avant changement
diff lu avant sync
sync manuel uniquement
```

---

## 22. Résumé de la méthode

Méthode complète :

```text
1. Vérifier état Git
2. Vérifier pg-lab Synced/Healthy
3. Vérifier PostgreSQL Running
4. Vérifier backup
5. Préparer une copie temporaire des values
6. Modifier la copie temporaire
7. helm template
8. diff avec le manifest actuel
9. kubectl diff
10. Valider le risque
11. Modifier apps/postgresql-preprod/values.yaml
12. Anti-secret check
13. Commit/push
14. Argo CD pg-lab passe OutOfSync
15. Lire le diff Argo CD
16. Sync manuel sans prune
17. Surveiller StatefulSet/pods/PVC
18. Tester HTTP application
19. Confirmer pg-lab Synced/Healthy
```

Conclusion :

```text
hors Argo CD = simulation
dans Argo CD = changement réel
```

Cette méthode permet d’augmenter la réplication PostgreSQL de manière contrôlée, reproductible et sécurisée.
