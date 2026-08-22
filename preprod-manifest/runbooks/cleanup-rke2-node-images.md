# Runbook — Diagnostic et modes d’appel du script images RKE2

## 1. Objectif

Ce runbook documente le script :

```bash
scripts/cleanup-rke2-node-images.py
```

Ce script sert à analyser les images présentes sur un nœud RKE2/containerd.

Il permet de savoir si un worker conserve encore des images applicatives inutiles après une migration de workloads.

Exemple de cas réel :

```text
Les pods applicatifs blog-back ont été déplacés de rke2-worker-2 vers rke2-worker-1.
On veut vérifier si rke2-worker-2 garde encore des images applicatives inutiles.
```

---

## 2. Point important

Le script `cleanup-rke2-node-images.py` est un script de **diagnostic images**.

Dans l’état actuel du lab, le nettoyage réel des images n’est pas effectué par ce script. Le wrapper associé est volontairement limité au diagnostic.

Le script peut afficher un mode `DRY-RUN`, des candidates de nettoyage, et expliquer qu’aucune image n’est supprimée.

Pour le nettoyage réel du runtime et des images inutilisées, utiliser :

```bash
scripts/cleanup-rke2-node-runtime.py
```

---

## 3. Emplacement du script

Depuis le bastion :

```bash
cd /home/masterdevops/rke2-lab
```

Le script est ici :

```bash
scripts/cleanup-rke2-node-images.py
```

---

## 4. Wrapper utilisé

Le script utilise le wrapper :

```bash
sudo -n /usr/local/sbin/rke2-image-maintenance
```

Explication :

| Élément | Rôle |
|---|---|
| `sudo` | Exécute le wrapper avec les droits root. |
| `-n` | Mode non interactif : si sudo demande un mot de passe, la commande échoue au lieu de bloquer. |
| `/usr/local/sbin/rke2-image-maintenance` | Wrapper limité au diagnostic images. |

Ce wrapper évite d’accorder un sudo global au technicien.

---

## 5. Toutes les façons d’appeler le script images

## 5.1 Afficher l’aide du script

Commande :

```bash
python3 scripts/cleanup-rke2-node-images.py --help
```

But :

```text
Afficher les options disponibles du script.
```

Quand l’utiliser :

```text
Avant utilisation, pour vérifier les arguments supportés par la version courante du script.
```

---

## 5.2 Lancer le diagnostic avec les valeurs par défaut

Commande :

```bash
python3 scripts/cleanup-rke2-node-images.py
```

But :

```text
Lancer le diagnostic images avec le nœud par défaut défini dans le script.
```

Dans le lab, le nœud par défaut est généralement :

```text
rke2-worker-2-maint
```

Ce mode ne supprime rien.

Sortie attendue :

```text
MODE=DRY-RUN
NODE=rke2-worker-2-maint
```

---

## 5.3 Lancer le diagnostic sur worker-2

Commande :

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint
```

Décomposition :

| Élément | Rôle |
|---|---|
| `python3` | Lance le script Python. |
| `scripts/cleanup-rke2-node-images.py` | Script de diagnostic images. |
| `--node` | Indique le nœud cible. |
| `rke2-worker-2-maint` | Alias SSH de maintenance vers `rke2-worker-2`. |

Utilisation typique :

```text
Après avoir déplacé des pods hors de worker-2, vérifier si des images applicatives restent présentes sur worker-2.
```

---

## 5.4 Lancer le diagnostic sur worker-1

Commande :

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-1-maint
```

But :

```text
Diagnostiquer les images présentes sur rke2-worker-1.
```

Utilisation typique :

```text
Vérifier que worker-1 possède bien les images applicatives après migration des pods.
```

---

## 5.5 Mode execute du script images

