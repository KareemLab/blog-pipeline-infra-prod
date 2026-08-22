#!/usr/bin/env python3
"""
Bootstrap DNS cluster pour les NetworkPolicies GitOps.

Rôle :
- détecter l'IP DNS réellement vue par les pods ;
- vérifier le Service kube-system correspondant ;
- mettre à jour les cidr DNS dans les NetworkPolicies nginx/FPM si --write est utilisé ;
- afficher les commandes grep et dry-run à exécuter ensuite.

Par défaut, le script ne modifie aucun fichier.
"""

from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import time


TARGET_FILES = [
    Path("apps/blog-preprod/16-blog-back-nginx-networkpolicy.yaml"),
    Path("apps/blog-preprod/17-blog-back-fpm-networkpolicy.yaml"),
    Path("manifests/16-blog-back-nginx-networkpolicy.yaml"),
    Path("manifests/17-blog-back-fpm-networkpolicy.yaml"),
]


def run(cmd):
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        print("ERROR: commande échouée", file=sys.stderr)
        print(" ".join(cmd), file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)

    return result.stdout.strip()


def detect_dns_ip(kubectl, namespace, node_name):
    pod_name = "dns-bootstrap-detect"

    # Nettoyage préventif si un ancien pod temporaire existe encore.
    subprocess.run(
        [
            kubectl,
            "-n",
            namespace,
            "delete",
            "pod",
            pod_name,
            "--ignore-not-found=true",
            "--grace-period=0",
            "--force",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    output = ""
    phase = ""

    try:
        # Création d'un pod temporaire non interactif.
        # Il est forcé sur un worker sain pour éviter rke2-master-1.
        run([
            kubectl,
            "-n",
            namespace,
            "run",
            pod_name,
            "--restart=Never",
            "--image=busybox:1.36",
            "--overrides",
            json.dumps({"spec": {"nodeName": node_name}}),
            "--command",
            "--",
            "sh",
            "-c",
            "cat /etc/resolv.conf",
        ])

        # Attente de la fin du pod.
        # On évite kubectl wait interactif et on lit directement la phase du pod.
        for _ in range(60):
            phase = run([
                kubectl,
                "-n",
                namespace,
                "get",
                "pod",
                pod_name,
                "-o",
                "jsonpath={.status.phase}",
            ])

            if phase in ("Succeeded", "Failed"):
                break

            time.sleep(1)

        if phase not in ("Succeeded", "Failed"):
            describe = run([
                kubectl,
                "-n",
                namespace,
                "describe",
                "pod",
                pod_name,
            ])
            print("ERROR: timeout en attendant la fin du pod temporaire", file=sys.stderr)
            print(describe, file=sys.stderr)
            sys.exit(1)

        # Lecture des logs du pod, qui contiennent /etc/resolv.conf.
        output = run([
            kubectl,
            "-n",
            namespace,
            "logs",
            pod_name,
        ])

        if phase != "Succeeded":
            print(f"ERROR: pod temporaire terminé en phase {phase}", file=sys.stderr)
            print(output, file=sys.stderr)
            sys.exit(1)

    finally:
        # Nettoyage du pod temporaire, même en cas d'erreur.
        subprocess.run(
            [
                kubectl,
                "-n",
                namespace,
                "delete",
                "pod",
                pod_name,
                "--ignore-not-found=true",
                "--grace-period=0",
                "--force",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    match = re.search(r"^nameserver\s+(\d+\.\d+\.\d+\.\d+)", output, re.MULTILINE)

    if not match:
        print(f"ERROR: IP DNS introuvable dans les logs: {output!r}", file=sys.stderr)
        sys.exit(1)

    return match.group(1)


def find_matching_dns_service(kubectl, dns_ip):
    output = run([
        kubectl,
        "-n",
        "kube-system",
        "get",
        "svc",
        "-o",
        "json",
    ])

    data = json.loads(output)
    matches = []

    for item in data.get("items", []):
        spec = item.get("spec", {})
        if spec.get("clusterIP") == dns_ip:
            matches.append(item)

    return matches


def update_dns_cidr_in_file(path, dns_ip, write):
    if not path.exists():
        print(f"ERROR: fichier absent: {path}", file=sys.stderr)
        sys.exit(1)

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    changed = False
    replacements = []

    for i, line in enumerate(lines):
        if not re.search(r"^\s*cidr:\s*\d+\.\d+\.\d+\.\d+/32\s*$", line):
            continue

        nearby_block = "".join(lines[i:i + 10])

        is_dns_block = (
            "port: 53" in nearby_block
            and (
                "protocol: UDP" in nearby_block
                or "protocol: TCP" in nearby_block
            )
        )

        if not is_dns_block:
            continue

        old_line = line.rstrip("\n")
        new_line = re.sub(
            r"cidr:\s*\d+\.\d+\.\d+\.\d+/32",
            f"cidr: {dns_ip}/32",
            line,
        )
        new_line_display = new_line.rstrip("\n")

        if new_line != line:
            lines[i] = new_line
            changed = True
            replacements.append((old_line, new_line_display))
        else:
            replacements.append((old_line, new_line_display))

    if write and changed:
        path.write_text("".join(lines), encoding="utf-8")

    return changed, replacements


def print_service_summary(matches):
    if not matches:
        print("WARNING: aucun Service kube-system ne correspond à cette IP DNS")
        return

    print()
    print("Service Kubernetes correspondant :")
    for item in matches:
        meta = item["metadata"]
        spec = item["spec"]
        ports = spec.get("ports", [])

        print(f"- {meta['namespace']}/{meta['name']}")
        print(f"  ClusterIP: {spec.get('clusterIP')}")
        print("  Ports:")
        for port in ports:
            print(
                f"    - protocol={port.get('protocol')} "
                f"port={port.get('port')} "
                f"targetPort={port.get('targetPort')}"
            )


def print_next_commands(dns_ip):
    files = " \\\n  ".join(str(path) for path in TARGET_FILES)

    print()
    print("Commandes de vérification à lancer ensuite :")
    print()
    print("1) Vérifier les lignes DNS :")
    print(f'grep -R "{dns_ip}/32\\|port: 53\\|protocol: UDP\\|protocol: TCP" -n \\')
    print(f"  {files}")
    print()
    print("2) Dry-run server :")
    print("k apply --dry-run=server -f \\")
    print(f"  {files}")
    print()
    print("3) Vérifier le diff Git :")
    print("git diff -- \\")
    print(f"  {files}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kubectl",
        default="kubectl",
        help="Commande kubectl à utiliser. Par défaut: kubectl",
    )
    parser.add_argument(
        "--namespace",
        default="lab-k8s",
        help="Namespace utilisé pour le pod temporaire de détection DNS. Par défaut: lab-k8s",
    )
    parser.add_argument(
        "--node-name",
        default="rke2-worker-1",
        help="Node cible pour le pod temporaire de détection DNS. Par défaut: rke2-worker-1",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Modifie réellement les fichiers YAML GitOps.",
    )
    args = parser.parse_args()

    print("Détection DNS depuis un pod temporaire...")
    dns_ip = detect_dns_ip(args.kubectl, args.namespace, args.node_name)
    print(f"CLUSTER_DNS_IP={dns_ip}")

    matches = find_matching_dns_service(args.kubectl, dns_ip)
    print_service_summary(matches)

    print()
    print("Analyse des fichiers NetworkPolicy :")

    any_changed = False

    for path in TARGET_FILES:
        changed, replacements = update_dns_cidr_in_file(path, dns_ip, args.write)

        status = "MODIFIÉ" if changed and args.write else "OK"
        if changed and not args.write:
            status = "À MODIFIER avec --write"

        print(f"- {path}: {status}")

        for old, new in replacements:
            if old == new:
                print(f"  {old}")
            else:
                print(f"  avant: {old}")
                print(f"  après: {new}")

        any_changed = any_changed or changed

    if not args.write:
        print()
        print("Mode lecture seule : aucun fichier n'a été modifié.")
        print("Pour modifier les YAML si nécessaire :")
        print(f"  {sys.argv[0]} --write")

    elif not any_changed:
        print()
        print("Aucune modification nécessaire : les fichiers contiennent déjà la bonne IP DNS.")

    print_next_commands(dns_ip)


if __name__ == "__main__":
    main()
