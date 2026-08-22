#!/usr/bin/env python3
import argparse
import shlex
import subprocess
import sys

WRAPPER = "/usr/local/sbin/rke2-runtime-maintenance"


def print_cmd(cmd):
    print("+ " + " ".join(shlex.quote(part) for part in cmd))


def run(cmd, check=False):
    print_cmd(cmd)
    result = subprocess.run(cmd)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def remote(node, action, check=False):
    return run(
        ["ssh", node, f"sudo -n {WRAPPER} {shlex.quote(action)}"],
        check=check,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostic et nettoyage prudent du runtime RKE2/containerd sur un node."
    )
    parser.add_argument(
        "--node",
        default="rke2-worker-2-maint",
        help="Alias SSH du node cible",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Nettoie les conteneurs Exited",
    )
    parser.add_argument(
        "--prune-images",
        action="store_true",
        help="Avec --execute, nettoie aussi les images/couches non utilisées",
    )
    args = parser.parse_args()

    print(f"Node cible : {args.node}")
    print(f"Wrapper    : sudo -n {WRAPPER}")
    print()

    print("===== Préflight SSH =====")
    run(["ssh", args.node, "whoami && hostname"], check=True)

    print()
    print("===== Etat disque =====")
    remote(args.node, "disk", check=True)

    print()
    print("===== Conteneurs Exited =====")
    remote(args.node, "exited-count", check=True)
    remote(args.node, "exited", check=False)

    if not args.execute:
        print()
        print("Dry-run uniquement : aucune suppression.")
        print()
        print("Pour nettoyer les conteneurs Exited :")
        print(f"  {sys.argv[0]} --node {args.node} --execute")
        print()
        print("Pour nettoyer aussi les images/couches non utilisées :")
        print(f"  {sys.argv[0]} --node {args.node} --execute --prune-images")
        return 0

    print()
    print("===== Nettoyage conteneurs Exited =====")
    remote(args.node, "prune-exited", check=True)

    if args.prune_images:
        print()
        print("===== Nettoyage images/couches non utilisées =====")
        remote(args.node, "prune-images", check=True)

    print()
    print("===== Etat disque final =====")
    remote(args.node, "disk", check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
