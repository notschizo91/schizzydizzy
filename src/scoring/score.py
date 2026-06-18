import csv
import os
from src.db import get_db


def score_keywords(db_path: str, top_n: int = 100) -> list[dict]:
    conn = get_db(db_path)

    rows = conn.execute(
        """
        SELECT phrase, autocomplete_rank, cross_listing_freq
        FROM keywords
        WHERE autocomplete_rank IS NOT NULL OR cross_listing_freq > 0
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("No keywords to score.")
        return []

    ranks = [r[1] for r in rows if r[1] is not None]
    freqs = [r[2] for r in rows if r[2] is not None]

    min_rank = min(ranks) if ranks else 0
    max_rank = max(ranks) if ranks else 1
    max_freq = max(freqs) if freqs else 1

    rank_range = max_rank - min_rank or 1

    scored = []
    for phrase, autocomplete_rank, cross_listing_freq in rows:
        if autocomplete_rank is not None:
            demand_score = 1 - (autocomplete_rank - min_rank) / rank_range
        else:
            demand_score = 0.0

        validation_score = (cross_listing_freq or 0) / max_freq

        score = 0.6 * demand_score + 0.4 * validation_score
        scored.append({
            "phrase": phrase,
            "score": round(score, 6),
            "autocomplete_rank": autocomplete_rank,
            "cross_listing_freq": cross_listing_freq or 0,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    os.makedirs("data", exist_ok=True)
    with open("data/scored_keywords.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["phrase", "score", "autocomplete_rank", "cross_listing_freq"])
        writer.writeheader()
        writer.writerows(scored)

    top = scored[:top_n]
    col_w = max(len(r["phrase"]) for r in top) + 2 if top else 20
    print(f"{'phrase':<{col_w}} {'score':>8}  {'rank':>6}  {'freq':>6}")
    print("-" * (col_w + 28))
    for r in top:
        rank_str = f"{r['autocomplete_rank']:.2f}" if r["autocomplete_rank"] is not None else "     -"
        print(f"{r['phrase']:<{col_w}} {r['score']:>8.4f}  {rank_str:>6}  {r['cross_listing_freq']:>6}")

    return scored


if __name__ == "__main__":
    score_keywords("data/keywords.db")
