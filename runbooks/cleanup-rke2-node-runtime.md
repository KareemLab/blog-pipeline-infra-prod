# Runbook — Nettoyage runtime RKE2/containerd sur un worker

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/cleanup-rke2-node-runtime.py
```

Ce script sert au nettoyage réel du runtime RKE2/containerd sur un worker.

Il peut :

```text
- afficher l’état disque ;
- lister les conteneurs Exited ;
- supprimer les conteneurs Exited ;
- lancer un prune des images inutilisées ;
- vérifier le gain disque.
```

---

## 2. Périmètre de sécurité

Le script agit sur :

```text
/var/lib/rancher/rke2/agent/containerd
```

Il ne supprime pas :

```text
/srv/nfs/rke2-lab
/opt/local-path-provisioner
les PVC Kubernetes
les PV Kubernetes
les volumes PostgreSQL
les anciens volumes applicatifs local-path
```

Donc il ne nettoie pas les données persistantes.

---

## 3. Wrapper utilisé

Le script utilise le wrapper :

```bash
sudo -n /usr/local/sbin/rke2-runtime-maintenance
```

Ce wrapper encapsule `crictl` avec l’endpoint RKE2 :

```text
unix:///run/k3s/containerd/containerd.sock
```

---

## 4. Toutes les façons d’appeler le script runtime

## 4.1 Aide du script

```bash
python3 scripts/cleanup-rke2-node-runtime.py --help
```

But :

```text
Afficher les options disponibles.
```

---

## 4.2 Diagnostic avec le nœud par défaut

```bash
python3 scripts/cleanup-rke2-node-runtime.py
```

But :

```text
Afficher l’état runtime du nœud par défaut.
```

Aucune suppression.

---

## 4.3 Diagnostic sur worker-2

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint
```

But :

```text
Voir l’état disque, containerd et les conteneurs Exited sur worker-2.
```

Aucune suppression.

---

## 4.4 Diagnostic sur worker-1

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-1-maint
```

But :

```text
Voir l’état runtime sur worker-1.
```

Aucune suppression.

---

## 4.5 Nettoyage des conteneurs Exited

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute
```

Effet :

```text
Supprime les conteneurs Exited.
Ne lance pas le prune des images.
```

---

## 4.6 Nettoyage complet runtime + images inutilisées

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images
```

Effet :

```text
1. affiche l’état disque ;
2. supprime les conteneurs Exited ;
3. lance le prune des images inutilisées ;
4. affiche l’état disque final.
```

---

## 4.7 Commande à ne pas utiliser seule

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --prune-images
```

Pourquoi l’éviter :

```text
Le prune d’images doit être couplé à --execute.
Sans --execute, le script doit rester en mode diagnostic ou refuser l’action réelle.
```

Commande correcte :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images
```

---

## 5. Explication des arguments

| Argument | Rôle |
|---|---|
| `--node` | Définit le nœud cible via son alias SSH. |
| `--execute` | Autorise les actions réelles de nettoyage. |
| `--prune-images` | Demande le prune des images inutilisées. |
| `--help` | Affiche l’aide du script. |

---

## 6. Différence entre sans execute et avec execute

Sans `--execute` :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint
```

Effet :

```text
Diagnostic uniquement.
Aucun conteneur supprimé.
Aucune image supprimée.
```

Avec `--execute` :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute
```

Effet :

```text
Supprime les conteneurs Exited.
Ne supprime pas encore les images inutilisées.
```

Avec `--execute --prune-images` :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images
```

Effet :

```text
Supprime les conteneurs Exited.
Supprime les images inutilisées.
Libère potentiellement de l’espace disque.
```

---

## 7. Exemple réel sur worker-2

Avant nettoyage :

```text
/           78%
containerd 8,3G
overlayfs  6,3G
content    2,0G
```

Commande lancée :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images
```

Images supprimées :

```text
docker.io/rancher/mirrored-pause:3.6
docker.io/kareemdev2/blog-back-fpm:latest
docker.io/kareemdev2/blog-back-fpm:prod-83
```

Après nettoyage :

```text
/           72%
containerd 7,0G
overlayfs  5,3G
content    1,7G
```

---

## 8. Pourquoi supprimer les pods Completed avant le prune

Des anciens hooks applicatifs `Completed` peuvent rester sur un worker.

Exemple :

```text
blog-back-node-assets-presync-*
blog-back-migration-presync-*
```

Commande :

```bash
kubectl get pods -n lab-k8s   --field-selector spec.nodeName=rke2-worker-2,status.phase=Succeeded   -o name | grep -E 'blog-back-(node-assets|migration)-presync' | xargs -r kubectl delete -n lab-k8s
```

Cette commande supprime uniquement les anciens pods Completed applicatifs sur worker-2.

---

## 9. Explication de cette commande

| Élément | Rôle |
|---|---|
| `kubectl get pods` | Liste les pods. |
| `-n lab-k8s` | Cible le namespace applicatif. |
| `--field-selector spec.nodeName=rke2-worker-2,status.phase=Succeeded` | Filtre les pods Completed sur worker-2. |
| `-o name` | Affiche les noms Kubernetes. |
| `grep -E` | Garde les hooks applicatifs ciblés. |
| `xargs -r kubectl delete -n lab-k8s` | Supprime uniquement s’il y a un résultat. |

---

## 10. Vérifications avant prune images

Avant de lancer :

```bash
--execute --prune-images
```

vérifier :

```bash
kubectl get pods -n lab-k8s -o wide | grep rke2-worker-2 || true
```

Si les pods applicatifs tournent encore sur worker-2, ne pas lancer le prune sans analyse.

---

## 11. Vérifications après nettoyage

```bash
kubectl get pods -n lab-k8s -o wide
kubectl get pods -A | grep -v Running | grep -v Completed
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint
ssh rke2-worker-2-maint 'sudo -n /usr/local/sbin/rke2-runtime-maintenance disk'
```

---

## 12. Résumé des appels possibles

| Commande | Effet |
|---|---|
| `python3 scripts/cleanup-rke2-node-runtime.py` | Diagnostic sur le nœud par défaut. |
| `python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint` | Diagnostic sur worker-2. |
| `python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-1-maint` | Diagnostic sur worker-1. |
| `python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute` | Supprime les conteneurs Exited. |
| `python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images` | Supprime conteneurs Exited + images inutilisées. |
| `python3 scripts/cleanup-rke2-node-runtime.py --help` | Affiche l’aide. |

---

## 13. Ce qu’il ne faut pas faire

Ne pas supprimer manuellement :

```text
/opt/local-path-provisioner
/srv/nfs/rke2-lab
les dossiers de PVC
les dossiers PostgreSQL
```

Ne pas lancer un prune si le nœud porte encore les workloads applicatifs concernés.

---

## 14. Workflow recommandé

```text
1. Diagnostic images.
2. Diagnostic runtime.
3. Vérification des pods sur le worker.
4. Suppression éventuelle des anciens pods Completed.
5. Nettoyage des conteneurs Exited avec --execute.
6. Vérification cluster.
7. Nettoyage images inutilisées avec --execute --prune-images.
8. Diagnostic final.
```

---

## 15. Conclusion

Le script runtime est l’outil de nettoyage réel.

Il complète le script images :

```text
cleanup-rke2-node-images.py  -> diagnostiquer
cleanup-rke2-node-runtime.py -> nettoyer
```

Utilisé correctement, il permet de libérer de l’espace disque sans toucher aux données persistantes.