Commande :

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint --execute
```

But attendu :

```text
Demander un nettoyage réel depuis le script images.
```

Comportement attendu dans ce lab :

```text
Le nettoyage réel est volontairement désactivé pour ce script.
Le script reste diagnostic only ou affiche un message indiquant que le mode nettoyage réel est désactivé.
```

Message attendu ou équivalent :

```text
Dry-run uniquement : aucune image supprimée.
Le mode nettoyage réel est désactivé pour l'instant.
Le wrapper actuel est diagnostic only.
```

Interprétation :

```text
Même avec --execute, ce script ne doit pas supprimer d’image dans la configuration actuelle.
```

Pourquoi ?

```text
Le script images sert à identifier les candidates.
Le nettoyage réel doit passer par le script runtime.
```

---

## 5.6 Mode execute sur worker-1

Commande :

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-1-maint --execute
```

But :

```text
Tester le même comportement sur worker-1.
```

Comportement attendu :

```text
Aucune suppression réelle si le wrapper images reste diagnostic only.
```

---

## 5.7 Commande à ne pas confondre avec le runtime

Ne pas confondre :

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint --execute
```

avec :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images
```

Différence :

| Script | Rôle |
|---|---|
| `cleanup-rke2-node-images.py` | Diagnostic images, candidates, comparaison avec manifests. |
| `cleanup-rke2-node-runtime.py` | Nettoyage réel du runtime containerd. |

---

## 6. Ce que le script images affiche

## 6.1 Préflight SSH/wrapper

Exemple :

```text
===== Préflight SSH/wrapper =====
SSH_OK_ON_rke2-worker-2
WRAPPER_SUDO_OK
```

Signification :

| Sortie | Signification |
|---|---|
| `SSH_OK_ON_rke2-worker-2` | Le bastion peut joindre le worker en SSH. |
| `WRAPPER_SUDO_OK` | Le wrapper sudo limité est utilisable. |

---

## 6.2 Host

Exemple :

```text
===== Host =====
rke2-worker-2
```

But :

```text
Confirmer que l’alias SSH pointe vers le bon nœud.
```

---

## 6.3 df /

Exemple :

```text
Filesystem                         Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv   23G   16G  6,2G  72% /
```

Interprétation :

| Colonne | Rôle |
|---|---|
| `Size` | Taille totale du disque racine. |
| `Used` | Espace utilisé. |
| `Avail` | Espace disponible. |
| `Use%` | Pourcentage d’utilisation. |

---

## 6.4 containerd

Exemple :

```text
8,3G /var/lib/rancher/rke2/agent/containerd
```

Ce répertoire contient les données runtime RKE2/containerd :

```text
images
layers
snapshots
metadata runtime
```

---

## 6.5 overlayfs / content

Exemple :

```text
6,3G /var/lib/rancher/rke2/agent/containerd/io.containerd.snapshotter.v1.overlayfs
2,0G /var/lib/rancher/rke2/agent/containerd/io.containerd.content.v1.content
```

Explication :

| Chemin | Rôle |
|---|---|
| `overlayfs` | Snapshots et couches montées ou préparées pour les conteneurs. |
| `content` | Blobs et contenus d’images containerd. |

---

## 6.6 /opt/local-path-provisioner

Exemple :

```text
570M /opt/local-path-provisioner
```

Important :

```text
Ce chemin contient les volumes local-path.
Il ne doit pas être supprimé par les scripts de nettoyage runtime/images.
```

---

## 7. Images utilisées par les pods Kubernetes

Exemple :

```text
===== Images utilisées par les pods Kubernetes =====
- kareemdev2/blog-back-fpm:prod-83
- kareemdev2/blog-back-nginx:prod-83
- kareemdev2/blog-back-node:prod-83
```

Ce bloc indique les images utilisées ou déclarées par les pods du cluster.

Attention :

```text
Une image peut être utilisée dans le cluster mais ne pas être présente localement sur le nœud analysé.
```

---

## 8. Images déclarées dans apps/blog-preprod

Exemple :

