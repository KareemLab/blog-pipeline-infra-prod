# Runbook automatisé — Réparation CNI Canal/Calico RKE2 sur un node

## 1. Objectif

Ce runbook documente le script d’administration :

```text
scripts/maintenance/repair-canal-node.py
```

Ce script permet de diagnostiquer et de réparer de manière contrôlée un incident CNI Canal/Calico sur un node RKE2.

Il ne remplace pas le runbook manuel déjà créé :

```text
incident-cni-canal-rke2-worker-node
```

Le runbook manuel reste la procédure détaillée pas à pas.  
Ce nouveau document décrit la version automatisée utilisée par l’administrateur `masterdevops`.

Objectif principal :

```text
Transformer une procédure manuelle sensible en procédure administrative contrôlée.
```

---

## 2. Contexte

Un incident CNI Canal/Calico peut provoquer des symptômes applicatifs alors que Kubernetes, Argo CD et les pods existants semblent corrects.

Cas déjà rencontré :

```text
- application Symfony en erreur 500 ;
- pods existants en Running ;
- nouveaux pods bloqués en ContainerCreating ;
- Service ClusterIP PostgreSQL en timeout ;
- endpoint direct PostgreSQL fonctionnel ;
- headless service PostgreSQL fonctionnel ;
- Argo CD Synced/Healthy ;
- manifests GitOps non modifiés.
```

Erreur typique observée lors de l’incident Canal/Calico :

```text
Failed to create pod sandbox:
plugin type="calico" failed (add):
error getting ClusterInformation: connection is unauthorized: Unauthorized
```

Autre erreur possible :

```text
failed to destroy network for sandbox:
plugin type="calico" failed (delete):
error getting ClusterInformation: connection is unauthorized: Unauthorized
```

Interprétation :

```text
Le composant CNI/Calico du node ne fonctionne plus correctement.
Le kubelet ne peut plus créer ou supprimer proprement le réseau des pods.
```

La correction peut nécessiter :

```text
1. suppression ciblée du pod rke2-canal du node concerné ;
2. recréation automatique par le DaemonSet rke2-canal ;
3. si nécessaire, redémarrage du service RKE2 du node.
```

---

## 3. Diagnostic différentiel — ImagePullBackOff vs Canal/CNI

Pendant les tests, un cas important a été observé : un nouveau pod applicatif peut afficher des erreurs `Failed`, `ErrImagePull` ou `ImagePullBackOff` sans que Canal/Calico soit en panne.

Cette distinction est essentielle.

Il ne faut pas réparer Canal automatiquement dès qu’un pod affiche `Failed`.

### 3.1 Cas observé pendant le test

Le déploiement FPM utilisait :

```text
image: kareemdev2/blog-back-fpm:prod-83
imagePullPolicy: Always
```

Lors de la recréation du pod FPM, le pod est passé temporairement par les états suivants :

```text
ContainerCreating
ImagePullBackOff
ErrImagePull
Running
```

Events observés sur le pod :

```text
Failed to pull image "kareemdev2/blog-back-fpm:prod-83":
failed to pull and unpack image "docker.io/kareemdev2/blog-back-fpm:prod-83":
failed to resolve reference "docker.io/kareemdev2/blog-back-fpm:prod-83":
unexpected status from HEAD request to https://registry-1.docker.io/v2/kareemdev2/blog-back-fpm/manifests/prod-83:
500 Internal Server Error
```

Puis Kubernetes a retenté automatiquement :

```text
Successfully pulled image
Created container fpm
Started container fpm
```

L’application est revenue en état normal :

```text
HTTP/1.1 200 OK
```

### 3.2 Interprétation

Dans ce cas précis, le problème ne venait pas de Canal/Calico.

La cause probable était :

```text
Docker Hub / registry temporairement indisponible
ou erreur temporaire pendant le pull de l’image
```

Le réseau CNI fonctionnait, car :

```text
- le pod a fini par obtenir une IP ;
- le conteneur a été créé ;
- le conteneur a démarré ;
- l’application est revenue en HTTP 200.
```

### 3.3 Différence avec une vraie panne Canal/CNI

Une vraie panne Canal/CNI est plutôt identifiée par des messages comme :

