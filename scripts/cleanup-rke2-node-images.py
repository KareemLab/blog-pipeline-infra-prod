#!/usr/bin/env python3
"""
- Nettoyage contrôlé des images containerd RKE2 sur un node.

Rôle :
- diagnostiquer l'espace disque du node cible ;
- lister les images containerd RKE2 présentes sur le node ;
- comparer avec les images utilisées par les pods Kubernetes ;
- comparer avec les images déclarées dans apps/blog-preprod/ ;
- proposer des candidates au nettoyage ;
- ne rien supprimer par défaut.

Usage lecture seule :
  ./scripts/cleanup-rke2-node-images.py

Usage nettoyage :
  Le mode nettoyage sera activé dans une future version du wrapper.
  Pour l'instant, ce script est diagnostic/dry-run uniquement.

Par défaut, le node cible SSH est rke2-worker-2-maint.
"""

from pathlib import Path
import argparse
import json
import re
import subprocess
import sys


DEFAULT_NODE = "rke2-worker-2-maint"
APP_MANIFEST_DIR = Path("apps/blog-preprod")
WRAPPER_BIN = "/usr/local/sbin/rke2-image-maintenance"


def run(cmd, check=True):
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if check and result.returncode != 0:
        print("ERROR: commande échouée", file=sys.stderr)
        print(" ".join(cmd), file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)

    return result.stdout.strip(), result.stderr.strip(), result.returncode


def ssh(node, command, check=True):
    return run(["ssh", node, command], check=check)


def normalize_image_ref(ref):
    ref = ref.strip()

    if not ref:
        return ref

    # Kubernetes accepte souvent kareemdev2/image:tag,
    # containerd l'affiche souvent docker.io/kareemdev2/image:tag.
    if ref.startswith("docker.io/"):
        ref = ref[len("docker.io/"):]

    if ref.startswith("registry-1.docker.io/"):
        ref = ref[len("registry-1.docker.io/"):]

    return ref


def preflight_ssh_sudo(node):
    print("===== Préflight SSH/wrapper =====")
    print(f"Node cible SSH: {node}")
    print()
    print("Le script utilise un wrapper sudo limité :")
    print(f"  sudo -n {WRAPPER_BIN}")
    print()
    print("Aucun sudo global sans mot de passe n'est requis.")
    print()

    command = (
        "echo SSH_OK_ON_$(hostname) && "
        f"sudo -n {WRAPPER_BIN} --help >/dev/null && "
        "echo WRAPPER_SUDO_OK"
    )

    stdout, stderr, code = ssh(node, command, check=False)

    if stdout:
        print(stdout)
    if stderr:
        print(stderr)

    if code != 0 or "WRAPPER_SUDO_OK" not in stdout:
        print("ERROR: préflight SSH/wrapper échoué", file=sys.stderr)
        print("Vérifie :", file=sys.stderr)
        print(f"  ssh {node} 'sudo -n {WRAPPER_BIN} --help'", file=sys.stderr)
        sys.exit(code if code != 0 else 1)

def get_pod_images(kubectl):
    output, _, _ = run([kubectl, "get", "pods", "-A", "-o", "json"])
    data = json.loads(output)

    images = set()

    for item in data.get("items", []):
        spec = item.get("spec", {})

        for section in ("initContainers", "containers", "ephemeralContainers"):
            for container in spec.get(section, []) or []:
                image = container.get("image")
                if image:
                    images.add(normalize_image_ref(image))

    return images


def get_declared_app_images():
    images = set()

    if not APP_MANIFEST_DIR.exists():
        return images

    pattern = re.compile(r"^\s*image:\s*([^\s]+)\s*$")

    for yaml_path in APP_MANIFEST_DIR.rglob("*.yaml"):
        text = yaml_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                images.add(normalize_image_ref(match.group(1)))

    return images


def parse_ctr_images(output):
    images = []

    for line in output.splitlines():
        if not line.strip() or line.startswith("REF "):
            continue

        parts = line.split()
        ref = parts[0]

        size = "UNKNOWN"
        if len(parts) >= 4:
            size = parts[3]
            if len(parts) >= 5 and re.match(r"^(B|KiB|MiB|GiB)$", parts[4]):
                size = f"{parts[3]} {parts[4]}"

        images.append({
            "ref": ref,
            "normalized": normalize_image_ref(ref),
            "size": size,
            "raw": line,
        })

    return images


