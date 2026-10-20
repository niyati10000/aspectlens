"""Process demo reviews through the ABSA pipeline and store extracted aspect mentions in SQLite."""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.db import get_canonical_aspect_id_map, get_connection, init_db
from nlp.pipeline import analyze_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def process_reviews(
    db_path: Path,
    limit: int = 500,
    scorer: str = "vader",
    extractor: str = "spacy_chunks",
    reprocess: bool = False,
) -> None:
    """Run pipeline over reviews in SQLite and persist aspect mentions."""
    logger.info("Initializing database: %s", db_path)
    init_db(db_path=db_path, seed_if_empty=True)

    conn = get_connection(db_path)
    canon_map = get_canonical_aspect_id_map(conn)

    # Fetch reviews to process
    if reprocess:
        query = "SELECT id, product_id, text_display FROM reviews ORDER BY id"
    else:
        query = "SELECT id, product_id, text_display FROM reviews WHERE processed_at IS NULL ORDER BY id"

    if limit > 0:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query)
    reviews_to_process = cursor.fetchall()

    logger.info(
        "Found %d reviews to process (scorer=%s, extractor=%s).",
        len(reviews_to_process),
        scorer,
        extractor,
    )
    if not reviews_to_process:
        print("No unprocessed reviews found.")
        return

    processed_count = 0
    total_mentions = 0
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}

    # Process in batches for efficient DB writes
    for i, row in enumerate(reviews_to_process, 1):
        r_id = row["id"]
        text = row["text_display"]

        # Run pipeline
        analysis = analyze_review(text, scorer=scorer, extractor=extractor)
        aspects = analysis.get("aspects", [])

        now_iso = datetime.now(UTC).isoformat()

        with conn:
            # Delete existing mentions for this review if reprocessing
            if reprocess:
                conn.execute("DELETE FROM aspect_mentions WHERE review_id = ?;", (r_id,))

            for a in aspects:
                canonical_name = a["canonical"]
                canonical_id = canon_map.get(canonical_name)
                if not canonical_id:
                    # Dynamically insert canonical aspect if newly encountered
                    c_cur = conn.execute(
                        "INSERT OR IGNORE INTO canonical_aspects (name, domain) VALUES (?, ?);",
                        (canonical_name, "general"),
                    )
                    canonical_id = c_cur.lastrowid
                    if not canonical_id:
                        c_fetch = conn.execute(
                            "SELECT id FROM canonical_aspects WHERE name = ?;", (canonical_name,)
                        )
                        canonical_id = c_fetch.fetchone()[0]
                    canon_map[canonical_name] = canonical_id

                sent = a["sentiment"]
                sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1

                # Calculate continuous polarity score
                conf = float(a["confidence"])
                if sent == "positive":
                    score = conf
                elif sent == "negative":
                    score = -conf
                else:
                    score = 0.0

                snippet = (
                    a.get("snippet")
                    or text[max(0, a["start"] - 30) : min(len(text), a["end"] + 30)].strip()
                )

                conn.execute(
                    """
                    INSERT INTO aspect_mentions (
                        review_id, canonical_id, term, char_start, char_end,
                        sentiment, confidence, score, opinion_words, scorer, extractor, snippet
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        r_id,
                        canonical_id,
                        a["term"],
                        a["start"],
                        a["end"],
                        sent,
                        conf,
                        score,
                        json.dumps(a["opinion_words"]),
                        scorer,
                        extractor,
                        snippet,
                    ),
                )
                total_mentions += 1

            conn.execute(
                "UPDATE reviews SET processed_at = ? WHERE id = ?;",
                (now_iso, r_id),
            )

        processed_count += 1
        if i % 100 == 0 or i == len(reviews_to_process):
            logger.info(
                "Processed %d / %d reviews (%d mentions stored)...",
                i,
                len(reviews_to_process),
                total_mentions,
            )

    # Update denormalized review counts on products
    with conn:
        conn.execute("""
            UPDATE products
            SET review_count = (
                SELECT COUNT(*) FROM reviews WHERE reviews.product_id = products.id
            );
        """)

    print("\n" + "=" * 50)
    print("ASPECTLENS DEMO PROCESSING REPORT")
    print("=" * 50)
    print(f"Reviews processed:     {processed_count}")
    print(f"Aspect mentions stored: {total_mentions}")
    print(
        f"Sentiment breakdown:   Positive: {sentiment_counts['positive']} ({sentiment_counts['positive'] / max(1, total_mentions):.1%})"
    )
    print(
        f"                       Negative: {sentiment_counts['negative']} ({sentiment_counts['negative'] / max(1, total_mentions):.1%})"
    )
    print(
        f"                       Neutral:  {sentiment_counts['neutral']} ({sentiment_counts['neutral'] / max(1, total_mentions):.1%})"
    )

    # Top aspects query
    top_aspects = conn.execute("""
        SELECT ca.name, COUNT(*) AS cnt
        FROM aspect_mentions m
        JOIN canonical_aspects ca ON ca.id = m.canonical_id
        GROUP BY ca.id
        ORDER BY cnt DESC
        LIMIT 10;
    """).fetchall()

    print("\nTop 10 Aspects Mentioned:")
    for row in top_aspects:
        print(f"  {row['name']:<18}: {row['cnt']} mentions")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process demo reviews through AspectLens pipeline")
    parser.add_argument(
        "--limit", type=int, default=500, help="Number of reviews to process (0 for all)"
    )
    parser.add_argument(
        "--scorer", type=str, default="vader", help="Sentiment scorer (vader or transformer)"
    )
    parser.add_argument(
        "--extractor", type=str, default="spacy_chunks", help="Aspect extractor method"
    )
    parser.add_argument(
        "--reprocess", action="store_true", help="Reprocess already processed reviews"
    )
    parser.add_argument(
        "--db-path", type=str, default=str(settings.DB_PATH), help="Target SQLite database path"
    )

    args = parser.parse_args()
    process_reviews(
        db_path=Path(args.db_path),
        limit=args.limit,
        scorer=args.scorer,
        extractor=args.extractor,
        reprocess=args.reprocess,
    )
