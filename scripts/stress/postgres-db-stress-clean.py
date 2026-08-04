#!/usr/bin/env python3
import argparse
import subprocess
import sys


DEFAULT_NAMESPACE = "lab-k8s"
DEFAULT_POD = "pg-lab-postgresql-primary-0"
DEFAULT_CONTAINER = "postgresql"
DEFAULT_TABLE = "public.db_stress_articles"


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Nettoie les lignes de stress BDD par run_id."
    )
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--pod", default=DEFAULT_POD)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Effectue réellement la suppression.",
    )
    return parser.parse_args()


def build_command(args, execute):
    mode = "EXECUTE" if execute else "SIMULATION"

    bash_script = """
set -euo pipefail

RUN_ID="$1"
TABLE_NAME="$2"
MODE="$3"

PGUSER="${POSTGRES_USER:-iksstudent}"
PGDATABASE="${POSTGRES_DATABASE:-blogkubernetesdb}"
PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
export PGPASSWORD

echo "PGDATABASE=${PGDATABASE}"
echo "PGUSER=${PGUSER}"
echo "TABLE=${TABLE_NAME}"

psql -qAt -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 -p 5432 \
  -U "$PGUSER" -d "$PGDATABASE" \
  -v run_id="$RUN_ID" \
  -v table_name="$TABLE_NAME" <<'SQL'
SELECT 'IS_REPLICA=' || pg_is_in_recovery();
SELECT 'DB_STRESS_ROWS_AVANT=' || count(*)
FROM :table_name
WHERE run_id = :'run_id';
SQL

if [ "$MODE" = "SIMULATION" ]; then
  echo "MODE=SIMULATION"
  echo "AUCUNE_SUPPRESSION_EFFECTUEE"
  exit 0
fi

echo "MODE=EXECUTION"

psql -qAt -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 -p 5432 \
  -U "$PGUSER" -d "$PGDATABASE" \
  -v run_id="$RUN_ID" \
  -v table_name="$TABLE_NAME" <<'SQL'
WITH deleted AS (
  DELETE FROM :table_name
  WHERE run_id = :'run_id'
  RETURNING 1
)
SELECT 'DB_STRESS_ROWS_SUPPRIMEES=' || count(*)
FROM deleted;

SELECT 'DB_STRESS_ROWS_APRES=' || count(*)
FROM :table_name
WHERE run_id = :'run_id';
SQL
"""

    return [
        "kubectl",
        "-n",
        args.namespace,
        "exec",
        args.pod,
        "-c",
        args.container,
        "--",
        "bash",
        "-lc",
        bash_script,
        "--",
        args.run_id,
        args.table,
        mode,
    ]


def main():
    args = parse_arguments()

    print(f"RUN_ID={args.run_id}")
    print(f"NAMESPACE={args.namespace}")
    print(f"POD={args.pod}")
    print(f"CONTAINER={args.container}")
    print(f"TABLE={args.table}")

    result = subprocess.run(
        build_command(args, args.execute),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.stdout.strip():
        print(result.stdout.rstrip())

    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)

    if result.returncode != 0:
        print(f"TEST_RC={result.returncode}")
        return result.returncode

    print("TEST_RC=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
