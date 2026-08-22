#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

CANAL_NAMESPACE = "kube-system"
CANAL_DAEMONSET = "rke2-canal"
CANAL_LABEL = "k8s-app=canal"
APP_NAMESPACE = "lab-k8s"

SSH_TARGET_OVERRIDES = {
    "rke2-worker-1": "rke2-worker-1-maint",
    "rke2-worker-2": "rke2-worker-2-maint",
}


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def run_cmd(
    cmd: List[str],
    *,
    check: bool = True,
    capture: bool = True,
    print_command: bool = True,
) -> subprocess.CompletedProcess[str]:
    if print_command:
        print("$ " + " ".join(cmd))

    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )

    if capture and result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")

    if check and result.returncode != 0:
        print(f"ERROR: commande en échec, code={result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    return result


def kubectl(args: List[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return run_cmd(["kubectl"] + args, check=check, capture=capture)


def kubectl_json(args: List[str]) -> Dict[str, Any]:
    result = subprocess.run(
        ["kubectl"] + args + ["-o", "json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        sys.exit(result.returncode)
    return json.loads(result.stdout)


def require_tools() -> None:
    if shutil.which("kubectl") is None:
        print("ERROR: binaire manquant: kubectl", file=sys.stderr)
        sys.exit(127)


def get_node(node: str) -> Dict[str, Any]:
    return kubectl_json(["get", "node", node])


def node_labels(node_obj: Dict[str, Any]) -> Dict[str, str]:
    return node_obj.get("metadata", {}).get("labels", {}) or {}


def is_control_plane(labels: Dict[str, str]) -> bool:
    return any(key in labels for key in (
        "node-role.kubernetes.io/control-plane",
        "node-role.kubernetes.io/master",
        "node-role.kubernetes.io/etcd",
    ))


def rke2_service_for_node(labels: Dict[str, str]) -> str:
    return "rke2-server" if is_control_plane(labels) else "rke2-agent"


def ssh_target_for_node(node: str, ssh_target: Optional[str]) -> str:
    return ssh_target or SSH_TARGET_OVERRIDES.get(node, node)


def find_canal_pod(node: str) -> Optional[Dict[str, Any]]:
    pods = kubectl_json(["-n", CANAL_NAMESPACE, "get", "pods", "-l", CANAL_LABEL])
    for pod in pods.get("items", []):
        if pod.get("spec", {}).get("nodeName") == node:
            return pod
    return None


def pod_ready_summary(pod: Dict[str, Any]) -> Tuple[str, int, int, int]:
    status = pod.get("status", {})
    phase = status.get("phase", "Unknown")
    container_statuses = status.get("containerStatuses", []) or []
    total = len(container_statuses)
    ready = sum(1 for item in container_statuses if item.get("ready"))
    restarts = sum(int(item.get("restartCount", 0)) for item in container_statuses)
    return phase, ready, total, restarts


def canal_pod_name_or_exit(node: str) -> str:
    pod = find_canal_pod(node)
    if not pod:
        print(f"ERROR: aucun pod {CANAL_DAEMONSET} trouvé sur le node {node}", file=sys.stderr)
        sys.exit(2)
    return pod.get("metadata", {}).get("name", "")


def print_node_role(node: str, node_obj: Dict[str, Any]) -> None:
    labels = node_labels(node_obj)
    role = "control-plane/master" if is_control_plane(labels) else "worker"
    service = rke2_service_for_node(labels)
    print(f"NODE={node}")
    print(f"NODE_ROLE={role}")
    print(f"RKE2_SERVICE={service}")


def action_list_nodes() -> None:
    print_section("NODES")
    kubectl(["get", "nodes", "-o", "wide", "--show-labels"])


def action_status(args: argparse.Namespace) -> None:
    node_obj = get_node(args.node)

    print_section("NODE")
    print_node_role(args.node, node_obj)
    kubectl(["get", "node", args.node, "-o", "wide"])

    print_section("DAEMONSET CANAL")
    kubectl(["-n", CANAL_NAMESPACE, "get", "ds", CANAL_DAEMONSET, "-o", "wide"])

    print_section("POD CANAL SUR LE NODE")
    pod = find_canal_pod(args.node)
    if not pod:
        print(f"CANAL_POD=ABSENT node={args.node}")
    else:
        name = pod.get("metadata", {}).get("name", "")
        phase, ready, total, restarts = pod_ready_summary(pod)
        print(f"CANAL_POD={name}")
        print(f"CANAL_STATUS={phase}")
        print(f"CANAL_READY={ready}/{total}")
        print(f"CANAL_RESTARTS={restarts}")
        kubectl(["-n", CANAL_NAMESPACE, "get", "pod", name, "-o", "wide"])

    print_section("PODS APPLICATIFS")
    kubectl(["-n", APP_NAMESPACE, "get", "pods", "-o", "wide"], check=False)


def print_describe_events(namespace: str, pod_name: str) -> None:
    result = subprocess.run(
        ["kubectl", "-n", namespace, "describe", "pod", pod_name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = result.stdout or ""
    if "Events:" in output:
        print(output.split("Events:", 1)[1].strip())
    else:
        print(output[-3000:])


def action_diagnose(args: argparse.Namespace) -> None:
    action_status(args)

    print_section("EVENTS POD CANAL")
    pod_name = canal_pod_name_or_exit(args.node)
    print_describe_events(CANAL_NAMESPACE, pod_name)

    print_section("RECHERCHE PODS BLOQUES")
    result = subprocess.run(
        ["kubectl", "get", "pods", "-A", "-o", "wide"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    output = result.stdout or ""
    lines = [
        line for line in output.splitlines()
        if any(s in line for s in (
            "ContainerCreating",
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "ErrImagePull",
            "Failed",
            "Error",
        ))
    ]

    if lines:
        for line in lines:
            print(line)
    else:
        print("AUCUN_POD_BLOQUE_DETECTE=OK")

    print_section("CLASSIFICATION DIAGNOSTIC")
    lower_output = output.lower()

    if any(pattern in lower_output for pattern in (
        "failedcreatepodsandbox",
        "plugin type=\"calico\"",
        "clusterinformation",
        "cni",
        "failed to create pod sandbox",
    )):
        print("DIAGNOSTIC_PROBABLE=CANAL_CNI")
        print("RECOMMANDATION=utiliser repair-canal sur le node concerné, puis restart-rke2 seulement si nécessaire")
    elif any(pattern in lower_output for pattern in (
        "imagepullbackoff",
        "errimagepull",
        "failed to pull image",
        "back-off pulling image",
    )):
        print("DIAGNOSTIC_PROBABLE=REGISTRY_OR_IMAGE_PULL")
        print("RECOMMANDATION=ne pas réparer Canal en premier ; vérifier registry, tag image, disponibilité Docker Hub et imagePullPolicy")
    elif lines:
        print("DIAGNOSTIC_PROBABLE=POD_ERROR_OTHER")
        print("RECOMMANDATION=inspecter les events du pod concerné avant action Canal")
    else:
        print("DIAGNOSTIC_PROBABLE=NONE")
        print("RECOMMANDATION=aucune réparation Canal nécessaire actuellement")


def action_repair_canal(args: argparse.Namespace) -> None:
    node_obj = get_node(args.node)
    labels = node_labels(node_obj)
    control_plane = is_control_plane(labels)
    pod_name = canal_pod_name_or_exit(args.node)

    print_section("REPAIR CANAL")
    print(f"NODE={args.node}")
    print(f"CANAL_POD_TARGET={pod_name}")

    if control_plane and args.execute and not args.allow_control_plane:
        print("ERROR: le node ciblé est un control-plane/master.")
        print("La suppression réelle du pod Canal sur un master nécessite: --allow-control-plane")
        sys.exit(3)

    if not args.execute:
        print("MODE=SIMULATION")
        print("AUCUNE_MODIFICATION_EFFECTUEE")
        print("Commande qui serait exécutée :")
        print(f"kubectl -n {CANAL_NAMESPACE} delete pod {pod_name}")
        print(f"kubectl -n {CANAL_NAMESPACE} rollout status ds/{CANAL_DAEMONSET} --timeout={args.timeout}s")
        return

    print("MODE=EXECUTION")
    kubectl(["-n", CANAL_NAMESPACE, "delete", "pod", pod_name])
    kubectl(["-n", CANAL_NAMESPACE, "rollout", "status", f"ds/{CANAL_DAEMONSET}", f"--timeout={args.timeout}s"])

    print_section("CANAL APRES REPARATION")
    new_pod = find_canal_pod(args.node)
    if not new_pod:
        print(f"ERROR: aucun nouveau pod Canal trouvé sur {args.node}", file=sys.stderr)
        sys.exit(2)
    new_name = new_pod.get("metadata", {}).get("name", "")
    phase, ready, total, restarts = pod_ready_summary(new_pod)
    print(f"NEW_CANAL_POD={new_name}")
    print(f"NEW_CANAL_STATUS={phase}")
    print(f"NEW_CANAL_READY={ready}/{total}")
    print(f"NEW_CANAL_RESTARTS={restarts}")
    kubectl(["-n", CANAL_NAMESPACE, "get", "pod", new_name, "-o", "wide"])


def action_restart_rke2(args: argparse.Namespace) -> None:
    node_obj = get_node(args.node)
    labels = node_labels(node_obj)
    control_plane = is_control_plane(labels)
    service = rke2_service_for_node(labels)
    target = ssh_target_for_node(args.node, args.ssh_target)

    print_section("RESTART RKE2 SERVICE")
    print(f"NODE={args.node}")
    print(f"SSH_TARGET={target}")
    print(f"RKE2_SERVICE={service}")

    if control_plane and not args.allow_control_plane:
        print("ERROR: le node ciblé est un control-plane/master.")
        print("Pour autoriser explicitement cette action, ajouter: --allow-control-plane")
        sys.exit(3)

    remote_command = (
        "set -e; "
        "hostname; "
        f"sudo systemctl restart {service}; "
        f"sudo systemctl is-active {service}; "
        f"echo RESTART_{service}=OK"
    )

    if not args.execute:
        print("MODE=SIMULATION")
        print("AUCUNE_MODIFICATION_EFFECTUEE")
        print("Commande qui serait exécutée :")
        print(f"ssh -t {target!r} {remote_command!r}")
        return

    print("MODE=EXECUTION")
    run_cmd(["ssh", "-t", target, remote_command], check=True, capture=True)

    if args.wait_seconds > 0:
        print(f"ATTENTE={args.wait_seconds}s")
        time.sleep(args.wait_seconds)

    print_section("NODE APRES RESTART")
    kubectl(["get", "node", args.node, "-o", "wide"], check=False)


def action_full_repair(args: argparse.Namespace) -> None:
    print_section("FULL REPAIR - ETAPE 1/2: CANAL")
    action_repair_canal(args)

    print_section("FULL REPAIR - ETAPE 2/2: RKE2 SERVICE")
    if not args.include_rke2_restart:
        print("RKE2_RESTART=SKIPPED")
        print("Pour inclure le redémarrage rke2-agent/rke2-server, ajouter: --include-rke2-restart")
        return

    action_restart_rke2(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnostic et réparation contrôlée Canal/Calico RKE2 sur un node.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "action",
        choices=[
            "list-nodes",
            "status",
            "diagnose",
            "repair-canal",
            "restart-rke2",
            "full-repair",
        ],
        help="Action à exécuter.",
    )
    parser.add_argument("--node", help="Nom du node Kubernetes ciblé.")
    parser.add_argument("--execute", action="store_true", help="Applique réellement l'action. Sinon simulation.")
    parser.add_argument("--allow-control-plane", action="store_true", help="Autorise explicitement une action sur master/control-plane.")
    parser.add_argument("--include-rke2-restart", action="store_true", help="Avec full-repair, inclut le restart rke2.")
    parser.add_argument("--ssh-target", help="Cible SSH à utiliser au lieu du mapping automatique.")
    parser.add_argument("--timeout", type=int, default=90, help="Timeout rollout Canal en secondes.")
    parser.add_argument("--wait-seconds", type=int, default=30, help="Attente après restart rke2.")
    return parser


def main() -> int:
    require_tools()
    parser = build_parser()
    args = parser.parse_args()

    if args.action != "list-nodes" and not args.node:
        parser.error("--node est obligatoire pour cette action")

    if args.action == "list-nodes":
        action_list_nodes()
    elif args.action == "status":
        action_status(args)
    elif args.action == "diagnose":
        action_diagnose(args)
    elif args.action == "repair-canal":
        action_repair_canal(args)
    elif args.action == "restart-rke2":
        action_restart_rke2(args)
    elif args.action == "full-repair":
        action_full_repair(args)
    else:
        parser.error("action inconnue")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
