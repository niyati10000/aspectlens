"""Per-product aspect statistics, monthly sentiment trends, and representative snippet selection.

Implements all aggregation queries specified in DATABASE_SCHEMA.md:
- Per-product aspect summary with mention count, pos %, neg %, neu %, and average score.
- Monthly sentiment trends (grouped by YYYY-MM and aspect).
- Representative top-3 positive and top-3 negative snippets per aspect ordered by confidence.
- Product side-by-side comparison.
- Strict parameterised queries and always displaying mention counts beside percentages.
"""

import json
import sqlite3
from typing import Any


def get_product_aspect_summary(
    conn: sqlite3.Connection,
    product_id: str,
    min_mentions: int = 1,
) -> list[dict[str, Any]]:
    """Compute per-aspect statistics for a given product.

    Returns:
        List of dicts: aspect, canonical_id, mentions, pos_pct, neg_pct, neu_pct, avg_score.
        Always displays mention counts alongside percentages.
        Filters by minimum-mentions threshold.
    """
    query = """
        SELECT ca.name AS aspect,
               ca.id AS canonical_id,
               COUNT(*) AS mentions,
               ROUND(100.0 * SUM(CASE WHEN m.sentiment = 'positive' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pos_pct,
               ROUND(100.0 * SUM(CASE WHEN m.sentiment = 'negative' THEN 1 ELSE 0 END) / COUNT(*), 1) AS neg_pct,
               ROUND(100.0 * SUM(CASE WHEN m.sentiment = 'neutral' THEN 1 ELSE 0 END) / COUNT(*), 1) AS neu_pct,
               ROUND(AVG(m.score), 3) AS avg_score
        FROM aspect_mentions m
        JOIN reviews r ON r.id = m.review_id
        JOIN canonical_aspects ca ON ca.id = m.canonical_id
        WHERE r.product_id = ?
        GROUP BY ca.id
        HAVING mentions >= ?
        ORDER BY mentions DESC, ca.name ASC;
    """
    cursor = conn.execute(query, (product_id, min_mentions))
    rows = cursor.fetchall()

    return [
        {
            "aspect": row["aspect"],
            "canonical_id": row["canonical_id"],
            "mentions": row["mentions"],
            "pos_pct": float(row["pos_pct"] or 0.0),
            "neg_pct": float(row["neg_pct"] or 0.0),
            "neu_pct": float(row["neu_pct"] or 0.0),
            "avg_score": float(row["avg_score"] or 0.0),
        }
        for row in rows
    ]


def get_monthly_trend(
    conn: sqlite3.Connection,
    product_id: str,
    canonical_id: int | None = None,
    min_mentions: int = 1,
) -> list[dict[str, Any]]:
    """Compute monthly sentiment trends for a product, optionally filtered by aspect.

    Groups by calendar month (YYYY-MM) and canonical aspect.
    """
    params: list[Any] = [product_id]
    aspect_clause = ""
    if canonical_id is not None:
        aspect_clause = "AND ca.id = ?"
        params.append(canonical_id)

    params.append(min_mentions)

    query = f"""
        SELECT substr(r.review_date, 1, 7) AS month,
               ca.name AS aspect,
               ca.id AS canonical_id,
               COUNT(*) AS mentions,
               ROUND(100.0 * SUM(CASE WHEN m.sentiment = 'positive' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pos_pct,
               ROUND(100.0 * SUM(CASE WHEN m.sentiment = 'negative' THEN 1 ELSE 0 END) / COUNT(*), 1) AS neg_pct,
               ROUND(AVG(m.score), 3) AS avg_score
        FROM aspect_mentions m
        JOIN reviews r ON r.id = m.review_id
        JOIN canonical_aspects ca ON ca.id = m.canonical_id
        WHERE r.product_id = ?
          AND r.review_date IS NOT NULL
          AND length(r.review_date) >= 7
          {aspect_clause}
        GROUP BY month, ca.id
        HAVING mentions >= ?
        ORDER BY month ASC, mentions DESC;
    """
    cursor = conn.execute(query, tuple(params))
    rows = cursor.fetchall()

    return [
        {
            "month": row["month"],
            "aspect": row["aspect"],
            "canonical_id": row["canonical_id"],
            "mentions": row["mentions"],
            "pos_pct": float(row["pos_pct"] or 0.0),
            "neg_pct": float(row["neg_pct"] or 0.0),
            "avg_score": float(row["avg_score"] or 0.0),
        }
        for row in rows
    ]


