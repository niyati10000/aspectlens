"""SQLite database connectivity, schema initialization, and querying for AspectLens.

Follows DATABASE_SCHEMA.md strictly:
- Engine: SQLite with PRAGMA foreign_keys = ON and PRAGMA user_version = 1.
- Parameterised queries only (no string-built SQL).
- Deliberately no users table and no reviewer personal information stored.
- Auto-seeds canonical aspects and demo reviews if database is empty.
"""

from typing import Optional, List, Dict, Any, Generator, Tuple
from pathlib import Path
from contextlib import contextmanager
import sqlite3
import json
import logging
from datetime import datetime

from app.config import settings
from nlp.preprocess import clean_text

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with foreign keys and dict-like row access."""
    target_path = db_path or settings.DB_PATH
    if isinstance(target_path, Path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target_path))
    else:
        conn = sqlite3.connect(str(target_path))

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite database transactions."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(
    db_path: Optional[Path] = None,
    seed_if_empty: bool = True,
    demo_sample_path: Optional[Path] = None,
    seed_lexicon_path: Optional[Path] = None,
) -> sqlite3.Connection:
    """Initialize SQLite database tables, indexes, and seed canonical aspects and demo reviews."""
    conn = get_connection(db_path)

    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # Check existing schema version
        cursor = conn.execute("PRAGMA user_version;")
        current_version = cursor.fetchone()[0]

        # -------------------------------------------------------------
        # 1. Create Tables
        # -------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                source TEXT,
                review_count INTEGER DEFAULT 0
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS upload_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                filename TEXT,
                row_count INTEGER DEFAULT 0,
                status TEXT CHECK (status IN ('processing', 'done', 'failed'))
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES products(id),
                batch_id INTEGER REFERENCES upload_batches(id),
                text_display TEXT NOT NULL,
                rating INTEGER,
                review_date TEXT,
                overall_label TEXT,
                processed_at TEXT
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS canonical_aspects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                domain TEXT
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS aspect_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_id INTEGER NOT NULL REFERENCES canonical_aspects(id) ON DELETE CASCADE,
                alias TEXT NOT NULL,
                origin TEXT CHECK (origin IN ('seed', 'wordnet', 'embedding')),
                UNIQUE(canonical_id, alias)
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS aspect_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
                canonical_id INTEGER NOT NULL REFERENCES canonical_aspects(id) ON DELETE CASCADE,
                term TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                sentiment TEXT NOT NULL CHECK (sentiment IN ('positive', 'negative', 'neutral')),
                confidence REAL NOT NULL,
                score REAL NOT NULL,
                opinion_words TEXT NOT NULL,
                scorer TEXT NOT NULL,
                extractor TEXT NOT NULL,
                snippet TEXT
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                name TEXT NOT NULL,
                result_path TEXT NOT NULL
            );
        """)

        # -------------------------------------------------------------
        # 2. Create Indexes
        # -------------------------------------------------------------
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_date ON reviews(review_date);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_review ON aspect_mentions(review_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_aspect ON aspect_mentions(canonical_id, sentiment);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_canonical ON aspect_mentions(canonical_id);")

        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")

    # -----------------------------------------------------------------
    # 3. Seed Canonical Aspects from seed_lexicon.json
    # -----------------------------------------------------------------
    _seed_canonical_aspects(conn, seed_lexicon_path or settings.SEED_LEXICON_PATH)

    # -----------------------------------------------------------------
    # 4. Seed Demo Reviews if reviews table is empty
    # -----------------------------------------------------------------
    if seed_if_empty:
        _seed_demo_reviews_if_empty(conn, demo_sample_path or settings.DEMO_SAMPLE_PATH)

    return conn


def _seed_canonical_aspects(conn: sqlite3.Connection, lexicon_path: Path) -> None:
    """Populate canonical_aspects and aspect_aliases from seed_lexicon.json if empty."""
    cursor = conn.execute("SELECT COUNT(*) FROM canonical_aspects;")
    if cursor.fetchone()[0] > 0:
        return

    if not lexicon_path.exists():
        logger.warning("Seed lexicon file not found at: %s", lexicon_path)
        return

    with open(lexicon_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    canonical_aspects = data.get("canonical_aspects", {})

    with conn:
        for name, info in canonical_aspects.items():
            domain = info.get("domain", "general")
            cursor = conn.execute(
                "INSERT OR IGNORE INTO canonical_aspects (name, domain) VALUES (?, ?);",
                (name, domain),
            )
            canon_id = cursor.lastrowid
            if not canon_id or canon_id == 0:
                c = conn.execute("SELECT id FROM canonical_aspects WHERE name = ?;", (name,))
                canon_id = c.fetchone()[0]

            keywords = info.get("keywords", [])
            for kw in keywords:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO aspect_aliases (canonical_id, alias, origin)
                    VALUES (?, ?, ?);
                    """,
                    (canon_id, kw.strip().lower(), "seed"),
                )


def _seed_demo_reviews_if_empty(conn: sqlite3.Connection, demo_path: Path) -> None:
    """Populate products and reviews from demo_sample.json if the reviews table is empty."""
    cursor = conn.execute("SELECT COUNT(*) FROM reviews;")
    if cursor.fetchone()[0] > 0:
        return

    if not demo_path.exists():
        logger.warning("Demo sample file not found at: %s", demo_path)
        return

    logger.info("Seeding database from demo sample: %s", demo_path)
    with open(demo_path, "r", encoding="utf-8") as f:
        demo_reviews = json.load(f)

    # 1. Group reviews by product
    products_map: Dict[str, Dict[str, Any]] = {}
    for r in demo_reviews:
        pid = r["product_id"]
        if pid not in products_map:
            products_map[pid] = {
                "id": pid,
                "name": r.get("product_name") or f"Product {pid}",
                "category": r.get("category", "Electronics"),
                "source": "amazon",
                "count": 0,
            }
        products_map[pid]["count"] += 1

    with conn:
        # 2. Insert Products
        for p in products_map.values():
            conn.execute(
                """
                INSERT OR REPLACE INTO products (id, name, category, source, review_count)
                VALUES (?, ?, ?, ?, ?);
                """,
                (p["id"], p["name"], p["category"], p["source"], p["count"]),
            )

        # 3. Insert Reviews with PII stripped and rating-based overall label
        review_records = []
        for r in demo_reviews:
            raw_text = r.get("text", "")
            cleaned = clean_text(raw_text)
            rating = r.get("rating")
            
            # Overall whole-review sentiment label for comparison
            overall = "neutral"
            if rating is not None:
                if rating >= 4:
                    overall = "positive"
                elif rating <= 2:
                    overall = "negative"

            review_records.append((
                r["review_id"],
                r["product_id"],
                None,  # batch_id null for seeded demo
                cleaned,
                rating,
                r.get("date"),
                overall,
                None,  # processed_at
            ))

        conn.executemany(
            """
            INSERT OR IGNORE INTO reviews (
                id, product_id, batch_id, text_display, rating, review_date, overall_label, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            review_records,
        )

    logger.info("Seeded %d products and %d reviews.", len(products_map), len(review_records))


def get_canonical_aspect_id_map(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return dictionary mapping canonical aspect names to database IDs."""
    cursor = conn.execute("SELECT id, name FROM canonical_aspects;")
    return {row["name"]: row["id"] for row in cursor.fetchall()}