```text
Failed to create pod sandbox
plugin type="calico" failed
error getting ClusterInformation
connection is unauthorized
failed to destroy network for sandbox
```

Dans ce cas, le problème concerne la création ou la suppression du réseau du pod.

### 3.4 Règle de décision

```text
ErrImagePull / ImagePullBackOff / failed to pull image
→ vérifier d’abord le registry, le tag image, Docker Hub et imagePullPolicy
→ ne pas réparer Canal en premier

FailedCreatePodSandBox / plugin type="calico" / ClusterInformation unauthorized
→ suspecter Canal/CNI
→ utiliser repair-canal sur le node concerné
```

Cette distinction évite de redémarrer Canal alors que le vrai problème vient simplement du pull d’image.

---

## 4. Pourquoi un script automatisé ?

La procédure manuelle fonctionne, mais elle demande plusieurs commandes sensibles.

Exemples :

```text
- identifier le bon pod rke2-canal ;
- vérifier le node associé ;
- supprimer uniquement le pod Canal du node malade ;
- attendre la recréation du DaemonSet ;
- éventuellement redémarrer rke2-agent ou rke2-server ;
- vérifier l’état du node et des pods applicatifs.
```

Le script réduit le risque d’erreur.

Il permet de :

```text
- cibler un node précis ;
- détecter automatiquement worker ou master ;
- choisir automatiquement rke2-agent ou rke2-server ;
- fonctionner en simulation par défaut ;
- exiger --execute pour toute action réelle ;
- protéger les masters avec --allow-control-plane ;
- supprimer uniquement le pod Canal du node ciblé ;
- éviter les suppressions larges.
```

---

## 5. Fichier concerné

Script :

```text
scripts/maintenance/repair-canal-node.py
```

Type :

```text
script Python d’administration
```

Utilisateur prévu :

```text
masterdevops
```

Ce script est créé pour l’administrateur.

Il n’est pas encore destiné au futur profil `maintenance-monitoring`.

Le futur profil `maintenance-monitoring` sera limité à certains workers applicatifs, mais cette étape sera traitée séparément.

---

## 6. Pré requis

Être connecté au bastion Linux avec l’utilisateur admin :

```text
masterdevops
```

Se placer dans le dépôt GitOps :

```bash
cd /home/masterdevops/rke2-lab
```

Définir le kubeconfig admin :

```bash
export KUBECONFIG=/home/masterdevops/.kube/config.yaml
```

Vérifier le contexte Kubernetes :

```bash
kubectl config current-context
kubectl get nodes
```

Le script utilise :

```text
- kubectl ;
- ssh pour le redémarrage distant du service RKE2 ;
- sudo sur les nodes pour redémarrer rke2-agent ou rke2-server.
```

---

## 7. Nodes concernés

Le script est générique.

Il peut diagnostiquer et réparer Canal sur :

```text
rke2-master-1
rke2-worker-1
rke2-worker-2
```

Le script détecte automatiquement si le node est :

```text
- worker ;
- control-plane/master.
```

Service RKE2 associé :

```text
worker                → rke2-agent
control-plane/master  → rke2-server
```

---

## 8. Sécurité intégrée

### 8.1 Simulation par défaut

Par défaut, le script ne modifie rien.

Sans option `--execute`, il affiche uniquement ce qu’il ferait.

Exemple :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2
```

Résultat attendu :

```text
MODE=SIMULATION
AUCUNE_MODIFICATION_EFFECTUEE
```

### 8.2 Action réelle uniquement avec --execute

Pour appliquer réellement une action, il faut ajouter :

```text
--execute
```

Exemple :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2 --execute
```

Sans cette option, aucune suppression de pod et aucun redémarrage de service RKE2 ne sont effectués.

### 8.3 Protection des masters

Un node control-plane/master est plus sensible.

Le script refuse certaines actions réelles sur master si l’option suivante n’est pas fournie :

```text
--allow-control-plane
```

Exemple refusé :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-master-1 --execute
```

Résultat attendu :

```text
ERROR: le node ciblé est un control-plane/master.
Pour autoriser explicitement cette action, ajouter: --allow-control-plane
```

Exemple autorisé explicitement :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-master-1 --execute --allow-control-plane
```

