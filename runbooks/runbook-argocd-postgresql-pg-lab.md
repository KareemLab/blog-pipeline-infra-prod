# Runbook — Argo CD PostgreSQL séparé (`pg-lab`)

## 1. Objectif

Ce runbook explique pourquoi on crée une application Argo CD séparée pour PostgreSQL.

Application Argo CD prévue :

```text
pg-lab
```

Chemin Git :

```text
apps/postgresql-preprod
```

Namespace Kubernetes :

```text
lab-k8s
```

Release Helm existante :

```text
pg-lab
```

Chart Helm :

```text
bitnami/postgresql
```

Version du chart :

```text
18.6.7
```

Version PostgreSQL :

```text
18.4.0
```

L’objectif n’est pas de redéployer PostgreSQL brutalement.

L’objectif est de faire entrer PostgreSQL dans GitOps progressivement, avec une application Argo CD dédiée, sans le mélanger avec l’application Symfony.

---

## 2. Situation actuelle

L’application Symfony est déjà gérée par Argo CD :

```text
Application Argo CD : blog-preprod
Chemin Git : apps/blog-preprod
Namespace : lab-k8s
```

Cette application gère notamment :

```text
FPM
Nginx
services applicatifs
ingress
jobs hooks
PVC applicatifs
network policies applicatives
```

PostgreSQL existe déjà dans le cluster, mais il n’est pas géré par `blog-preprod`.

Il est géré par Helm directement :

```text
Release Helm : pg-lab
Namespace : lab-k8s
Chart : postgresql-18.6.7
App version : 18.4.0
Status : deployed
```

Ressources PostgreSQL présentes :

```text
statefulset.apps/pg-lab-postgresql-primary
statefulset.apps/pg-lab-postgresql-read

pod/pg-lab-postgresql-primary-0
pod/pg-lab-postgresql-read-0
pod/pg-lab-postgresql-read-1

service/pg-lab-postgresql-primary
service/pg-lab-postgresql-read

PVC data-pg-lab-postgresql-primary-0
PVC data-pg-lab-postgresql-read-0
PVC data-pg-lab-postgresql-read-1
```

Les objets PostgreSQL contiennent les annotations et labels Helm :

```text
meta.helm.sh/release-name: pg-lab
meta.helm.sh/release-namespace: lab-k8s
app.kubernetes.io/instance: pg-lab
app.kubernetes.io/managed-by: Helm
```

Cela confirme que PostgreSQL est actuellement piloté par Helm.

---

## 3. Pourquoi une application Argo CD séparée

PostgreSQL est une ressource stateful.

Il ne doit pas être mélangé avec l’application Symfony.

La bonne séparation est :

```text
blog-preprod
→ application Symfony
→ sync fréquent
→ CD applicatif normal

pg-lab
→ PostgreSQL
→ sync rare
→ sync manuel au début
→ actions contrôlées
```

Pourquoi cette séparation est importante ?

Parce qu’un mauvais changement PostgreSQL peut impacter :

```text
StatefulSet PostgreSQL
PVC data
primary / read replicas
service de connexion
référence de secret
version d’image
version de chart
resources
affinity / placement
stockage local-path
```

PostgreSQL ne doit donc pas être synchronisé automatiquement à chaque déploiement applicatif.

---

## 4. Ce que permet Argo CD pour PostgreSQL

L’application Argo CD `pg-lab` permet de voir PostgreSQL dans Argo CD.

Elle permet aussi de piloter sa configuration Helm depuis Git.

Ce que cela apporte :

```text
visibilité GitOps de PostgreSQL
historique Git des changements PostgreSQL
diff avant sync
contrôle manuel des changements
séparation avec blog-preprod
reproductibilité du chart et des values
documentation de la configuration BDD
```

Exemples de changements qui pourront être gérés plus tard par GitOps :

```text
changer resourcesPreset
définir resources explicites CPU/RAM
ajuster replicaCount des read replicas
modifier affinity / node placement
figer ou changer une version d’image
modifier les options metrics
ajouter des labels ou annotations
préparer un upgrade de chart
```

---

## 5. Ce que cette application ne doit pas faire

