import string
from datetime import datetime

from src.db import get_db
from src.transport import client_session, throttled_get

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

_AUTOCOMPLETE_URL = "https://www.amazon.com/suggestions"
_AUTOCOMPLETE_PARAMS = {
    "alias": "aps",
    "suggestion-type": "KEYWORD",
    "page-type": "Gateway",
    "site-variant": "desktop",
    "version": "3",
    "lop": "en_US",
    "mid": "ATVPDKIKX0DER",
    "limit": "11",
}
_AUTOCOMPLETE_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
}


def _fetch_suggestions(query: str, client) -> list[dict]:
    """Returns list of {"suggestion": str, "rank": int} (rank 0 = top)."""
    params = {**_AUTOCOMPLETE_PARAMS, "prefix": query}
    resp = throttled_get(client, _AUTOCOMPLETE_URL, params=params, extra_headers=_AUTOCOMPLETE_HEADERS)
    data = resp.json()
    results = []
    for rank, item in enumerate(data.get("suggestions", [])):
        value = item.get("value", "").strip()
        if value:
            results.append({"suggestion": value, "rank": rank})
    return results


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


def harvest(db_path: str, seeds: list[str] = None):
    if seeds is None:
        seeds = SEEDS

    conn = get_db(db_path)
    queries = _expand_queries(seeds)
    total = len(queries)
    print(f"Harvesting {total} queries from {len(seeds)} seeds")

    with client_session(sticky=False) as client:
        for i, query in enumerate(queries):
            print(f"[{i+1}/{total}] {query}")
            try:
                suggestions = _fetch_suggestions(query, client)
            except Exception as e:
                print(f"  ERROR: {e}")
                continue

            now = datetime.utcnow().isoformat()
            for item in suggestions:
                _upsert_keyword(conn, item["suggestion"], item["rank"], now)
            conn.commit()

    conn.close()
    print("Done.")


if __name__ == "__main__":
    harvest("data/keywords.db")