---

## 9. Actions disponibles

Afficher l’aide :

```bash
./scripts/maintenance/repair-canal-node.py --help
```

Actions disponibles :

```text
list-nodes
status
diagnose
repair-canal
restart-rke2
full-repair
```

---

## 10. Action list-nodes

Commande :

```bash
./scripts/maintenance/repair-canal-node.py list-nodes
```

Objectif :

```text
- afficher les nodes du cluster ;
- afficher les rôles ;
- afficher les labels ;
- vérifier les noms exacts à utiliser avec --node.
```

Exemples de nodes :

```text
rke2-master-1
rke2-worker-1
rke2-worker-2
```

---

## 11. Action status

Commande :

```bash
./scripts/maintenance/repair-canal-node.py status --node rke2-worker-2
```

Objectif :

```text
- vérifier le rôle du node ;
- afficher le service RKE2 associé ;
- afficher le DaemonSet rke2-canal ;
- identifier le pod Canal présent sur le node ;
- afficher son statut ;
- afficher les pods applicatifs.
```

Exemple de sortie attendue pour un worker :

```text
NODE=rke2-worker-2
NODE_ROLE=worker
RKE2_SERVICE=rke2-agent
CANAL_POD=rke2-canal-bx7wq
CANAL_STATUS=Running
CANAL_READY=2/2
```

Exemple pour un master :

```text
NODE=rke2-master-1
NODE_ROLE=control-plane/master
RKE2_SERVICE=rke2-server
```

Cette commande ne modifie rien.

---

## 12. Action diagnose

Commande :

```bash
./scripts/maintenance/repair-canal-node.py diagnose --node rke2-worker-2
```

Objectif :

```text
- exécuter le status ;
- afficher les events du pod Canal du node ciblé ;
- rechercher des pods bloqués ;
- classer le diagnostic probable.
```

Le script recherche notamment :

```text
ContainerCreating
CrashLoopBackOff
ImagePullBackOff
ErrImagePull
Failed
Error
```

Classification possible :

```text
DIAGNOSTIC_PROBABLE=CANAL_CNI
DIAGNOSTIC_PROBABLE=REGISTRY_OR_IMAGE_PULL
DIAGNOSTIC_PROBABLE=POD_ERROR_OTHER
DIAGNOSTIC_PROBABLE=NONE
```

### 12.1 Diagnostic Canal/CNI

Si le script détecte :

```text
FailedCreatePodSandBox
plugin type="calico"
ClusterInformation
CNI
failed to create pod sandbox
```

Il affiche :

```text
DIAGNOSTIC_PROBABLE=CANAL_CNI
RECOMMANDATION=utiliser repair-canal sur le node concerné, puis restart-rke2 seulement si nécessaire
```

### 12.2 Diagnostic image / registry

Si le script détecte :

```text
ImagePullBackOff
ErrImagePull
failed to pull image
back-off pulling image
```

Il affiche :

```text
DIAGNOSTIC_PROBABLE=REGISTRY_OR_IMAGE_PULL
RECOMMANDATION=ne pas réparer Canal en premier ; vérifier registry, tag image, disponibilité Docker Hub et imagePullPolicy
```

### 12.3 Diagnostic sain

Si aucun pod bloqué n’est détecté :

```text
AUCUN_POD_BLOQUE_DETECTE=OK
DIAGNOSTIC_PROBABLE=NONE
RECOMMANDATION=aucune réparation Canal nécessaire actuellement
```

---

## 13. Action repair-canal

Commande de simulation :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2
```

Objectif :

```text
- identifier le pod rke2-canal du node ciblé ;
- afficher la commande qui serait exécutée ;
- ne rien modifier sans --execute.
```

Commande réelle sur worker :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2 --execute
```

Action réelle effectuée :

```text
kubectl -n kube-system delete pod <pod-rke2-canal-du-node>
kubectl -n kube-system rollout status ds/rke2-canal --timeout=90s
```

Pourquoi supprimer le pod Canal ?

```text
rke2-canal est géré par un DaemonSet.
Quand le pod Canal d’un node est supprimé, Kubernetes le recrée automatiquement sur ce même node.
```

Le script ne supprime pas le DaemonSet.

