#!/usr/bin/env python3
import argparse
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


DEFAULT_NAMESPACE = "lab-k8s"
DEFAULT_POD = "pg-lab-postgresql-primary-0"
DEFAULT_CONTAINER = "postgresql"
DEFAULT_TABLE = "public.db_stress_articles"

# Valeurs mesurées sur public.article :
# ARTICLE_AVG=title_bytes=58 | content_bytes=271 | image_ref_bytes=30 | pg_row_bytes=405
DEFAULT_TITLE_BYTES = 58
DEFAULT_CONTENT_BYTES = 271
DEFAULT_IMAGE_REF_BYTES = 30


def positive_integer(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("la valeur doit etre superieure a zero")
    return number


def non_negative_float(value):
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("la valeur doit etre positive ou nulle")
    return number


def generate_run_id():
    now = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"{now}-db-{uuid.uuid4().hex[:6]}"


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Lance des writers PostgreSQL vers la table de stress BDD."
    )
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--pod", default=DEFAULT_POD)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--run-id", default=generate_run_id())
    parser.add_argument("--writers", type=positive_integer, default=1)
    parser.add_argument("--duration", type=positive_integer, default=30)
    parser.add_argument("--batch-size", type=positive_integer, default=100)
    parser.add_argument(
        "--title-bytes",
        type=positive_integer,
        default=DEFAULT_TITLE_BYTES,
        help="Taille cible de payload_title en bytes.",
    )
    parser.add_argument(
        "--payload-bytes",
        type=positive_integer,
        default=DEFAULT_CONTENT_BYTES,
        help="Taille cible de payload_content en bytes.",
    )
    parser.add_argument(
        "--image-ref-bytes",
        type=positive_integer,
        default=DEFAULT_IMAGE_REF_BYTES,
        help="Taille cible de payload_image_ref en bytes.",
    )
    parser.add_argument(
        "--target-rate-per-writer",
        type=non_negative_float,
        default=0.0,
        help="Debit cible par writer en lignes/s. 0 = pas de limitation.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Effectue réellement les insertions.",
    )
    return parser.parse_args()


def build_writer_command(args, writer_id):
    bash_script = """
set -euo pipefail

RUN_ID="$1"
WRITER_ID="$2"
DURATION_SECONDS="$3"
BATCH_SIZE="$4"
TITLE_BYTES="$5"
PAYLOAD_BYTES="$6"
IMAGE_REF_BYTES="$7"
TARGET_RATE="$8"
TABLE_NAME="$9"

PGUSER="${POSTGRES_USER:-iksstudent}"
PGDATABASE="${POSTGRES_DATABASE:-blogkubernetesdb}"
PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
export PGPASSWORD

START_NS="$(date +%s%N)"
END_EPOCH=$(( $(date +%s) + DURATION_SECONDS ))

SEQ_START=1
INSERTED_TOTAL=0
BATCHES=0

while [ "$(date +%s)" -lt "$END_EPOCH" ]; do
  SEQ_END=$((SEQ_START + BATCH_SIZE - 1))

  INSERTED_BATCH="$(
    psql -qAt -v ON_ERROR_STOP=1 \
      -h 127.0.0.1 -p 5432 \
      -U "$PGUSER" -d "$PGDATABASE" \
      -v run_id="$RUN_ID" \
      -v writer_id="$WRITER_ID" \
      -v seq_start="$SEQ_START" \
      -v seq_end="$SEQ_END" \
      -v title_bytes="$TITLE_BYTES" \
      -v payload_bytes="$PAYLOAD_BYTES" \
      -v image_ref_bytes="$IMAGE_REF_BYTES" \
      -v table_name="$TABLE_NAME" <<'SQL'
WITH generated AS (
  SELECT
    gs::bigint AS writer_seq,
    left(
      'Article DB stress ' || repeat('T', :title_bytes::integer),
      :title_bytes::integer
    ) AS generated_title,
    repeat('C', :payload_bytes::integer) AS generated_content,
    left(
      'stress-image-ref-' || gs::text || '-' || repeat('I', :image_ref_bytes::integer),
      :image_ref_bytes::integer
    ) AS generated_image_ref
  FROM generate_series(:seq_start::bigint, :seq_end::bigint) AS gs
),
inserted AS (
  INSERT INTO :table_name (
    run_id,
    writer_id,
    writer_seq,
    payload_title,
    payload_content,
    payload_bytes,
    payload_title_bytes,
    payload_image_ref,
    payload_image_ref_bytes
  )
  SELECT
    :'run_id',
    :writer_id::integer,
    writer_seq,
    generated_title,
    generated_content,
    :payload_bytes::integer,
    octet_length(generated_title),
    generated_image_ref,
    octet_length(generated_image_ref)
  FROM generated
  RETURNING 1
)
SELECT count(*) FROM inserted;
SQL
  )"

  INSERTED_TOTAL=$((INSERTED_TOTAL + INSERTED_BATCH))
  BATCHES=$((BATCHES + 1))
  SEQ_START=$((SEQ_END + 1))

  if [ "$TARGET_RATE" != "0" ] && [ "$TARGET_RATE" != "0.0" ]; then
    SLEEP_SECONDS="$(awk -v b="$BATCH_SIZE" -v r="$TARGET_RATE" 'BEGIN { if (r > 0) printf "%.6f", b / r; else printf "0" }')"
    sleep "$SLEEP_SECONDS"
  fi
done

END_NS="$(date +%s%N)"
DURATION_REAL="$(awk -v s="$START_NS" -v e="$END_NS" 'BEGIN { printf "%.3f", (e - s) / 1000000000 }')"
ROWS_PER_SECOND="$(awk -v rows="$INSERTED_TOTAL" -v d="$DURATION_REAL" 'BEGIN { if (d > 0) printf "%.2f", rows / d; else printf "0.00" }')"

echo "WRITER_ID=${WRITER_ID}"
echo "WRITER_BATCHES=${BATCHES}"
echo "WRITER_ROWS=${INSERTED_TOTAL}"
echo "WRITER_DURATION=${DURATION_REAL}s"
echo "WRITER_ROWS_PER_SECOND=${ROWS_PER_SECOND}"
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
        str(writer_id),
        str(args.duration),
        str(args.batch_size),
        str(args.title_bytes),
        str(args.payload_bytes),
        str(args.image_ref_bytes),
        str(args.target_rate_per_writer),
        args.table,
    ]


def run_writer(args, writer_id):
    started_at = time.perf_counter()
    result = subprocess.run(
        build_writer_command(args, writer_id),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    elapsed = time.perf_counter() - started_at

    rows = 0
    for line in result.stdout.splitlines():
        if line.startswith("WRITER_ROWS="):
            rows = int(line.split("=", 1)[1])

    return {
        "writer_id": writer_id,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed": elapsed,
        "rows": rows,
    }


def count_rows(args):
    bash_script = """
