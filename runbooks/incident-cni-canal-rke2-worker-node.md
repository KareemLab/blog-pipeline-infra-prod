# Runbook incident — CNI Canal/Calico RKE2 sur un worker node

## 1. Objectif

Ce runbook décrit la procédure de diagnostic et de correction lorsqu’un node RKE2 présente un problème réseau CNI/Canal/Calico.

Cas rencontré :

```text
- l’application Symfony retourne 500 ;
- les pods existants sont Running ;
- les nouveaux pods restent bloqués en ContainerCreating ;
- le Service Kubernetes ClusterIP PostgreSQL timeout ;
- l’accès direct à l’endpoint PostgreSQL fonctionne ;
- le headless service PostgreSQL fonctionne ;
- Argo CD indique Synced/Healthy mais l’application ne répond pas correctement.
```

Le problème n’était pas :

```text
- un secret modifié ;
- une image applicative cassée ;
- une corruption confirmée de PostgreSQL ;
- un problème Argo CD ;
- un problème Grafana ;
- un problème de manifests Git.
```

Le problème était un incident réseau local au node `rke2-worker-2`, lié à Canal/Calico et au datapath Kubernetes Service.

---

## 2. Symptômes observés

### 2.1 Application en erreur 500

Depuis le navigateur :

```text
http://blog.k8s.test/articles
```

retournait :

```text
500 Internal Server Error
```

### 2.2 Pods applicatifs existants Running

Commande :

```bash
k get pods -n lab-k8s -o wide | grep -E 'NAME|blog-back|pg-lab-postgresql'
```

Exemple observé :

```text
blog-back-fpm       Running   rke2-worker-2
blog-back-nginx     Running   rke2-worker-2
postgresql-primary  Running   rke2-worker-1
```

### 2.3 FPM retourne 500

Logs Nginx applicatif :

```text
GET /articles HTTP/1.1" 500
```

Logs FPM :

```text
GET /index.php" 500
```

### 2.4 Connexion PostgreSQL via Service ClusterIP en timeout

Depuis le pod FPM :

```text
pg-lab-postgresql-primary -> 10.43.29.229 -> timeout
```

Mais l’endpoint direct PostgreSQL répondait :

```text
10.42.1.41:5432 -> OK
```

Et le headless service répondait :

```text
pg-lab-postgresql-primary-hl -> OK
```

Conclusion :

```text
PostgreSQL fonctionne.
DNS Kubernetes fonctionne.
Le pod PostgreSQL répond.
Mais le Service ClusterIP ne route plus correctement depuis le node applicatif.
```

---

## 3. Erreur critique identifiée

Lors du redémarrage de FPM, le nouveau pod est resté bloqué en `ContainerCreating`.

Commande :

```bash
k describe pod -n lab-k8s <pod-fpm-bloque> | sed -n '/Events:/,$p'
```

Erreur observée :

```text
Failed to create pod sandbox:
plugin type="calico" failed (add):
error getting ClusterInformation: connection is unauthorized: Unauthorized
```

Puis au nettoyage réseau :

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

---

## 4. Diagnostic rapide

### 4.1 Vérifier les pods applicatifs

```bash
k get pods -n lab-k8s -o wide | grep -E 'NAME|blog-back-fpm|blog-back-nginx|pg-lab-postgresql-primary'
```

### 4.2 Vérifier le pod CNI du node concerné

```bash
k get pods -n kube-system -o wide | grep -Ei 'rke2-canal|calico|canal|flannel'
```

Exemple :

```text
rke2-canal-ltlwt   2/2 Running   rke2-worker-2
```

### 4.3 Vérifier le DaemonSet Canal

```bash
k get ds -n kube-system | grep -Ei 'rke2-canal|calico|canal|flannel'
```

Exemple :

```text
rke2-canal   3   3   3   3
```

---

## 5. Correction niveau 1 — redémarrer Canal sur le worker concerné

Identifier le pod `rke2-canal` du node concerné :

```bash
k get pods -n kube-system -o wide | grep rke2-canal
```

Puis supprimer uniquement le pod Canal du worker malade.

Exemple pour `rke2-worker-2` :

```bash
k delete pod -n kube-system <pod-rke2-canal-worker-2>
```

Exemple réel :

```bash
k delete pod -n kube-system rke2-canal-ltlwt
```

Comme `rke2-canal` est un DaemonSet, Kubernetes recrée automatiquement un nouveau pod Canal sur ce node.

Attendre le rollout :

```bash
k rollout status ds -n kube-system rke2-canal --timeout=90s
```

Vérifier :

```bash
k get pods -n kube-system -o wide | grep -Ei 'rke2-canal|NAME'
```

Résultat attendu :