Le script ne supprime pas tous les pods Canal.

Il supprime uniquement le pod Canal du node ciblé.

### 13.1 Exemple réel validé sur worker-2

Avant action :

```text
rke2-canal-pnwzk   2/2 Running   rke2-worker-2
```

Commande exécutée :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2 --execute
```

Action observée :

```text
pod "rke2-canal-pnwzk" deleted
daemon set "rke2-canal" successfully rolled out
```

Après action :

```text
NEW_CANAL_POD=rke2-canal-bx7wq
NEW_CANAL_STATUS=Running
NEW_CANAL_READY=2/2
NEW_CANAL_RESTARTS=0
```

Conclusion :

```text
La suppression ciblée du pod Canal du worker-2 a fonctionné.
Le DaemonSet a recréé un nouveau pod Canal.
Le node est resté opérationnel.
```

---

## 14. Action restart-rke2

Commande de simulation :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-worker-2
```

Commande réelle sur worker :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-worker-2 --execute
```

Action effectuée sur un worker :

```text
ssh -t rke2-worker-2-maint 'sudo systemctl restart rke2-agent'
```

Action effectuée sur un master :

```text
ssh -t rke2-master-1 'sudo systemctl restart rke2-server'
```

Pour un master, il faut ajouter :

```text
--allow-control-plane
```

Exemple :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-master-1 --execute --allow-control-plane
```

---

## 15. Action full-repair

La commande `full-repair` enchaîne les étapes.

Par défaut, elle exécute la partie Canal et ignore le restart RKE2.

Simulation :

```bash
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2
```

Résultat :

```text
1. simulation ou exécution repair-canal selon présence de --execute ;
2. restart RKE2 ignoré.
```

Pour inclure aussi le redémarrage du service RKE2 :

```bash
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2 --include-rke2-restart
```

Pour exécuter réellement sur worker :

```bash
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2 --include-rke2-restart --execute
```

Pour exécuter réellement sur master :

```bash
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-master-1 --include-rke2-restart --execute --allow-control-plane
```

---

## 16. Mapping SSH

Le script utilise un mapping SSH pour les workers :

```text
rke2-worker-1 → rke2-worker-1-maint
rke2-worker-2 → rke2-worker-2-maint
```

Ces alias sont définis dans :

```text
/home/masterdevops/.ssh/config
```

Pour le master, le script utilise par défaut :

```text
rke2-master-1
```

Il est possible de forcer la cible SSH avec :

```text
--ssh-target
```

Exemple :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-master-1 --ssh-target rke2-master-1-maint
```

---

## 17. Exemples d’utilisation recommandée

### 17.1 Diagnostic simple

```bash
export KUBECONFIG=/home/masterdevops/.kube/config.yaml
cd /home/masterdevops/rke2-lab

./scripts/maintenance/repair-canal-node.py status --node rke2-worker-2
./scripts/maintenance/repair-canal-node.py diagnose --node rke2-worker-2
```

### 17.2 Réparation Canal uniquement

Simulation :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2
```

Exécution réelle :

```bash
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2 --execute
```

### 17.3 Redémarrage RKE2 du worker

