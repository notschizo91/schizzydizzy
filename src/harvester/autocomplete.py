import random
import string
import time
from datetime import datetime

import httpx

from src.db import get_db

# AUTOCOMPLETE_STUB: capture the request from your browser's Network tab
# (filter for "completion" or "suggest"), copy as cURL, then wire _fetch_suggestions below.

SEEDS = [
    "personalized keychain",
    "custom keychain",
    "name keychain",
    "keychain",
    "name magnet",
]

MODIFIER_STEMS = [
    "for", "with", "custom", "personalized", "monogram",
    "engraved", "initial", "kids", "men", "women", "gift",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def _fetch_suggestions(query: str, client: httpx.Client) -> list[dict]:
    """
    STUB — wire this once the user pastes the captured cURL from their browser.
    Returns: list of {"suggestion": str, "rank": int}
    """
    raise NotImplementedError(
        "Paste the cURL from your browser network tab and wire this function. "
        "See AUTOCOMPLETE_STUB note in this file."
    )


def _expand_queries(seeds: list[str]) -> list[str]:
    queries = []
    for seed in seeds:
        for letter in string.ascii_lowercase:
            queries.append(f"{seed} {letter}")
        for stem in MODIFIER_STEMS:
            queries.append(f"{seed} {stem}")
    return queries


def _upsert_keyword(conn, phrase: str, rank: int, now: str):
    conn.execute(
        """
        INSERT INTO keywords (phrase, source, autocomplete_rank, first_seen, updated)
        VALUES (?, 'autocomplete', ?, ?, ?)
        ON CONFLICT(phrase) DO UPDATE SET
            autocomplete_rank = (autocomplete_rank + excluded.autocomplete_rank) / 2,
            source = 'autocomplete',
            updated = excluded.updated
        """,
        (phrase, rank, now, now),
    )


def harvest(db_path: str, seeds: list[str] = None, max_depth: int = 2):
    if seeds is None:
        seeds = SEEDS

    conn = get_db(db_path)
    queries = _expand_queries(seeds)
    total = len(queries)
    print(f"Harvesting {total} queries from {len(seeds)} seeds")

    with httpx.Client(headers={"Accept-Encoding": "gzip"}) as client:
        for i, query in enumerate(queries):
            client.headers["User-Agent"] = random.choice(USER_AGENTS)
            print(f"[{i+1}/{total}] {query}")
            try:
                suggestions = _fetch_suggestions(query, client)
            except NotImplementedError as e:
                print(f"  STUB: {e}")
                break
            except Exception as e:
                print(f"  ERROR: {e}")
                time.sleep(random.uniform(0.5, 2.0))
                continue

            now = datetime.utcnow().isoformat()
            for item in suggestions:
                _upsert_keyword(conn, item["suggestion"], item["rank"], now)

            conn.commit()
            time.sleep(random.uniform(0.5, 2.0))

    conn.close()
    print("Done.")


if __name__ == "__main__":
    harvest("data/keywords.db")