def get_representative_snippets(
    conn: sqlite3.Connection,
    product_id: str,
    canonical_id: int,
    limit: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Retrieve top positive and top negative representative snippets for an aspect.

    Ordered by model confidence and absolute polarity score.
    Returns:
        {
            "positive": [...],
            "negative": [...]
        }
    """
    # 1. Top positive snippets
    pos_query = """
        SELECT m.id,
               m.term,
               m.snippet,
               m.confidence,
               m.score,
               m.opinion_words,
               r.id AS review_id,
               r.rating,
               r.review_date
        FROM aspect_mentions m
        JOIN reviews r ON r.id = m.review_id
        WHERE r.product_id = ?
          AND m.canonical_id = ?
          AND m.sentiment = 'positive'
        ORDER BY m.confidence DESC, m.score DESC
        LIMIT ?;
    """
    pos_rows = conn.execute(pos_query, (product_id, canonical_id, limit)).fetchall()

    # 2. Top negative snippets
    neg_query = """
        SELECT m.id,
               m.term,
               m.snippet,
               m.confidence,
               m.score,
               m.opinion_words,
               r.id AS review_id,
               r.rating,
               r.review_date
        FROM aspect_mentions m
        JOIN reviews r ON r.id = m.review_id
        WHERE r.product_id = ?
          AND m.canonical_id = ?
          AND m.sentiment = 'negative'
        ORDER BY m.confidence DESC, m.score ASC
        LIMIT ?;
    """
    neg_rows = conn.execute(neg_query, (product_id, canonical_id, limit)).fetchall()

    def parse_snippet_rows(rows):
        res = []
        for r in rows:
            op_words = r["opinion_words"]
            if isinstance(op_words, str):
                try:
                    op_words = json.loads(op_words)
                except Exception:
                    op_words = [op_words]

            snippet_text = r["snippet"] or r["term"]
            res.append(
                {
                    "id": r["id"],
                    "term": r["term"],
                    "snippet": snippet_text,
                    "confidence": float(r["confidence"]),
                    "score": float(r["score"]),
                    "opinion_words": op_words,
                    "review_id": r["review_id"],
                    "rating": r["rating"],
                    "review_date": r["review_date"],
                }
            )
        return res

    return {
        "positive": parse_snippet_rows(pos_rows),
        "negative": parse_snippet_rows(neg_rows),
    }


def get_product_summary(
    conn: sqlite3.Connection,
    product_id: str,
    min_mentions: int = 1,
) -> dict[str, Any] | None:
    """Assemble complete product summary: product metadata, per-aspect stats, snippets, and monthly trend."""
    # 1. Product details
    cursor = conn.execute(
        "SELECT id, name, category, source, review_count FROM products WHERE id = ?;",
        (product_id,),
    )
    product_row = cursor.fetchone()
    if not product_row:
        return None

    # Count actual reviews in DB
    rev_count_cur = conn.execute(
        "SELECT COUNT(*) FROM reviews WHERE product_id = ?;", (product_id,)
    )
    actual_reviews = rev_count_cur.fetchone()[0]

    # 2. Aspect summaries
    aspect_summaries = get_product_aspect_summary(conn, product_id, min_mentions=min_mentions)

    # 3. Attach snippets to each aspect
    for aspect in aspect_summaries:
        snippets = get_representative_snippets(conn, product_id, aspect["canonical_id"], limit=3)
        aspect["snippets"] = snippets

    # 4. Monthly trend
    trends = get_monthly_trend(conn, product_id, min_mentions=1)

    return {
        "product_id": product_row["id"],
        "name": product_row["name"],
        "category": product_row["category"],
        "source": product_row["source"],
        "review_count": actual_reviews,
        "aspects": aspect_summaries,
        "monthly_trend": trends,
    }


def compare_products(
    conn: sqlite3.Connection,
    product_a_id: str,
    product_b_id: str,
    min_mentions: int = 1,
) -> dict[str, Any]:
    """Perform side-by-side aspect comparison between two products."""
    # Product details
    cur_a = conn.execute(
        "SELECT id, name, category, review_count FROM products WHERE id = ?;", (product_a_id,)
    ).fetchone()
    cur_b = conn.execute(
        "SELECT id, name, category, review_count FROM products WHERE id = ?;", (product_b_id,)
    ).fetchone()

    prod_a_info = (
        dict(cur_a) if cur_a else {"id": product_a_id, "name": product_a_id, "review_count": 0}
    )
    prod_b_info = (
        dict(cur_b) if cur_b else {"id": product_b_id, "name": product_b_id, "review_count": 0}
    )

    # Aspect summaries
    summary_a = {
        a["aspect"]: a for a in get_product_aspect_summary(conn, product_a_id, min_mentions=0)
    }
    summary_b = {
        b["aspect"]: b for b in get_product_aspect_summary(conn, product_b_id, min_mentions=0)
    }

    # Union of all aspects
    all_aspect_names = sorted(list(set(summary_a.keys()) | set(summary_b.keys())))

    compared_aspects = []
    for name in all_aspect_names:
        stats_a = summary_a.get(name)
        stats_b = summary_b.get(name)

        mentions_a = stats_a["mentions"] if stats_a else 0
        mentions_b = stats_b["mentions"] if stats_b else 0

        # Apply min_mentions: at least one product must meet threshold
        if mentions_a < min_mentions and mentions_b < min_mentions:
            continue

        target_stats = stats_a or stats_b
        cid = target_stats["canonical_id"] if target_stats else 0

        a_data = {
            "mentions": mentions_a,
            "pos_pct": stats_a["pos_pct"] if stats_a else 0.0,
            "neg_pct": stats_a["neg_pct"] if stats_a else 0.0,
            "neu_pct": stats_a["neu_pct"] if stats_a else 0.0,
            "avg_score": stats_a["avg_score"] if stats_a else 0.0,
        }

        b_data = {
            "mentions": mentions_b,
            "pos_pct": stats_b["pos_pct"] if stats_b else 0.0,
            "neg_pct": stats_b["neg_pct"] if stats_b else 0.0,
            "neu_pct": stats_b["neu_pct"] if stats_b else 0.0,
            "avg_score": stats_b["avg_score"] if stats_b else 0.0,
        }

        # Determine winner based on avg_score, breaking ties on pos_pct
        if mentions_a == 0:
            winner = "product_b"
        elif mentions_b == 0:
            winner = "product_a"
        elif a_data["avg_score"] > b_data["avg_score"]:
            winner = "product_a"
        elif b_data["avg_score"] > a_data["avg_score"]:
            winner = "product_b"
        elif a_data["pos_pct"] > b_data["pos_pct"]:
            winner = "product_a"
        elif b_data["pos_pct"] > a_data["pos_pct"]:
            winner = "product_b"
        else:
            winner = "tie"

        compared_aspects.append(
            {
                "aspect": name,
                "canonical_id": cid,
                "product_a": a_data,
                "product_b": b_data,
                "winner": winner,
            }
        )

    # Sort by total mentions across both products
    compared_aspects.sort(
        key=lambda x: x["product_a"]["mentions"] + x["product_b"]["mentions"],
        reverse=True,
    )

    return {
        "product_a": prod_a_info,
        "product_b": prod_b_info,
        "aspects": compared_aspects,
    }