def get_node_images(node):
    command = f"sudo -n {WRAPPER_BIN} images"
    output, _, _ = ssh(node, command)
    return parse_ctr_images(output)


def get_disk_summary(node):
    command = f"sudo -n {WRAPPER_BIN} disk"
    output, _, _ = ssh(node, command)
    return output


def is_cleanup_candidate(image, used_images, declared_images):
    ref = image["ref"]
    normalized = image["normalized"]

    # Garde-fou : ne jamais proposer les références digest-only.
    # On commence par nettoyer uniquement des tags explicites.
    if "@sha256:" in ref:
        return False, "skip digest reference"

    # Garde-fou : ne jamais proposer une image utilisée par les pods.
    if normalized in used_images:
        return False, "used by Kubernetes pod"

    # Garde-fou : ne jamais proposer une image déclarée dans apps/blog-preprod.
    if normalized in declared_images:
        return False, "declared in apps/blog-preprod"

    # Candidates limitées aux images applicatives du lab.
    if "kareemdev2/blog-back-" not in normalized:
        return False, "not an application image"

    # latest est typiquement un ancien reliquat dangereux en GitOps immuable.
    if normalized.endswith(":latest"):
        return True, "old mutable tag latest"

    # Anciennes versions prod-* non utilisées / non déclarées.
    if re.search(r":prod-\d+$", normalized):
        return True, "old unused prod tag"

    return False, "no cleanup rule matched"


def remove_image(node, ref):
    raise RuntimeError(
        "Le mode execute n'est pas encore activé. "
        "Le wrapper actuel est limité au diagnostic."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostic et nettoyage contrôlé des images RKE2/containerd."
    )
    parser.add_argument("--node", default=DEFAULT_NODE, help="Node cible SSH")
    parser.add_argument("--kubectl", default="kubectl", help="Commande kubectl")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Réservé pour une future version. Le wrapper actuel est diagnostic only.",
    )

    args = parser.parse_args()

    if args.execute:
        print("ERROR: --execute est désactivé pour l'instant.", file=sys.stderr)
        print("Le wrapper actuel est diagnostic only.", file=sys.stderr)
        sys.exit(1)

    mode = "EXECUTE" if args.execute else "DRY-RUN"

    print(f"MODE={mode}")
    print(f"NODE={args.node}")
    print()

    preflight_ssh_sudo(args.node)
    print()

    print(get_disk_summary(args.node))
    print()

    used_images = get_pod_images(args.kubectl)
    declared_images = get_declared_app_images()
    node_images = get_node_images(args.node)

    print("===== Images utilisées par les pods Kubernetes =====")
    for image in sorted(used_images):
        print(f"- {image}")

    print()
    print("===== Images déclarées dans apps/blog-preprod =====")
    for image in sorted(declared_images):
        print(f"- {image}")

    print()
    print("===== Images applicatives présentes sur le node =====")
    app_images = [
        image for image in node_images
        if "kareemdev2/blog-back-" in image["normalized"]
    ]

    for image in app_images:
        print(f"- {image['ref']} ({image['size']})")

    print()
    print("===== Candidates nettoyage =====")

    candidates = []

    for image in node_images:
        candidate, reason = is_cleanup_candidate(image, used_images, declared_images)
        if candidate:
            candidates.append((image, reason))

    if not candidates:
        print("Aucune candidate détectée.")
    else:
        for image, reason in candidates:
            print(f"- {image['ref']} ({image['size']}) -> {reason}")

    if not args.execute:
        print()
        print("Dry-run uniquement : aucune image supprimée.")
        print("Le mode nettoyage réel est désactivé pour l'instant.")
        print("Le wrapper actuel est diagnostic only.")
        return

    print()
    print("===== Suppression des candidates =====")

    for image, reason in candidates:
        print(f"Suppression: {image['ref']} ({reason})")
        stdout, stderr, code = remove_image(args.node, image["ref"])
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
        if code != 0:
            print(f"WARNING: échec suppression {image['ref']} code={code}")

    print()
    print("===== Disque après nettoyage =====")
    print(get_disk_summary(args.node))


if __name__ == "__main__":
    main()