L’application Argo CD PostgreSQL ne doit pas être utilisée comme un bouton de réparation rapide.

Elle ne doit pas servir à :

```text
restaurer une base PostgreSQL
supprimer des PVC
recréer une base depuis zéro
changer un secret en clair
déclencher un upgrade non validé
faire un sync automatique non contrôlé
pruner des ressources stateful sans audit
remplacer les backups
réparer Canal/CNI
réparer un problème node ou stockage
```

La restauration PostgreSQL reste une opération admin séparée.

Règle :

```text
restore PostgreSQL = masterdevops uniquement
```

---

## 6. Stratégie de sécurité

Pour la première intégration Argo CD de PostgreSQL, la stratégie retenue est prudente.

L’application Argo CD `pg-lab` est créée :

```text
sans syncPolicy
sans automated
sans prune
sans selfHeal
```

Cela signifie :

```text
pas de synchronisation automatique
pas de suppression automatique de ressources
pas de correction automatique du drift
pas d’action sans décision humaine
```

Le sync doit être manuel.

Avant tout sync réel, il faut vérifier :

```text
backup disponible
PostgreSQL Running
primary 1/1
read replicas 2/2
PVC Bound
diff Argo CD compréhensible
pas de changement destructif
pas de suppression de PVC
pas de changement inattendu de StatefulSet
```

---

## 7. Pourquoi garder le nom `pg-lab`

La release Helm existante s’appelle :

```text
pg-lab
```

Il est recommandé que l’application Argo CD utilise aussi le release name :

```text
pg-lab
```

Dans le manifest Argo CD :

```yaml
helm:
  releaseName: pg-lab
```

Pourquoi ?

Parce que le chart Bitnami PostgreSQL utilise le nom de release dans plusieurs labels et selectors.

Exemple :

```text
app.kubernetes.io/instance: pg-lab
```

Changer le release name pourrait modifier les noms d’objets, les labels ou les selectors.

Pour éviter un risque inutile, on garde :

```text
releaseName: pg-lab
```

---

## 8. Structure Git créée

La structure prévue est :

```text
apps/postgresql-preprod/
├── Chart.yaml
├── Chart.lock
├── values.yaml
└── charts/
    └── postgresql-18.6.7.tgz
```

Application Argo CD :

```text
argocd/applications/pg-lab-application.yaml
```

---

## 9. Fichier `Chart.yaml`

Le fichier :

```text
apps/postgresql-preprod/Chart.yaml
```

déclare un wrapper chart.

Son rôle est simple :

```text
dire à Helm d’utiliser le chart Bitnami PostgreSQL en version 18.6.7
```

Contenu :

```yaml
apiVersion: v2
name: postgresql-preprod
description: Wrapper chart for pg-lab PostgreSQL preprod
type: application
version: 0.1.0
dependencies:
  - name: postgresql
    version: 18.6.7
    repository: https://charts.bitnami.com/bitnami
```

Ce fichier ne contient aucun secret.

---

## 10. Fichier `values.yaml`

Le fichier :

```text
apps/postgresql-preprod/values.yaml
```

contient les valeurs Helm de PostgreSQL.

Comme PostgreSQL est utilisé comme dépendance Helm, les values sont placées sous la clé :

```yaml
postgresql:
```

Les valeurs ont été exportées depuis la release Helm existante :

```bash
helm get values pg-lab -n lab-k8s -o yaml
```

Points importants contenus dans les values :

```text
architecture: replication
database: blogkubernetesdb
username: iksstudent
existingSecret: blog-back-secret
replicationUsername: repl_user
metrics.enabled: true
primary sur rke2-worker-2
read replicas sur rke2-worker-1 et rke2-worker-2
persistence 5Gi local-path
replicaCount readReplicas: 2
resourcesPreset: nano
```

---

## 11. Gestion des secrets

Le fichier `values.yaml` ne contient pas de mot de passe en clair.

Il référence le secret Kubernetes existant :

```text
blog-back-secret
```

Les clés utilisées sont :

```text
POSTGRES_PASSWORD
POSTGRES_REPLICATION_PASSWORD
```

Extrait :