```text
rke2-canal-xxxxx   2/2 Running   rke2-worker-2
```

---

## 6. Vérifier les pods bloqués

Après redémarrage de Canal :

```bash
k get pods -n lab-k8s -l app.kubernetes.io/name=blog-back-fpm -o wide
```

Résultat attendu :

```text
un seul pod FPM actif en Running
```

Vérifier le rollout :

```bash
k rollout status deploy -n lab-k8s blog-back-fpm --timeout=60s
```

Résultat attendu :

```text
deployment "blog-back-fpm" successfully rolled out
```

---

## 7. Correction niveau 2 — redémarrer rke2-agent sur le worker concerné

Si l’application retourne toujours 500 après redémarrage de Canal, et si le Service ClusterIP PostgreSQL timeout encore depuis FPM, redémarrer `rke2-agent` sur le worker concerné.

Exemple pour `rke2-worker-2` :

```bash
ssh -t rke2-worker-2-maint '
hostname
sudo systemctl restart rke2-agent
echo "rke2-agent restart demandé"
'
```

Puis attendre environ 30 secondes.

Vérifier le node :

```bash
k get node rke2-worker-2
```

Vérifier les pods applicatifs :

```bash
k get pods -n lab-k8s -o wide | grep -E "NAME|blog-back-fpm|blog-back-nginx|pg-lab-postgresql-primary"
```

Vérifier Canal :

```bash
k get pods -n kube-system -o wide | grep -E "NAME|rke2-canal"
```

---

## 8. Test applicatif final

Depuis le navigateur :

```text
http://blog.k8s.test/articles
```

Résultat attendu :

```text
Symfony fonctionne de nouveau.
La page /articles répond normalement.
```

---

## 9. Ce qu’il ne faut pas faire trop vite

Ne pas commencer par :

```text
- modifier les secrets ;
- modifier DATABASE_URL ;
- restaurer PostgreSQL ;
- patcher Argo CD ;
- supprimer les PVC ;
- relancer plusieurs rollouts successifs ;
- supprimer l’ancien pod FPM Running tant qu’un nouveau pod n’est pas Ready.
```

Tant qu’un ancien pod applicatif est encore Running, il faut le préserver.

---

## 10. Résumé de l’incident

Cause probable :

```text
Canal/Calico sur rke2-worker-2 est entré dans un état incohérent.
Le node ne gérait plus correctement le réseau des pods et/ou le routage Service ClusterIP.
```

Symptôme clé :

```text
plugin type="calico" failed:
error getting ClusterInformation: connection is unauthorized
```

Effet applicatif :

```text
Symfony ne pouvait plus joindre PostgreSQL via le Service ClusterIP.
La route /articles retournait 500.
```

Réparation effectuée :

```text
1. Redémarrage du pod rke2-canal sur rke2-worker-2.
2. Redémarrage de rke2-agent sur rke2-worker-2.
```

Résultat :

```text
Le réseau du node a été réinitialisé.
Le Service PostgreSQL est redevenu accessible depuis FPM.
Symfony est revenu.
```

---

## 11. Commandes condensées d’urgence

Adapter le nom du pod Canal au node concerné.

```bash
# 1. Identifier Canal
k get pods -n kube-system -o wide | grep rke2-canal

# 2. Redémarrer Canal du worker malade
k delete pod -n kube-system <pod-rke2-canal-du-worker>

# 3. Attendre Canal
k rollout status ds -n kube-system rke2-canal --timeout=90s

# 4. Vérifier app
k get pods -n lab-k8s -o wide | grep -E 'NAME|blog-back-fpm|blog-back-nginx'

# 5. Si le 500 persiste, redémarrer rke2-agent du worker
ssh -t rke2-worker-2-maint '
sudo systemctl restart rke2-agent
echo "rke2-agent restart demandé"
'

# 6. Vérifier après 30 secondes
k get node rke2-worker-2
k get pods -n lab-k8s -o wide | grep -E 'NAME|blog-back-fpm|blog-back-nginx|pg-lab-postgresql-primary'
k get pods -n kube-system -o wide | grep rke2-canal
```

---

## 12. Notes production

En production, pour éviter qu’un incident CNI sur un seul node provoque une panne visible :

```text
- avoir plusieurs replicas FPM sur plusieurs workers ;
- avoir plusieurs replicas Nginx applicatifs sur plusieurs workers ;
- éviter que tous les workloads applicatifs dépendent d’un seul worker ;
- ajouter des alertes sur ContainerCreating prolongé ;
- ajouter des alertes sur erreurs Canal/Calico ;
- surveiller les erreurs HTTP 5xx applicatives ;
- documenter cette procédure comme runbook d’urgence.
```
