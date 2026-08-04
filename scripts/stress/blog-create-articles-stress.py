#!/usr/bin/env python3
import argparse
import io
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests


DEFAULT_IMAGE = (
    Path(__file__).resolve().parents[2]
    / "uploads-images"
    / "gpu-tpu.jpg"
)

LOREM_IPSUM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
    "nisi ut aliquip ex ea commodo consequat."
)


def positive_integer(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("la valeur doit etre superieure a zero")
    return number


def percentile(values, percent):
    if not values:
        return 0.0

    sorted_values = sorted(values)

    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (percent / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower

    return (
        sorted_values[lower] * (1 - weight)
        + sorted_values[upper] * weight
    )


def format_latency_stats(prefix, values):
    if not values:
        print(f"{prefix}_COUNT=0")
        return

    print(f"{prefix}_COUNT={len(values)}")
    print(f"{prefix}_MIN={min(values):.3f}s")
    print(f"{prefix}_P50={percentile(values, 50):.3f}s")
    print(f"{prefix}_P95={percentile(values, 95):.3f}s")
    print(f"{prefix}_P99={percentile(values, 99):.3f}s")
    print(f"{prefix}_MAX={max(values):.3f}s")


def create_connection_articles(
    connection_number,
    articles_per_connection,
    base_url,
    host_header,
    image_bytes,
    run_id,
    timeout,
):
    session = requests.Session()
    session.headers.update({"Host": host_header})
    results = []

    connection_started_at = time.perf_counter()

    try:
        for article_number in range(1, articles_per_connection + 1):
            marker = (
                f"[STRESS:{run_id}:"
                f"C{connection_number:04d}:A{article_number:02d}]"
            )
            today = datetime.now().astimezone().date().isoformat()

            data = {
                "title": f"{marker} Article de test {today}",
                "content": (
                    f"{marker}\n"
                    f"Run de stress du {today}.\n\n"
                    f"{LOREM_IPSUM}"
                ),
            }
            files = {
                "image": (
                    f"stress-{run_id}-{connection_number:04d}-"
                    f"{article_number:02d}.jpg",
                    io.BytesIO(image_bytes),
                    "image/jpeg",
                )
            }

            article_started_at = time.perf_counter()

            try:
                response = session.post(
                    f"{base_url}/api/createArticle",
                    data=data,
                    files=files,
                    timeout=timeout,
                )
                elapsed = time.perf_counter() - article_started_at
                success = response.status_code == 201

                results.append({
                    "success": success,
                    "connection": connection_number,
                    "article": article_number,
                    "status": response.status_code,
                    "duration": elapsed,
                    "error": "" if success else response.text[:300],
                })
            except requests.RequestException as exc:
                results.append({
                    "success": False,
                    "connection": connection_number,
                    "article": article_number,
                    "status": None,
                    "duration": time.perf_counter() - article_started_at,
                    "error": str(exc),
                })
    finally:
        session.close()

    connection_duration = time.perf_counter() - connection_started_at

    return {
        "connection": connection_number,
        "connection_duration": connection_duration,
        "articles": results,
    }


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Cree des articles de stress via des connexions HTTP simultanees."
        )
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--host-header", default="blog.k8s.test")
    parser.add_argument(
        "--connections",
        required=True,
        type=positive_integer,
    )
    parser.add_argument(
        "--articles-per-connection",
        type=positive_integer,
        default=3,
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_IMAGE,
    )
    parser.add_argument("--run-id")
    parser.add_argument("--timeout", type=positive_integer, default=30)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help=(
            "N'affiche pas chaque requete OK. "
            "Les erreurs restent affichees."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    image_path = args.image.expanduser().resolve()

    if not image_path.is_file():
        print(f"ERREUR: image introuvable: {image_path}", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    run_id = args.run_id or (
        datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid.uuid4().hex[:6]
    )

    print(f"RUN_ID={run_id}")
    print(f"BASE_URL={base_url}")
    print(f"HOST_HEADER={args.host_header}")
    print(f"CONNEXIONS={args.connections}")
    print(f"ARTICLES_PAR_CONNEXION={args.articles_per_connection}")
    print(f"IMAGE={image_path}")
    print(f"THREAD_PRINCIPAL={threading.current_thread().name}")
    print(f"SUMMARY_ONLY={args.summary_only}")

    image_bytes = image_path.read_bytes()
    started_at = time.perf_counter()

    article_results = []
    connection_results = []

    with ThreadPoolExecutor(max_workers=args.connections) as executor:
        futures = [
            executor.submit(
                create_connection_articles,
                connection_number,
                args.articles_per_connection,
                base_url,
                args.host_header,
                image_bytes,
                run_id,
                args.timeout,
            )
            for connection_number in range(1, args.connections + 1)
        ]

        for future in as_completed(futures):
            connection_result = future.result()
            connection_results.append(connection_result)
            article_results.extend(connection_result["articles"])

    duration = time.perf_counter() - started_at
    successes = sum(result["success"] for result in article_results)
    errors = len(article_results) - successes
    throughput = successes / duration if duration else 0.0

    by_connection = defaultdict(list)
    for result in article_results:
        by_connection[result["connection"]].append(result)

    if not args.summary_only:
        for result in sorted(
            article_results,
            key=lambda item: (item["connection"], item["article"]),
        ):
            state = "OK" if result["success"] else "ERREUR"
            status = result["status"] if result["status"] is not None else "-"
            print(
                f"{state} C{result['connection']:04d} "
                f"A{result['article']:02d} HTTP={status} "
                f"DUREE={result['duration']:.3f}s"
            )
            if result["error"]:
                print(f"  DETAIL={result['error']}", file=sys.stderr)
    else:
        for result in sorted(
            article_results,
            key=lambda item: (item["connection"], item["article"]),
        ):
            if result["success"]:
                continue

            status = result["status"] if result["status"] is not None else "-"
            print(
                f"ERREUR C{result['connection']:04d} "
                f"A{result['article']:02d} HTTP={status} "
                f"DUREE={result['duration']:.3f}s"
            )
            if result["error"]:
                print(f"  DETAIL={result['error']}", file=sys.stderr)

    article_durations = [
        result["duration"]
        for result in article_results
    ]
    successful_article_durations = [
        result["duration"]
        for result in article_results
        if result["success"]
    ]
    connection_durations = [
        result["connection_duration"]
        for result in connection_results
    ]

    print("===== RESUME =====")
    print(f"RUN_ID={run_id}")
    print(f"SUCCES={successes}")
    print(f"ERREURS={errors}")
    print(f"DUREE={duration:.3f}s")
    print(f"DEBIT={throughput:.2f} articles/s")

    print("===== LATENCES ARTICLES TOUTES REQUETES =====")
    format_latency_stats("ARTICLE_LATENCE", article_durations)

    print("===== LATENCES ARTICLES SUCCES =====")
    format_latency_stats("ARTICLE_SUCCES_LATENCE", successful_article_durations)

    print("===== LATENCES CONNEXIONS SIMULEES =====")
    format_latency_stats("CONNEXION_LATENCE", connection_durations)

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
