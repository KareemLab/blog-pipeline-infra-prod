# Restauration — Sécurité manuelle

Ce document est un runbook local non versionné.

## 1. Principe

Le fichier versionné est un template sécurisé :

`postgresql/21-postgresql-real-restore-job-template.yaml`

Ce template ne doit pas être exécuté tel quel.

Il contient trois sécurités :

- `suspend: true`
- `BACKUP_FILE=/backups/CHANGE_ME.dump`
- `RESTORE_CONFIRMATION=CHANGE_ME_TO_RUN`

## 2. Lister les dumps disponibles

Avant une restauration réelle, il faut lister les backups disponibles dans le PVC.

Le but est de choisir explicitement le dump à restaurer.

On ne restaure pas automatiquement le dernier dump.
Le dernier dump peut contenir un état déjà corrompu si le problème existait avant le backup.

Commande de listing :

```bash
cd ~/rke2-lab

k delete pod -n lab-k8s backup-list --ignore-not-found

cat > /tmp/backup-list-pod.yaml <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: backup-list
  namespace: lab-k8s
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: rke2-worker-2
  containers:
    - name: backup-list
      image: registry-1.docker.io/bitnami/postgresql:latest
      command: ["/bin/bash", "-lc", "echo === Dumps disponibles ===; ls -lh /backups/*.dump"]
      volumeMounts:
        - name: backup-storage
          mountPath: /backups
          readOnly: true
  volumes:
    - name: backup-storage
      persistentVolumeClaim:
        claimName: postgresql-logical-backups
EOF

k apply -f /tmp/backup-list-pod.yaml
sleep 5
k logs -n lab-k8s backup-list
k delete pod -n lab-k8s backup-list
```

## 3. Choisir le dump et préparer les variables

Après avoir listé les dumps disponibles, choisir explicitement le fichier à restaurer.

Exemple :

```bash
cd ~/rke2-lab

RESTORE_BACKUP="/backups/blogkubernetesdb-20260522-121500.dump"
RESTORE_JOB_NAME="postgresql-real-restore-$(date +%Y%m%d-%H%M%S)"
```

`RESTORE_BACKUP` contient le dump choisi.
`RESTORE_JOB_NAME` donne un nom unique au Job cloné.

```bash
echo "RESTORE_BACKUP=${RESTORE_BACKUP}"
echo "RESTORE_JOB_NAME=${RESTORE_JOB_NAME}"
```

## 4. Cloner le template vers un manifest temporaire

Ne pas modifier directement le template versionné.
Le jour J, on crée une copie temporaire dans `/tmp`.

```bash
cp postgresql/21-postgresql-real-restore-job-template.yaml /tmp/postgresql-real-restore-run.yaml
ls -lh /tmp/postgresql-real-restore-run.yaml
```

Le fichier `/tmp/postgresql-real-restore-run.yaml` est le manifest de restauration du jour.
Il sera personnalisé avec le dump choisi et un nom unique de Job.

## 5. Injecter les valeurs dans le manifest temporaire

Cette étape personnalise la copie temporaire du template.
Elle ne modifie pas le template versionné.

```bash
python3 <<PY
from pathlib import Path

path = Path("/tmp/postgresql-real-restore-run.yaml")
text = path.read_text()

text = text.replace("name: postgresql-real-restore", f"name: ${RESTORE_JOB_NAME}", 1)
text = text.replace("value: /backups/CHANGE_ME.dump", f"value: ${RESTORE_BACKUP}", 1)
text = text.replace("value: CHANGE_ME_TO_RUN", "value: YES_RESTORE_BLOGKUBERNETESDB", 1)

path.write_text(text)
print("Manifest temporaire généré :", path)
PY
```

Le manifest généré reste suspendu grâce à `suspend: true`.
À ce stade, aucune restauration ne démarre.



## 6. Vérifier le manifest temporaire

Avant de créer le Job, vérifier que le manifest temporaire contient bien la bonne structure et les bonnes valeurs.

```bash
grep -nE 'kind:|name: postgresql-real-restore|namespace:|suspend:|claimName|pg_restore|psql' \
  /tmp/postgresql-real-restore-run.yaml

grep -nA2 -E 'name: BACKUP_FILE|name: RESTORE_CONFIRMATION|name: PGHOST|name: PGDATABASE' \
  /tmp/postgresql-real-restore-run.yaml
```

