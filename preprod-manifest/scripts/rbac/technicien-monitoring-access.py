#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


KUBECTL_BIN = os.environ.get("KUBECTL_BIN", "kubectl")
NAMESPACE = os.environ.get("NAMESPACE", "monitoring")
SERVICE_ACCOUNT = os.environ.get("SERVICE_ACCOUNT", "technicien-monitoring")
TECH_USER = os.environ.get("TECH_USER", "technicien-monitoring")
TECH_HOME = os.environ.get("TECH_HOME", f"/home/{TECH_USER}")
KUBE_CONFIG = os.environ.get("KUBE_CONFIG", f"{TECH_HOME}/.kube/config")
CLUSTER_ALIAS = os.environ.get("CLUSTER_ALIAS", "rke2-lab")
DEFAULT_DURATION = os.environ.get("DEFAULT_DURATION", "720h")


def run(command, check=True):
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if check and result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)

    return result


def output(command):
    return run(command, check=True).stdout.strip()


def ensure_duration(value):
    if not re.fullmatch(r"[0-9]+[smh]", value):
        raise SystemExit(
            f"ERREUR: durée invalide: {value}. "
            "Utiliser par exemple 24h, 168h ou 720h."
        )


def ensure_linux_user():
    result = run(["id", TECH_USER], check=False)
    if result.returncode != 0:
        raise SystemExit(f"ERREUR: utilisateur Linux absent: {TECH_USER}")


def ensure_service_account():
    run(
        [
            KUBECTL_BIN,
            "-n",
            NAMESPACE,
            "get",
            "serviceaccount",
            SERVICE_ACCOUNT,
            "-o",
            "name",
        ],
        check=True,
    )


def get_cluster_values():
    server = output(
        [
            KUBECTL_BIN,
            "config",
            "view",
            "--raw",
            "--minify",
            "-o",
            "jsonpath={.clusters[0].cluster.server}",
        ]
    )

    ca_data = output(
        [
            KUBECTL_BIN,
            "config",
            "view",
            "--raw",
            "--minify",
            "-o",
            "jsonpath={.clusters[0].cluster.certificate-authority-data}",
        ]
    )

    if not server:
        raise SystemExit("ERREUR: server Kubernetes introuvable.")

    if not ca_data:
        raise SystemExit("ERREUR: certificate-authority-data introuvable.")

    return server, ca_data


def kubeconfig_exists():
    return run(["sudo", "test", "-f", KUBE_CONFIG], check=False).returncode == 0


def run_as_technician(args, check=False):
    return run(
        [
            "sudo",
            "-u",
            TECH_USER,
            "env",
            f"KUBECONFIG={KUBE_CONFIG}",
            KUBECTL_BIN,
            *args,
        ],
        check=check,
    )



