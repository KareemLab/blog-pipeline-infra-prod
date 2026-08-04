# Diagnostic DNS cluster avec Job de maintenance

## Objectif

Cette procédure explique comment utiliser le Job de maintenance DNS pour diagnostiquer rapidement si le cluster Kubernetes peut créer un pod temporaire, lui attribuer un réseau Pod, et lui permettre de voir le DNS Kubernetes.

Ce diagnostic est utile après :

* un reboot des VM ;
* une recréation de cluster ;
* un incident réseau ;
* un problème de pod bloqué en `ContainerCreating` ;
* une erreur applicative du type `host not found`;
* un doute sur Calico, Canal ou CoreDNS.

## Fichier concerné

Le template du Job est stocké ici :

```text
maintenance/30-cluster-dns-diagnostic-job-template.yaml
```

Ce fichier est un outil de maintenance. Il ne fait pas partie du déploiement applicatif principal.

## Rôle du Job

Le Job sert à vérifier :

```text
1. que Kubernetes peut créer un pod temporaire ;
2. que le pod peut démarrer dans le namespace lab-k8s ;
3. que le pod est lancé sur un worker sain : rke2-worker-1 ;
4. que le pod reçoit une IP Pod ;
5. que le pod peut lire /etc/resolv.conf ;
6. que le DNS Kubernetes est visible depuis le pod.
```

Le Job ne modifie aucune ressource applicative.

Il ne modifie pas :

```text
les NetworkPolicies
les Deployments
les Services
les Ingress
les PVC
les Secrets
le cluster DNS
```

Il affiche uniquement un diagnostic dans les logs.

## Pourquoi le Job est suspendu

Dans le template Git, le Job contient :

```yaml
spec:
  suspend: true
```

Cela signifie que le Job est prêt, mais qu’il ne s’exécute pas automatiquement.

Il est volontairement suspendu pour éviter qu’un pod de diagnostic soit lancé sans action humaine.

## Pourquoi le Job cible rke2-worker-1

Les tests ont montré que les pods temporaires ne doivent pas être schedulés sur `rke2-master-1`.

Lors de tests précédents, des pods temporaires créés sur le master sont restés en `ContainerCreating` à cause d’une erreur CNI/Calico :

```text
plugin type="calico" failed (add): error getting ClusterInformation: connection is unauthorized: Unauthorized
```

En forçant le pod sur `rke2-worker-1`, le diagnostic DNS fonctionne correctement.

Le template contient donc :

```yaml
nodeName: rke2-worker-1
```

## Différence entre BusyBox, Calico et Canal

BusyBox est l’image Linux légère utilisée dans le pod de diagnostic.

Elle sert à exécuter des commandes simples comme :

```bash
cat /etc/resolv.conf
awk '/^nameserver / {print $2; exit}' /etc/resolv.conf
```

Calico est le composant réseau qui permet de créer le réseau du pod, de lui attribuer une IP et d’appliquer les NetworkPolicies.

Canal est le bundle réseau RKE2 qui inclut Calico et Flannel.

Résumé :

```text
BusyBox = l’image de test dans le pod
Calico  = le composant réseau / NetworkPolicy
Canal   = le bundle réseau RKE2 incluant Calico + Flannel
```

## Validation du template en dry-run

Avant toute exécution réelle, valider le manifest avec un dry-run serveur :

```bash
cd /home/masterdevops/rke2-lab

k apply --dry-run=server -f maintenance/30-cluster-dns-diagnostic-job-template.yaml
```

Résultat attendu :

```text
job.batch/cluster-dns-diagnostic created (server dry run)
```

Cette commande ne crée pas réellement le Job. Elle vérifie seulement que Kubernetes accepterait le manifest.

## Exécution réelle sous forme de copie temporaire

Ne pas désuspendre directement le template original.

Pour tester le Job, créer une copie temporaire non suspendue :

```bash
cd /home/masterdevops/rke2-lab

k -n lab-k8s delete job cluster-dns-diagnostic-test --ignore-not-found=true

sed \
  -e 's/cluster-dns-diagnostic/cluster-dns-diagnostic-test/g' \
  -e 's/suspend: true/suspend: false/g' \
  maintenance/30-cluster-dns-diagnostic-job-template.yaml \
  | k apply -f -
```

Cette commande crée un Job temporaire nommé :

```text
cluster-dns-diagnostic-test
```

Le template Git reste inchangé.

## Attendre la fin du Job

```bash
k -n lab-k8s wait job/cluster-dns-diagnostic-test \
  --for=condition=complete \
  --timeout=60s
```

## Voir le pod créé par le Job

```bash
k -n lab-k8s get pods \
  -l app.kubernetes.io/name=cluster-dns-diagnostic-test \
  -o wide
```

Résultat attendu :

```text
cluster-dns-diagnostic-test-xxxxx   Completed   ...   rke2-worker-1
```

Le point important est :

```text
STATUS = Completed
NODE   = rke2-worker-1
```

## Lire les logs du Job

```bash
k -n lab-k8s logs job/cluster-dns-diagnostic-test
```

Résultat attendu :

```text
===== /etc/resolv.conf =====
search lab-k8s.svc.cluster.local svc.cluster.local cluster.local lan
nameserver 10.43.0.10
options ndots:5

===== nameserver =====
10.43.0.10
```

## Interprétation du résultat

La ligne importante est :

```text
nameserver 10.43.0.10
```

Elle confirme que le pod voit le DNS Kubernetes du cluster.

Dans le cluster actuel, cette IP correspond au Service :

```text
kube-system/rke2-coredns-rke2-coredns
ClusterIP: 10.43.0.10
Ports: 53/UDP, 53/TCP
```

La ligne suivante :

```text
options ndots:5
```

n’est pas une IP et ne doit pas être utilisée dans les NetworkPolicies.

Elle indique simplement comment le resolver DNS du pod complète les noms courts avec les suffixes Kubernetes.

## Nettoyer le Job de test

Après lecture des logs, supprimer le Job temporaire :

```bash
k -n lab-k8s delete job cluster-dns-diagnostic-test --ignore-not-found=true
```

Vérifier qu’il ne reste plus de pod de test :

```bash
k -n lab-k8s get pods \
  -l app.kubernetes.io/name=cluster-dns-diagnostic-test
```

Résultat attendu :

```text
No resources found in lab-k8s namespace.
```

ou aucune ressource restante.

## Validation réalisée

Le Job de maintenance DNS a été testé avec une copie temporaire non suspendue.

Résultat observé :

```text
Pod créé : cluster-dns-diagnostic-test-gp2j9
Status : Completed
Node : rke2-worker-1
IP Pod : 10.42.1.38
```

Logs observés :

```text
===== /etc/resolv.conf =====
search lab-k8s.svc.cluster.local svc.cluster.local cluster.local lan
nameserver 10.43.0.10
options ndots:5

===== nameserver =====
10.43.0.10
```

Le Job temporaire a ensuite été supprimé.

## Conclusion

Le Job de maintenance DNS permet de vérifier rapidement que le cluster est capable de créer un pod temporaire sur un worker sain et que ce pod voit correctement le DNS Kubernetes.

Ce Job est un outil de diagnostic et de maintenance. Il ne remplace pas le script de bootstrap GitOps et ne modifie aucune ressource applicative.