```yaml
auth:
  existingSecret: blog-back-secret
  secretKeys:
    adminPasswordKey: POSTGRES_PASSWORD
    replicationPasswordKey: POSTGRES_REPLICATION_PASSWORD
    userPasswordKey: POSTGRES_PASSWORD
```

Cela signifie :

```text
le secret réel reste dans Kubernetes
le mot de passe n’est pas versionné
Git contient seulement le nom du Secret et les noms des clés
```

Règle :

```text
ne jamais commiter un mot de passe PostgreSQL en clair
ne jamais commiter un token
ne jamais commiter un kubeconfig
```

---

## 12. Fichier `Chart.lock`

Le fichier :

```text
apps/postgresql-preprod/Chart.lock
```

est généré par :

```bash
helm dependency build apps/postgresql-preprod
```

Il fige la dépendance Helm exacte.

Il permet de savoir précisément quelle version du chart est utilisée.

Ce fichier est utile à versionner pour la reproductibilité.

---

## 13. Fichier `.tgz` du chart

Le fichier généré est :

```text
apps/postgresql-preprod/charts/postgresql-18.6.7.tgz
```

Taille observée :

```text
88K
```

Dans ce lab, il est acceptable de le versionner.

Avantage :

```text
Argo CD n’a pas besoin de télécharger le chart Bitnami au moment du sync
la version exacte testée est embarquée dans Git
le rendu est plus reproductible
```

Inconvénient :

```text
le repo contient une archive Helm
il faudra la mettre à jour lors d’un upgrade de chart
```

Pour ce lab, le choix recommandé est de versionner le `.tgz`.

---

## 14. Fichier Argo CD Application

Le fichier :

```text
argocd/applications/pg-lab-application.yaml
```

déclare l’application Argo CD séparée.

Contenu :

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: pg-lab
  namespace: argocd
spec:
  project: default
  source:
    repoURL: git@github.com:KareemLab/homelab-blog-preprod.git
    targetRevision: main
    path: apps/postgresql-preprod
    helm:
      releaseName: pg-lab
  destination:
    server: https://kubernetes.default.svc
    namespace: lab-k8s
