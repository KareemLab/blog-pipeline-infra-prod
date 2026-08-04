# Bootstrap DNS cluster pour NetworkPolicies

## Objectif

Cette procédure sert à identifier l'adresse IP DNS réellement utilisée par les pods Kubernetes, puis à vérifier que les NetworkPolicies applicatives autorisent bien les flux DNS nécessaires.

Elle est utile après une recréation de cluster ou une restauration d'environnement, car l'adresse IP du DNS Kubernetes peut changer selon le service CIDR du cluster.

## Pourquoi cette procédure est nécessaire

Les pods applicatifs utilisent le DNS Kubernetes pour résoudre les noms de services internes.

Exemples :

```text
blog-back-fpm
pg-lab-postgresql-primary
```

Si une NetworkPolicy bloque l'egress DNS, nginx ou FPM peuvent ne plus résoudre les services internes.

Erreur déjà rencontrée côté nginx :

```text
host not found in upstream "blog-back-fpm"
```

Dans ce cas, nginx ne pouvait pas résoudre le service `blog-back-fpm` au démarrage.

## Étape 1 — Lire le DNS vu par un pod

Depuis le bastion :

```bash
k run dns-check --rm -it --restart=Never \
  --image=busybox:1.36 \
  -- cat /etc/resolv.conf
```

La ligne importante est :

```text
nameserver X.X.X.X
```

Dans le cluster actuel, la valeur validée est :

```text
nameserver 10.43.0.10
```

Cela signifie que les pods envoient leurs requêtes DNS vers :

```text
10.43.0.10
```

## Étape 2 — Vérifier le Service Kubernetes correspondant

Remplacer `10.43.0.10` par l'adresse IP trouvée à l'étape précédente si elle est différente.

```bash
k -n kube-system get svc -o wide | grep "10.43.0.10"
```

Dans le cluster actuel, le service validé est :

```text
kube-system/rke2-coredns-rke2-coredns
ClusterIP: 10.43.0.10
Ports: 53/UDP, 53/TCP
```

## Étape 3 — Vérifier les NetworkPolicies applicatives

```bash
grep -R "10.43.0.10/32" -n \
  apps/blog-preprod/16-blog-back-nginx-networkpolicy.yaml \
  apps/blog-preprod/17-blog-back-fpm-networkpolicy.yaml \
  manifests/16-blog-back-nginx-networkpolicy.yaml \
  manifests/17-blog-back-fpm-networkpolicy.yaml
```

Les fichiers concernés sont :

```text
apps/blog-preprod/16-blog-back-nginx-networkpolicy.yaml
apps/blog-preprod/17-blog-back-fpm-networkpolicy.yaml
manifests/16-blog-back-nginx-networkpolicy.yaml
manifests/17-blog-back-fpm-networkpolicy.yaml
```

## Flux DNS attendu

Les pods nginx et FPM doivent pouvoir sortir vers le DNS Kubernetes :

```text
egress vers CLUSTER_DNS_IP/32
port UDP 53
port TCP 53
```

Dans le cluster actuel :

```text
CLUSTER_DNS_IP=10.43.0.10
```

Les NetworkPolicies doivent donc autoriser :

```text
10.43.0.10/32
UDP 53
TCP 53
```

## Si l'adresse IP DNS change

Ne pas modifier directement le cluster à la main.

Procédure attendue :

1. modifier les fichiers YAML avec Python ;
2. afficher les lignes importantes avec `grep` ;
3. lancer un `k apply --dry-run=server` ;
4. seulement ensuite proposer le `k apply` réel ;
5. vérifier les objets modifiés ;
6. garder `apps/blog-preprod/` et `manifests/` synchronisés.

## État validé actuellement

```text
DNS vu par les pods : 10.43.0.10
Service DNS correspondant : kube-system/rke2-coredns-rke2-coredns
Ports DNS : 53/UDP et 53/TCP
NetworkPolicies nginx/FPM : 10.43.0.10/32 présent
```

## Commandes de contrôle rapide

Lire le DNS vu par un pod :

```bash
k run dns-check --rm -it --restart=Never \
  --image=busybox:1.36 \
  -- cat /etc/resolv.conf
```

Vérifier le service DNS correspondant :

```bash
k -n kube-system get svc -o wide | grep "10.43.0.10"
```

Vérifier les NetworkPolicies :

```bash
grep -R "10.43.0.10/32" -n \
  apps/blog-preprod/16-blog-back-nginx-networkpolicy.yaml \
  apps/blog-preprod/17-blog-back-fpm-networkpolicy.yaml \
  manifests/16-blog-back-nginx-networkpolicy.yaml \
  manifests/17-blog-back-fpm-networkpolicy.yaml
```