La première commande vérifie la structure du Job.
La deuxième commande affiche les variables importantes avec leurs lignes `value:`.

À vérifier :

- `kind: Job`
- le nom du Job cloné est unique ;
- `namespace: lab-k8s`
- `suspend: true`
- `claimName: postgresql-logical-backups`
- `BACKUP_FILE` pointe vers le dump choisi ;
- `RESTORE_CONFIRMATION` vaut `YES_RESTORE_BLOGKUBERNETESDB` ;
- `PGHOST` vaut `pg-lab-postgresql-primary` ;
- `PGDATABASE` vient du Secret `blog-back-secret` ;
- `pg_restore` est présent ;
- `psql` est présent.



## 7. Dry-run serveur

Le dry-run serveur valide le manifest auprès de Kubernetes sans créer le Job.

```bash
k apply --dry-run=server -f /tmp/postgresql-real-restore-run.yaml
```

Cette commande ne crée rien.
Elle vérifie uniquement que le manifest est valide côté API Kubernetes.

## 8. Appliquer le Job suspendu

Cette étape crée le Job dans Kubernetes, mais il reste suspendu.
Aucun Pod ne doit démarrer à cette étape.

```bash
k apply -f /tmp/postgresql-real-restore-run.yaml

k get job -n lab-k8s "$RESTORE_JOB_NAME"
k get pods -n lab-k8s | grep "$RESTORE_JOB_NAME" || true
```

Résultat attendu :

- le Job existe ;
- aucun Pod de restauration n’est créé ;
- aucune restauration ne démarre.

## 9. Désuspendre volontairement le Job

Cette étape déclenche réellement la restauration.
Elle ne doit être exécutée qu’après validation humaine.

Avant cette commande, vérifier que :

- le dump choisi est correct ;
- `RESTORE_CONFIRMATION` vaut `YES_RESTORE_BLOGKUBERNETESDB` ;
- le Job est toujours en `suspend: true` ;
- l’application est arrêtée si nécessaire pour éviter les écritures pendant la restauration.

Commande :

```bash
k patch job -n lab-k8s "$RESTORE_JOB_NAME" \
  --type=merge \
  -p '{"spec":{"suspend":false}}'
```

Après cette commande, Kubernetes crée le Pod du Job et le script lance `pg_restore`.

## 10. Suivre les logs du Job

Après désuspension, Kubernetes crée un Pod temporaire pour exécuter la restauration.

```bash
POD_NAME="$(k get pods -n lab-k8s -l job-name="$RESTORE_JOB_NAME" -o jsonpath='{.items[0].metadata.name}')"

k logs -n lab-k8s "$POD_NAME" -f
```

Les logs doivent montrer la vérification du dump, le lancement de `pg_restore`, puis la vérification SQL avec `psql`.

## 11. Vérifier la base après restauration

Après les logs du Job, vérifier directement dans la vraie base que la restauration a produit le résultat attendu.


```bash
k exec -n lab-k8s pg-lab-postgresql-primary-0 -c postgresql -- bash -lc '
export PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"

echo "=== Articles après restauration réelle ==="
psql -U "$POSTGRES_USER" -d blogkubernetesdb -c "
select id, title, created_at
from article
order by id;
"
'
```

Résultat attendu : la base doit correspondre au contenu du dump choisi.


## 12. Nettoyer le Job et le Pod temporaire

Après validation, supprimer le Job cloné.
La suppression du Job supprime aussi le Pod temporaire créé pour la restauration.

```bash
k delete job -n lab-k8s "$RESTORE_JOB_NAME" --ignore-not-found

k get pods -n lab-k8s | grep "$RESTORE_JOB_NAME" || true
```

Résultat attendu : aucun Pod lié au Job de restauration ne doit rester.

## 13. Nettoyer les variables locales

Après suppression du Job cloné, nettoyer les variables utilisées dans le terminal.

```bash
unset RESTORE_BACKUP
unset RESTORE_JOB_NAME
unset POD_NAME
```

Vérification optionnelle :

```bash
echo "${RESTORE_BACKUP:-variable RESTORE_BACKUP supprimée}"
echo "${RESTORE_JOB_NAME:-variable RESTORE_JOB_NAME supprimée}"
echo "${POD_NAME:-variable POD_NAME supprimée}"
```