```text
===== Images déclarées dans apps/blog-preprod =====
- kareemdev2/blog-back-fpm:prod-83
- kareemdev2/blog-back-nginx:prod-83
- kareemdev2/blog-back-node:prod-83
```

Ce bloc vient des manifests Git.

Il sert à comparer :

```text
images déclarées dans Git
vs
images présentes localement sur le node
```

---

## 9. Images applicatives présentes sur le node

Exemple avant nettoyage :

```text
===== Images applicatives présentes sur le node =====
- docker.io/kareemdev2/blog-back-fpm:latest (307.3 MiB)
- docker.io/kareemdev2/blog-back-fpm:prod-83 (307.3 MiB)
```

Cela signifie que ces images sont encore stockées dans le runtime containerd du worker ciblé.

---

## 10. Candidates nettoyage

Exemple :

```text
===== Candidates nettoyage =====
- docker.io/kareemdev2/blog-back-fpm:latest (307.3 MiB) -> old mutable tag latest
```

Interprétation :

| Élément | Signification |
|---|---|
| `latest` | Tag mutable, souvent à éviter en production. |
| `prod-83` | Tag applicatif versionné. |
| `candidate nettoyage` | Image que le script identifie comme potentiellement supprimable. |

Le script images ne supprime pas cette candidate.

---

## 11. Workflow recommandé avec le script images

## 11.1 Diagnostic avant migration

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint
```

Objectif :

```text
Voir quelles images sont présentes avant déplacement des pods.
```

---

## 11.2 Diagnostic après migration des pods

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint
```

Objectif :

```text
Vérifier si worker-2 garde encore des images applicatives après déplacement vers worker-1.
```

---

## 11.3 Test du mode execute images

```bash
python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint --execute
```

Objectif :

```text
Vérifier que le script images ne supprime toujours rien si le mode réel est désactivé.
```

---

## 11.4 Nettoyage réel ensuite avec runtime

Si le diagnostic montre des images inutiles, utiliser :

```bash
python3 scripts/cleanup-rke2-node-runtime.py --node rke2-worker-2-maint --execute --prune-images
```

---

## 12. Commandes complémentaires

Vérifier les pods encore sur worker-2 :

```bash
kubectl get pods -n lab-k8s -o wide | grep rke2-worker-2 || true
```

Vérifier uniquement les images app présentes via le wrapper runtime :

```bash
ssh rke2-worker-2-maint 'sudo -n /usr/local/sbin/rke2-runtime-maintenance images | grep -E "kareemdev2/blog-back|IMAGE"'
```

Vérifier le disque :

```bash
ssh rke2-worker-2-maint 'sudo -n /usr/local/sbin/rke2-runtime-maintenance disk'
```

---

## 13. Résumé des appels possibles

| Commande | Effet |
|---|---|
| `python3 scripts/cleanup-rke2-node-images.py` | Diagnostic avec le nœud par défaut. |
| `python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint` | Diagnostic images sur worker-2. |
| `python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-1-maint` | Diagnostic images sur worker-1. |
| `python3 scripts/cleanup-rke2-node-images.py --node rke2-worker-2-maint --execute` | Mode execute demandé, mais nettoyage réel désactivé dans ce script. |
| `python3 scripts/cleanup-rke2-node-images.py --help` | Affiche l’aide du script. |

---

## 14. Conclusion

Le script images sert à décider si un nettoyage est nécessaire.

Il ne doit pas être utilisé comme outil principal de suppression.

Le nettoyage réel se fait ensuite avec :

```bash
scripts/cleanup-rke2-node-runtime.py
```

Le rôle du technicien est donc :

```text
1. diagnostiquer avec cleanup-rke2-node-images.py ;
2. interpréter les candidates ;
3. vérifier que les pods ne tournent plus sur le nœud ;
4. nettoyer avec cleanup-rke2-node-runtime.py si nécessaire.
```