Simulation :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-worker-2
```

Exécution réelle :

```bash
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-worker-2 --execute
```

### 17.4 Réparation complète worker

Simulation :

```bash
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2 --include-rke2-restart
```

Exécution réelle :

```bash
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2 --include-rke2-restart --execute
```

---

## 18. Ce que le script ne fait pas

Le script ne fait pas :

```text
- suppression de DaemonSet ;
- suppression large dans kube-system ;
- modification de Secret ;
- modification de ConfigMap ;
- restauration PostgreSQL ;
- suppression de PVC ;
- cleanup d’images ;
- cleanup runtime ;
- rm -rf ;
- crictl rmi ;
- ctr images rm ;
- patch Argo CD ;
- modification Git.
```

Les scripts de cleanup RKE2 sont séparés :

```text
scripts/cleanup-rke2-node-images.py
scripts/cleanup-rke2-node-runtime.py
```

La restauration PostgreSQL doit rester une procédure séparée et contrôlée.

---

## 19. Différence entre runbook manuel et script

Runbook manuel :

```text
incident-cni-canal-rke2-worker-node
→ explique l’incident
→ détaille les symptômes
→ décrit les commandes manuelles
→ sert de documentation pédagogique et de secours
```

Script automatisé :

```text
scripts/maintenance/repair-canal-node.py
→ applique une procédure encadrée
→ limite les erreurs de ciblage
→ sécurise les actions sensibles
→ fonctionne en simulation par défaut
```

Les deux sont complémentaires.

Le runbook manuel explique.

Le script automatise.

---

## 20. Procédure de validation réalisée

Le script a été testé en simulation et avec une action réelle limitée.

Tests sans action réelle :

```text
python3 -m py_compile scripts/maintenance/repair-canal-node.py
./scripts/maintenance/repair-canal-node.py --help
./scripts/maintenance/repair-canal-node.py list-nodes
./scripts/maintenance/repair-canal-node.py status --node rke2-worker-2
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-worker-2
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-worker-2
./scripts/maintenance/repair-canal-node.py status --node rke2-master-1
./scripts/maintenance/repair-canal-node.py repair-canal --node rke2-master-1
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-master-1
./scripts/maintenance/repair-canal-node.py restart-rke2 --node rke2-master-1 --allow-control-plane
./scripts/maintenance/repair-canal-node.py diagnose --node rke2-worker-2
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2
./scripts/maintenance/repair-canal-node.py full-repair --node rke2-worker-2 --include-rke2-restart
```

Sécurité master validée :

```text
repair-canal --node rke2-master-1 --execute
→ refusé sans --allow-control-plane

restart-rke2 --node rke2-master-1
→ refusé sans --allow-control-plane
```

Action réelle validée sur worker-2 :

```text
repair-canal --node rke2-worker-2 --execute
→ suppression ciblée du pod Canal
→ recréation automatique par DaemonSet
→ nouveau pod Canal Running 2/2
```

---

## 21. Résultat attendu après réparation

Après une réparation Canal ou un redémarrage RKE2, vérifier :

```bash
kubectl get nodes -o wide
kubectl -n kube-system get pods -o wide | grep rke2-canal
kubectl -n lab-k8s get pods -o wide
```

Résultats attendus :

```text
node ciblé : Ready
pod rke2-canal du node : 2/2 Running
pods applicatifs : Running
application : répond normalement
```

Test applicatif final :

```text
http://blog.k8s.test/articles
```

Résultat attendu :

```text
HTTP/1.1 200 OK
```

---

## 22. Notes pour la future Partie maintenance-monitoring

Ce script est actuellement prévu pour l’administrateur `masterdevops`.

Pour un futur profil `maintenance-monitoring`, il faudra réduire le périmètre.

Principe futur :

```text
maintenance-monitoring
→ workers applicatifs uniquement
→ pas de master
→ pas de kube-system libre
→ pas de cluster-admin
→ procédures contrôlées seulement
```

Exemple de limitation future :

```text
workload-role=app
```

Dans l’état actuel du cluster, le worker applicatif identifié est :

```text
rke2-worker-1
```

Cette restriction sera traitée dans une étape séparée.

---

## 23. Conclusion

Le script `repair-canal-node.py` transforme une procédure manuelle Canal/Calico sensible en procédure administrative contrôlée.

Il permet de traiter un incident Canal/Calico récurrent sans supprimer de ressources larges et sans modifier les manifests GitOps.

La logique est sécurisée :

```text
simulation par défaut
--execute obligatoire
--allow-control-plane obligatoire pour les masters
suppression ciblée du pod Canal uniquement
restart RKE2 explicite uniquement
diagnostic différentiel avant action
```

Le diagnostic différentiel est important :

```text
ImagePullBackOff / ErrImagePull
→ problème probable de registry ou de pull image
→ ne pas réparer Canal en premier

FailedCreatePodSandBox / plugin calico / ClusterInformation unauthorized
→ problème probable Canal/CNI
→ utiliser repair-canal sur le node concerné
```

Ce script complète le runbook manuel existant et prépare une future séparation entre :

```text
masterdevops
→ administration complète

technicien-monitoring
→ lecture seule

maintenance-monitoring
→ maintenance contrôlée sur périmètre restreint
```