def get_token_metadata():
    if not kubeconfig_exists():
        return None

    result = run(
        [
            "sudo",
            "awk",
            "/^[[:space:]]*token:/ {print $2; exit}",
            KUBE_CONFIG,
        ],
        check=False,
    )

    token = result.stdout.strip()

    if not token:
        return None

    parts = token.split(".")
    if len(parts) < 2:
        return {"error": "token non JWT ou format inattendu"}

    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
    except Exception as exc:
        return {"error": f"payload JWT illisible: {exc}"}

    exp = payload.get("exp")
    iat = payload.get("iat")

    if not exp:
        return {"error": "champ exp absent du token"}

    now = datetime.now(timezone.utc)
    exp_dt = datetime.fromtimestamp(int(exp), tz=timezone.utc)
    remaining_seconds = int((exp_dt - now).total_seconds())

    if iat:
        iat_dt = datetime.fromtimestamp(int(iat), tz=timezone.utc)
        issued_at = iat_dt.isoformat().replace("+00:00", "Z")
    else:
        issued_at = "UNKNOWN"

    if remaining_seconds <= 0:
        remaining = "EXPIRED"
    else:
        days, rem = divmod(remaining_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        remaining = f"{days}d {hours}h {minutes}m {seconds}s"

    return {
        "issued_at": issued_at,
        "expires_at": exp_dt.isoformat().replace("+00:00", "Z"),
        "remaining": remaining,
    }


def action_status(_args):
    print(f"TECH_USER={TECH_USER}")
    print(f"TECH_HOME={TECH_HOME}")
    print(f"KUBE_CONFIG={KUBE_CONFIG}")
    print(f"NAMESPACE={NAMESPACE}")
    print(f"SERVICE_ACCOUNT={SERVICE_ACCOUNT}")

    user_result = run(["id", TECH_USER], check=False)
    if user_result.returncode == 0:
        print("LINUX_USER=OK")
        print(user_result.stdout.strip())
    else:
        print("LINUX_USER=ABSENT")

    sa_result = run(
        [
            KUBECTL_BIN,
            "-n",
            NAMESPACE,
            "get",
            "serviceaccount",
            SERVICE_ACCOUNT,
            "-o",
            "name",
        ],
        check=False,
    )
    if sa_result.returncode == 0:
        print("SERVICE_ACCOUNT=OK")
        print(sa_result.stdout.strip())
    else:
        print("SERVICE_ACCOUNT=ABSENT")

    if kubeconfig_exists():
        print("KUBECONFIG=OK")
        stat_result = run(
            [
                "sudo",
                "stat",
                "-c",
                "OWNER=%U GROUP=%G MODE=%a PATH=%n",
                KUBE_CONFIG,
            ],
            check=True,
        )
        print(stat_result.stdout.strip())

        token_metadata = get_token_metadata()
        if token_metadata is None:
            print("TOKEN_STATUS=UNKNOWN")
        elif "error" in token_metadata:
            print(f"TOKEN_STATUS=UNKNOWN REASON={token_metadata['error']}")
        else:
            print(f"TOKEN_ISSUED_AT_UTC={token_metadata['issued_at']}")
            print(f"TOKEN_EXPIRES_AT_UTC={token_metadata['expires_at']}")
            print(f"TOKEN_REMAINING={token_metadata['remaining']}")
    else:
        print("KUBECONFIG=ABSENT")


def action_show_config(_args):
    if not kubeconfig_exists():
        raise SystemExit(f"ERREUR: kubeconfig absent: {KUBE_CONFIG}")

    result = run(
        [
            "sudo",
            "sed",
            "-E",
            r"s/(token: ).*/\1***REDACTED***/",
            KUBE_CONFIG,
        ],
        check=True,
    )
    print(result.stdout, end="")


def expect_forbidden(title, kubectl_args):
    print(title)
    result = run_as_technician(kubectl_args, check=False)
    combined = f"{result.stdout}{result.stderr}"

    if result.returncode == 0:
        print(combined, end="")
        raise SystemExit("ERREUR: action interdite mais autorisée.")

    print(combined, end="")

    if "Forbidden" not in combined:
        raise SystemExit("ERREUR: échec inattendu, Forbidden non trouvé.")


def action_test(_args):
    ensure_linux_user()

    if not kubeconfig_exists():
        raise SystemExit(f"ERREUR: kubeconfig absent: {KUBE_CONFIG}")

    print("=== CONTEXTE ===")
    result = run_as_technician(["config", "current-context"], check=True)
    print(result.stdout.strip())

    print("=== TEST AUTORISÉ: get nodes ===")
    result = run_as_technician(["get", "nodes"], check=True)
    print(result.stdout, end="")

    print("=== TEST AUTORISÉ: get pods -n monitoring ===")
    result = run_as_technician(["get", "pods", "-n", NAMESPACE], check=True)
    print("\n".join(result.stdout.splitlines()[:8]))

    expect_forbidden(
        "=== TEST INTERDIT: get secrets -n monitoring ===",
        ["get", "secrets", "-n", NAMESPACE],
    )
    print("SECRET_FORBIDDEN=OK")

    expect_forbidden(
        "=== TEST INTERDIT: get pods -n kube-system ===",
        ["get", "pods", "-n", "kube-system"],
    )
    print("KUBE_SYSTEM_FORBIDDEN=OK")

    print("VERIFICATION=OK")


def build_kubeconfig(server, ca_data, token):
    return f"""apiVersion: v1
kind: Config
clusters:
- name: {CLUSTER_ALIAS}
  cluster:
    server: {server}
    certificate-authority-data: {ca_data}
contexts:
- name: {SERVICE_ACCOUNT}@{CLUSTER_ALIAS}
  context:
    cluster: {CLUSTER_ALIAS}
    namespace: {NAMESPACE}
    user: {SERVICE_ACCOUNT}
current-context: {SERVICE_ACCOUNT}@{CLUSTER_ALIAS}
users:
- name: {SERVICE_ACCOUNT}
  user:
    token: {token}
"""


def action_renew(args):
    ensure_duration(args.duration)
    ensure_linux_user()
    ensure_service_account()

    server, ca_data = get_cluster_values()

    print(f"TECH_USER={TECH_USER}")
    print(f"KUBE_CONFIG={KUBE_CONFIG}")
    print(f"SERVICE_ACCOUNT={NAMESPACE}/{SERVICE_ACCOUNT}")
    print(f"TOKEN_DURATION={args.duration}")
    print(f"CLUSTER_SERVER={server}")

    if not args.execute:
        print("MODE=SIMULATION")
        print("AUCUN_TOKEN_GENERE")
        print("AUCUNE_MODIFICATION_EFFECTUEE")
        print(
            "Pour appliquer: "
            f"{sys.argv[0]} renew --duration {args.duration} --execute"
        )
        return

    token = output(
        [
            KUBECTL_BIN,
            "-n",
            NAMESPACE,
            "create",
            "token",
            SERVICE_ACCOUNT,
            f"--duration={args.duration}",
        ]
    )

    if not token:
        raise SystemExit("ERREUR: token vide.")

    kubeconfig_content = build_kubeconfig(server, ca_data, token)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        tmp.write(kubeconfig_content)
        tmp_path = tmp.name

    os.chmod(tmp_path, 0o600)

    try:
        run(
            [
                "sudo",
                "install",
                "-d",
                "-m",
                "700",
                "-o",
                TECH_USER,
                "-g",
                TECH_USER,
                f"{TECH_HOME}/.kube",
            ],
            check=True,
        )

        run(
            [
                "sudo",
                "install",
                "-m",
                "600",
                "-o",
                TECH_USER,
                "-g",
                TECH_USER,
                tmp_path,
                KUBE_CONFIG,
            ],
            check=True,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    print("KUBECONFIG_UPDATED=OK")

    stat_result = run(
        [
            "sudo",
            "stat",
            "-c",
            "OWNER=%U GROUP=%G MODE=%a PATH=%n",
            KUBE_CONFIG,
        ],
        check=True,
    )
    print(stat_result.stdout.strip())

    action_test(args)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Gestion du kubeconfig limité du technicien monitoring. "
            "Le token n'est jamais affiché."
        )
    )

    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "show-config", "test", "renew"],
        help="Action à exécuter.",
    )

    parser.add_argument(
        "--duration",
        default=DEFAULT_DURATION,
        help="Durée du token Kubernetes. Exemples: 24h, 168h, 720h.",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Autorise une modification réelle pour l'action renew.",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.action != "renew" and args.execute:
        parser.error("--execute est uniquement valide avec l'action renew")

    if args.action == "status":
        action_status(args)
    elif args.action == "show-config":
        action_show_config(args)
    elif args.action == "test":
        action_test(args)
    elif args.action == "renew":
        action_renew(args)


if __name__ == "__main__":
    main()
