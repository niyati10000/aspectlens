"""Unit tests for SQLite database initialization and summary aggregation queries."""

import pytest
import sqlite3
import json
from pathlib import Path

from app.db import init_db, get_canonical_aspect_id_map
from nlp.aggregate import (
    get_product_aspect_summary,
    get_monthly_trend,
    get_representative_snippets,
    get_product_summary,
    compare_products,
)


@pytest.fixture
def fixture_db() -> sqlite3.Connection:
    """Create a fully seeded, controlled in-memory SQLite database for aggregation testing."""
    conn = init_db(":memory:", seed_if_empty=False)

    with conn:
        # Insert two test products
        conn.execute("""
            INSERT INTO products (id, name, category, source, review_count)
            VALUES 
                ('PROD_PHONE_A', 'Apex Pro Phone', 'Cell Phones', 'test', 5),
                ('PROD_PHONE_B', 'Budget Lite Phone', 'Cell Phones', 'test', 4);
        """)

        # Insert test reviews spanning different months
        reviews_data = [
            # Product A reviews
            ('rev_a1', 'PROD_PHONE_A', 'Battery life is amazing and fast charging.', 5, '2024-01-10', 'positive'),
            ('rev_a2', 'PROD_PHONE_A', 'Great battery, screen is bright and sharp.', 5, '2024-01-20', 'positive'),
            ('rev_a3', 'PROD_PHONE_A', 'Battery died quickly yesterday.', 2, '2024-02-05', 'negative'),
            ('rev_a4', 'PROD_PHONE_A', 'Price is too high for what you get.', 2, '2024-02-15', 'negative'),
            ('rev_a5', 'PROD_PHONE_A', 'Normal phone, battery is okay.', 3, '2024-03-01', 'neutral'),
            # Product B reviews
            ('rev_b1', 'PROD_PHONE_B', 'Affordable price and good screen.', 4, '2024-01-15', 'positive'),
            ('rev_b2', 'PROD_PHONE_B', 'Battery is terrible, screen is okay.', 1, '2024-02-10', 'negative'),
            ('rev_b3', 'PROD_PHONE_B', 'Horrible battery life.', 1, '2024-02-20', 'negative'),
            ('rev_b4', 'PROD_PHONE_B', 'Cheap price, low cost bargain.', 5, '2024-03-05', 'positive'),
        ]
        conn.executemany("""
            INSERT INTO reviews (id, product_id, text_display, rating, review_date, overall_label)
            VALUES (?, ?, ?, ?, ?, ?);
        """, reviews_data)

    canon_map = get_canonical_aspect_id_map(conn)
    battery_id = canon_map["Battery"]
    price_id = canon_map["Price"]
    display_id = canon_map["Display"]

    # Insert aspect mentions with controlled scores, confidences, and snippets
    mentions_data = [
        # Product A mentions:
        # Battery: 3 pos, 1 neg, 1 neu (5 total) -> pos_pct = 60.0%, neg_pct = 20.0%, neu_pct = 20.0%
        ('rev_a1', battery_id, 'Battery life', 0, 12, 'positive', 0.95, 0.90, '["amazing"]', 'vader', 'spacy_chunks', 'Battery life is amazing'),
        ('rev_a1', battery_id, 'charging', 22, 30, 'positive', 0.85, 0.80, '["fast"]', 'vader', 'spacy_chunks', 'fast charging'),
        ('rev_a2', battery_id, 'battery', 6, 13, 'positive', 0.90, 0.85, '["great"]', 'vader', 'spacy_chunks', 'Great battery'),
        ('rev_a3', battery_id, 'Battery', 0, 7, 'negative', 0.88, -0.80, '["died quickly"]', 'vader', 'spacy_chunks', 'Battery died quickly yesterday'),
        ('rev_a5', battery_id, 'battery', 14, 21, 'neutral', 0.50, 0.00, '["okay"]', 'vader', 'spacy_chunks', 'battery is okay'),
        # Display: 1 pos (1 total)
        ('rev_a2', display_id, 'screen', 15, 21, 'positive', 0.92, 0.88, '["bright", "sharp"]', 'vader', 'spacy_chunks', 'screen is bright and sharp'),
        # Price: 1 neg (1 total)
        ('rev_a4', price_id, 'Price', 0, 5, 'negative', 0.89, -0.75, '["too high"]', 'vader', 'spacy_chunks', 'Price is too high'),

        # Product B mentions:
        # Battery: 0 pos, 2 neg (2 total) -> pos_pct = 0.0%, neg_pct = 100.0%
        ('rev_b2', battery_id, 'Battery', 0, 7, 'negative', 0.94, -0.90, '["terrible"]', 'vader', 'spacy_chunks', 'Battery is terrible'),
        ('rev_b3', battery_id, 'battery life', 9, 21, 'negative', 0.96, -0.95, '["horrible"]', 'vader', 'spacy_chunks', 'Horrible battery life'),
        # Price: 2 pos (2 total) -> pos_pct = 100.0%, neg_pct = 0.0%
        ('rev_b1', price_id, 'price', 11, 16, 'positive', 0.86, 0.75, '["affordable"]', 'vader', 'spacy_chunks', 'Affordable price'),
        ('rev_b4', price_id, 'price', 6, 11, 'positive', 0.91, 0.85, '["cheap", "bargain"]', 'vader', 'spacy_chunks', 'Cheap price'),
        # Display: 1 pos (1 total)
        ('rev_b1', display_id, 'screen', 26, 32, 'positive', 0.80, 0.70, '["good"]', 'vader', 'spacy_chunks', 'good screen'),
    ]

    with conn:
        conn.executemany("""
            INSERT INTO aspect_mentions (
                review_id, canonical_id, term, char_start, char_end,
                sentiment, confidence, score, opinion_words, scorer, extractor, snippet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, mentions_data)

    return conn


def test_db_initialization_and_schema():
    """Verify init_db schema constraints, PRAGMA user_version, and foreign keys."""
    conn = init_db(":memory:", seed_if_empty=False)

    # Check user_version
    cur = conn.execute("PRAGMA user_version;")
    assert cur.fetchone()[0] == 1

    # Check foreign keys enabled
    cur = conn.execute("PRAGMA foreign_keys;")
    assert cur.fetchone()[0] == 1

    # Verify tables created
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    assert "products" in tables
    assert "reviews" in tables
    assert "canonical_aspects" in tables
    assert "aspect_aliases" in tables
    assert "aspect_mentions" in tables
    assert "upload_batches" in tables
    assert "evaluation_runs" in tables

    # Verify canonical aspects seeded
    cur = conn.execute("SELECT COUNT(*) FROM canonical_aspects;")
    assert cur.fetchone()[0] >= 11

    # Verify NO user or reviewer personal information column exists in reviews table
    cur = conn.execute("PRAGMA table_info(reviews);")
    columns = {r[1] for r in cur.fetchall()}
    assert "user_id" not in columns
    assert "reviewer_name" not in columns
    assert "email" not in columns


def test_product_aspect_summary(fixture_db):
    """Test get_product_aspect_summary for accurate mention count, percentages, and avg_score."""
    summary = get_product_aspect_summary(fixture_db, "PROD_PHONE_A", min_mentions=1)
    assert len(summary) == 3

    by_aspect = {s["aspect"]: s for s in summary}

    # Battery for PROD_PHONE_A: 5 mentions (3 pos, 1 neg, 1 neu)
    assert "Battery" in by_aspect
    bat = by_aspect["Battery"]
    assert bat["mentions"] == 5
    assert bat["pos_pct"] == 60.0
    assert bat["neg_pct"] == 20.0
    assert bat["neu_pct"] == 20.0
    assert round(bat["pos_pct"] + bat["neg_pct"] + bat["neu_pct"], 1) == 100.0
    assert bat["avg_score"] > 0.0

    # Display for PROD_PHONE_A: 1 mention (100% pos)
    assert "Display" in by_aspect
    disp = by_aspect["Display"]
    assert disp["mentions"] == 1
    assert disp["pos_pct"] == 100.0
    assert disp["neg_pct"] == 0.0

    # Price for PROD_PHONE_A: 1 mention (100% neg)
    assert "Price" in by_aspect
    pr = by_aspect["Price"]
    assert pr["mentions"] == 1
    assert pr["pos_pct"] == 0.0
    assert pr["neg_pct"] == 100.0


def test_summary_min_mentions_threshold(fixture_db):
    """Verify that min_mentions threshold filters out low-frequency aspects."""
    # When min_mentions=2, Display (1) and Price (1) should be filtered out
    summary = get_product_aspect_summary(fixture_db, "PROD_PHONE_A", min_mentions=2)
    assert len(summary) == 1
    assert summary[0]["aspect"] == "Battery"
    assert summary[0]["mentions"] == 5


def test_monthly_trend_aggregation(fixture_db):
    """Test get_monthly_trend aggregates by month (YYYY-MM) in chronological order."""
    trend = get_monthly_trend(fixture_db, "PROD_PHONE_A")
    assert len(trend) > 0

    months = [t["month"] for t in trend]
    assert months == sorted(months)  # Chronological ordering

    # Check January 2024 for Battery
    jan_battery = next((t for t in trend if t["month"] == "2024-01" and t["aspect"] == "Battery"), None)
    assert jan_battery is not None
    assert jan_battery["mentions"] == 3
    assert jan_battery["pos_pct"] == 100.0

    # Check February 2024 for Battery
    feb_battery = next((t for t in trend if t["month"] == "2024-02" and t["aspect"] == "Battery"), None)
    assert feb_battery is not None
    assert feb_battery["mentions"] == 1
    assert feb_battery["neg_pct"] == 100.0


def test_representative_snippets_selection(fixture_db):
    """Test get_representative_snippets returns top positive and negative snippets ordered by confidence."""
    canon_map = get_canonical_aspect_id_map(fixture_db)
    bat_id = canon_map["Battery"]

    snippets = get_representative_snippets(fixture_db, "PROD_PHONE_A", bat_id, limit=3)
    assert "positive" in snippets
    assert "negative" in snippets

    pos = snippets["positive"]
    neg = snippets["negative"]

    # 3 positive snippets exist for Battery in PROD_PHONE_A
    assert len(pos) == 3
    # Top positive snippet should have the highest confidence (0.95: 'Battery life is amazing')
    assert pos[0]["confidence"] == 0.95
    assert pos[0]["snippet"] == "Battery life is amazing"
    assert pos[0]["rating"] == 5

    # 1 negative snippet exists for Battery in PROD_PHONE_A
    assert len(neg) == 1
    assert neg[0]["snippet"] == "Battery died quickly yesterday"
    assert neg[0]["confidence"] == 0.88


def test_get_product_summary(fixture_db):
    """Test get_product_summary bundles product details, aspect stats, snippets, and trends."""
    summary = get_product_summary(fixture_db, "PROD_PHONE_A", min_mentions=1)
    assert summary is not None
    assert summary["product_id"] == "PROD_PHONE_A"
    assert summary["name"] == "Apex Pro Phone"
    assert summary["review_count"] == 5
    assert len(summary["aspects"]) == 3

    # Check that snippets are embedded in each aspect summary
    bat_aspect = next(a for a in summary["aspects"] if a["aspect"] == "Battery")
    assert "snippets" in bat_aspect
    assert len(bat_aspect["snippets"]["positive"]) > 0

    # Test non-existent product
    assert get_product_summary(fixture_db, "NON_EXISTENT") is None


def test_compare_products(fixture_db):
    """Test compare_products side-by-side aspect comparison and winner determination."""
    comparison = compare_products(fixture_db, "PROD_PHONE_A", "PROD_PHONE_B", min_mentions=1)

    assert comparison["product_a"]["id"] == "PROD_PHONE_A"
    assert comparison["product_b"]["id"] == "PROD_PHONE_B"

    aspects = {a["aspect"]: a for a in comparison["aspects"]}

    # Battery: PROD_PHONE_A (60% pos, avg 0.35) vs PROD_PHONE_B (0% pos, avg -0.925) -> Winner A
    assert "Battery" in aspects
    bat = aspects["Battery"]
    assert bat["product_a"]["mentions"] == 5
    assert bat["product_b"]["mentions"] == 2
    assert bat["winner"] == "product_a"

    # Price: PROD_PHONE_A (0% pos, 100% neg) vs PROD_PHONE_B (100% pos, 0% neg) -> Winner B
    assert "Price" in aspects
    pr = aspects["Price"]
    assert pr["product_a"]["mentions"] == 1
    assert pr["product_b"]["mentions"] == 2
    assert pr["winner"] == "product_b"


def test_parameterized_query_safety(fixture_db):
    """Verify SQL injection safety with malicious inputs."""
    malicious_id = "PROD_PHONE_A' OR '1'='1"
    summary = get_product_aspect_summary(fixture_db, malicious_id)
    assert len(summary) == 0

    comparison = compare_products(fixture_db, malicious_id, "PROD_PHONE_B")
    assert len(comparison["aspects"]) > 0
    assert comparison["product_a"]["id"] == malicious_id
    assert comparison["product_a"]["review_count"] == 0