set -euo pipefail

RUN_ID="$1"
TABLE_NAME="$2"

PGUSER="${POSTGRES_USER:-iksstudent}"
PGDATABASE="${POSTGRES_DATABASE:-blogkubernetesdb}"
PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
export PGPASSWORD

psql -qAt -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 -p 5432 \
  -U "$PGUSER" -d "$PGDATABASE" \
  -v run_id="$RUN_ID" \
  -v table_name="$TABLE_NAME" <<'SQL'
SELECT count(*) FROM :table_name WHERE run_id = :'run_id';
SQL
"""

    command = [
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
    ]

    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        print(result.stderr.rstrip(), file=sys.stderr)
        return -1

    return int(result.stdout.strip() or "0")


def main():
    args = parse_arguments()

    print(f"RUN_ID={args.run_id}")
    print(f"NAMESPACE={args.namespace}")
    print(f"POD={args.pod}")
    print(f"CONTAINER={args.container}")
    print(f"TABLE={args.table}")
    print(f"WRITERS={args.writers}")
    print(f"DURATION_SECONDS={args.duration}")
    print(f"BATCH_SIZE={args.batch_size}")
    print(f"TITLE_BYTES={args.title_bytes}")
    print(f"PAYLOAD_BYTES={args.payload_bytes}")
    print(f"IMAGE_REF_BYTES={args.image_ref_bytes}")
    print(f"TARGET_RATE_PER_WRITER={args.target_rate_per_writer}")

    if not args.execute:
        print("MODE=SIMULATION")
        print("AUCUNE_INSERTION_EFFECTUEE")
        print("TEST_RC=0")
        return 0

    print("MODE=EXECUTION")

    started_at = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=args.writers) as executor:
        futures = [
            executor.submit(run_writer, args, writer_id)
            for writer_id in range(1, args.writers + 1)
        ]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            print(f"--- WRITER {result['writer_id']} STDOUT ---")
            print(result["stdout"].rstrip())

            if result["stderr"].strip():
                print(
                    f"--- WRITER {result['writer_id']} STDERR ---",
                    file=sys.stderr,
                )
                print(result["stderr"].rstrip(), file=sys.stderr)

    duration = time.perf_counter() - started_at
    total_rows = sum(result["rows"] for result in results)
    rows_per_second = total_rows / duration if duration > 0 else 0.0
    failed = [result for result in results if result["returncode"] != 0]
    rows_in_db = count_rows(args)

    print(f"TOTAL_ROWS={total_rows}")
    print(f"ROWS_IN_DB_FOR_RUN_ID={rows_in_db}")
    print(f"TOTAL_DURATION={duration:.3f}s")
    print(f"TOTAL_ROWS_PER_SECOND={rows_per_second:.2f}")

    if failed:
        print(f"ERREURS_WRITERS={len(failed)}", file=sys.stderr)
        print("TEST_RC=1")
        return 1

    if rows_in_db != total_rows:
        print(
            "ERREUR: le nombre de lignes en base ne correspond pas "
            "au total inséré par les writers.",
            file=sys.stderr,
        )
        print("TEST_RC=2")
        return 2

    print("ERREURS_WRITERS=0")
    print("TEST_RC=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
