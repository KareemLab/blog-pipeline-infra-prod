#!/usr/bin/env python3
import argparse
import sys

import requests


MARKER = "STRESS:"


def get_articles(session, base_url, timeout):
    response = session.get(
        f"{base_url}/api/articles",
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def is_stress_article(article):
    title = article.get("title") or ""
    content = article.get("content") or ""
    return MARKER in title or MARKER in content


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Supprime uniquement les articles marques STRESS."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--host-header", default="blog.k8s.test")
    parser.add_argument("--expected-seed-count", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Effectue réellement les suppressions.",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    base_url = args.base_url.rstrip("/")

    session = requests.Session()
    session.headers.update({"Host": args.host_header})

    try:
        articles_before = get_articles(session, base_url, args.timeout)
        stress_before = [
            article for article in articles_before
            if is_stress_article(article)
        ]
        seeds_before = [
            article for article in articles_before
            if not is_stress_article(article)
        ]

        print(f"ARTICLES_AVANT={len(articles_before)}")
        print(f"ARTICLES_STRESS_AVANT={len(stress_before)}")
        print(f"ARTICLES_SEED_AVANT={len(seeds_before)}")

        if len(seeds_before) != args.expected_seed_count:
            print(
                "ERREUR: nombre d'articles seed différent de la référence "
                f"attendue ({args.expected_seed_count}).",
                file=sys.stderr,
            )
            return 2

        for article in stress_before:
            print(
                f"CIBLE_STRESS ID={article.get('id')} "
                f"TITRE={article.get('title', '')}"
            )

        if not args.execute:
            print("MODE=SIMULATION")
            print("AUCUNE_SUPPRESSION_EFFECTUEE")
            return 0

        deleted = 0

        for article in stress_before:
            article_id = article.get("id")

            if article_id is None:
                print(
                    "ERREUR: article STRESS sans identifiant.",
                    file=sys.stderr,
                )
                return 3

            response = session.delete(
                f"{base_url}/api/articles/{article_id}",
                timeout=args.timeout,
            )

            if response.status_code != 200:
                print(
                    f"ERREUR: suppression ID={article_id}, "
                    f"HTTP={response.status_code}, "
                    f"REPONSE={response.text[:300]}",
                    file=sys.stderr,
                )
                return 4

            deleted += 1
            print(f"SUPPRIME ID={article_id}")

        articles_after = get_articles(session, base_url, args.timeout)
        stress_after = [
            article for article in articles_after
            if is_stress_article(article)
        ]
        seeds_after = [
            article for article in articles_after
            if not is_stress_article(article)
        ]

        print(f"ARTICLES_SUPPRIMES={deleted}")
        print(f"ARTICLES_APRES={len(articles_after)}")
        print(f"ARTICLES_STRESS_APRES={len(stress_after)}")
        print(f"ARTICLES_SEED_APRES={len(seeds_after)}")

        if stress_after:
            print(
                "ERREUR: des articles STRESS existent encore.",
                file=sys.stderr,
            )
            return 5

        if len(seeds_after) != args.expected_seed_count:
            print(
                "ERREUR: les articles seed ne correspondent plus "
                "à la référence.",
                file=sys.stderr,
            )
            return 6

        print("VERIFICATION_SEED=OK")
        return 0

    except (requests.RequestException, ValueError) as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