```

Points importants :

```text
name: pg-lab
path: apps/postgresql-preprod
releaseName: pg-lab
destination namespace: lab-k8s
pas de syncPolicy
pas de automated
pas de prune
pas de selfHeal
```

---

## 15. État attendu juste après création de l’Application

Si l’Application Argo CD est appliquée avant le commit/push Git, Argo CD peut afficher :

```text
SYNC STATUS = Unknown
REVISION = main
```

Et la condition :

```text
app path does not exist
```

C’est normal si le dossier :

```text
apps/postgresql-preprod
```

existe seulement en local et pas encore dans GitHub.

La correction est :

```text
commit
push
refresh Argo CD
```

Après le push, Argo CD pourra lire le chemin Git.

---

## 16. Vérifications avant commit

Avant de commiter les fichiers PostgreSQL, il faut vérifier qu’il n’y a pas de secret.

Commande utilisée :

```bash
grep -RInEi 'password:|postgresPassword|replicationPassword|adminPassword|userPassword|token:|client-key-data|client-certificate-data|BEGIN .*PRIVATE KEY'   apps/postgresql-preprod   argocd/applications/pg-lab-application.yaml || true
```

Sortie possible :

```text
apps/postgresql-preprod/values.yaml:9:      adminPasswordKey: POSTGRES_PASSWORD
apps/postgresql-preprod/values.yaml:10:      replicationPasswordKey: POSTGRES_REPLICATION_PASSWORD
apps/postgresql-preprod/values.yaml:11:      userPasswordKey: POSTGRES_PASSWORD
```

Interprétation :

```text
ce sont des noms de clés
ce ne sont pas des secrets
c’est acceptable
```

---

## 17. Vérification de reproductibilité

Le manifest actuel de la release Helm a été exporté :

```bash
helm get manifest pg-lab -n lab-k8s > /tmp/pg-lab-audit/manifest.yaml
```

Puis le rendu local a été testé :

```bash
helm template pg-lab apps/postgresql-preprod   --namespace lab-k8s   > /tmp/pg-lab-audit/render-wrapper-from-git.yaml
```

Comparaison :

```bash
diff -u /tmp/pg-lab-audit/manifest.yaml /tmp/pg-lab-audit/render-wrapper-from-git.yaml | head -120
```

Résultat observé :

```text
diff uniquement sur les commentaires Helm # Source
et une ligne vide finale
```

Conclusion :

```text
apps/postgresql-preprod reproduit bien le PostgreSQL actuel
```

C’est une étape importante avant d’autoriser Argo CD à voir PostgreSQL.

---

## 18. Ce qu’on peut faire avec `pg-lab` dans Argo CD

On peut :

```text
voir PostgreSQL dans Argo CD
voir s’il est Synced ou OutOfSync
voir le diff avant sync
synchroniser manuellement après validation
suivre l’état Healthy/Degraded
gérer les values Helm depuis Git
préparer un upgrade contrôlé du chart
documenter l’état attendu de PostgreSQL
```

On peut aussi utiliser Argo CD pour constater un drift :

```text
quelqu’un a modifié Helm directement
quelqu’un a changé un StatefulSet à la main
un service ou une annotation a changé
```

Mais au début, on évite `selfHeal`.

---

## 19. Ce qu’on ne doit pas faire avec `pg-lab`

Ne pas utiliser `pg-lab` pour :

```text
sync automatique
prune automatique
suppression de PVC
restore PostgreSQL
test destructif
upgrade de chart sans backup
changement de secret en clair
changement de storageClass sans analyse
changement de volume size sans procédure
déplacement du primary sans validation
réparation Canal/CNI
```

Règle :

```text
pas de sync PostgreSQL sans lire le diff
pas de sync PostgreSQL sans backup récent
pas de prune sur PostgreSQL au début
pas de selfHeal au début
```

---

## 20. Procédure de sync manuel recommandée

Avant un sync manuel PostgreSQL :

```bash
kubectl -n lab-k8s get sts,pods,svc,pvc | grep -E 'pg-lab|postgresql'
```

Vérifier :

```text
primary 1/1
read replicas 2/2
pods Running
PVC Bound
```

Vérifier Argo CD :

```bash
kubectl -n argocd get application pg-lab -o wide
```

Vérifier le diff depuis l’interface Argo CD.

Ne lancer le sync que si le diff est compris.

Après sync :

```bash
kubectl -n lab-k8s rollout status statefulset/pg-lab-postgresql-primary --timeout=180s
kubectl -n lab-k8s rollout status statefulset/pg-lab-postgresql-read --timeout=180s
kubectl -n lab-k8s get pods -o wide | grep -E 'pg-lab|postgresql'
```

Puis vérifier l’application Symfony :

```bash
curl -I http://blog.k8s.test/articles | head -n 1
```

Résultat attendu :

```text
HTTP/1.1 200 OK
```

---

## 21. Responsabilités

### `maintenance-monitoring`

Peut observer certains symptômes applicatifs.

Ne doit pas gérer PostgreSQL.

Ne doit pas faire de sync PostgreSQL.

Ne doit pas restaurer PostgreSQL.

---

### `masterdevops`

Responsable de :

```text
création/modification de l’application Argo CD pg-lab
sync PostgreSQL
backup avant modification
restore PostgreSQL
upgrade du chart
gestion des incidents stateful
analyse des PVC
gestion des secrets Kubernetes
```

---

## 22. Conclusion

L’application Argo CD séparée `pg-lab` sert à rendre PostgreSQL visible et pilotable par GitOps, sans le mélanger avec l’application Symfony.

La stratégie est volontairement prudente :

```text
application Argo CD séparée
releaseName conservé pg-lab
chart version figée
values exportées depuis l’existant
secrets non versionnés
sync manuel
pas de prune
pas de selfHeal
```

Ce modèle permet d’améliorer la traçabilité sans prendre de risque inutile sur la base de données.

Résumé :

```text
blog-preprod
→ application Symfony
→ CD applicatif

pg-lab
→ PostgreSQL
→ GitOps stateful contrôlé

masterdevops
→ responsable des actions PostgreSQL sensibles
```
