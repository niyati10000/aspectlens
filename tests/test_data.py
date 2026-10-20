"""Unit tests for dataset loading and schema verification."""

import pytest
from pathlib import Path
from data.scripts.build_demo_sample import load_demo_sample
from data.scripts.download_semeval import load_semeval
from nlp.preprocess import strip_pii, clean_text


def test_demo_sample_exists_and_valid():
    """Verify demo_sample.json exists, is < 20 MB, and conforms to common schema."""
    demo_path = Path("data/demo_sample.json")
    assert demo_path.exists(), "demo_sample.json does not exist!"
    size_mb = demo_path.stat().st_size / (1024 * 1024)
    assert size_mb < 20.0, f"demo_sample.json size ({size_mb:.2f} MB) exceeds 20 MB!"

    reviews = load_demo_sample()
    assert len(reviews) >= 1000, f"Expected >= 1000 reviews, got {len(reviews)}"

    # Check schema on sample
    required_keys = {"review_id", "product_id", "text", "rating", "date"}
    for r in reviews[:50]:
        assert required_keys.issubset(r.keys()), f"Missing keys in review: {r}"
        assert isinstance(r["review_id"], str)
        assert isinstance(r["product_id"], str)
        assert isinstance(r["text"], str) and len(r["text"]) > 0
        assert 1 <= r["rating"] <= 5
        assert len(r["date"]) == 10  # YYYY-MM-DD


def test_semeval_loader_and_schema():
    """Verify SemEval dataset loading and ground truth aspect annotations."""
    semeval_path = Path("data/processed_semeval.json")
    assert semeval_path.exists(), "processed_semeval.json does not exist!"

    laptops_test = load_semeval(split="test", domain="laptop")
    assert len(laptops_test) == 800, f"Expected 800 laptop test sentences, got {len(laptops_test)}"

    restaurants_train = load_semeval(split="train", domain="restaurant")
    assert len(restaurants_train) == 3041, f"Expected 3041 restaurant train sentences, got {len(restaurants_train)}"

    # Check aspect terms structure
    sample = [r for r in laptops_test if len(r.get("aspect_terms", [])) > 0][0]
    aspect = sample["aspect_terms"][0]
    assert "term" in aspect
    assert "polarity" in aspect
    assert "from" in aspect and "to" in aspect


def test_pii_stripping():
    """Verify PII stripping removes emails, phones, and HTML tags."""
    raw = "Contact support@example.com or call 555-123-4567. <b>Great battery</b>!"
    cleaned = strip_pii(raw)
    assert "support@example.com" not in cleaned
    assert "[EMAIL]" in cleaned
    assert "555-123-4567" not in cleaned
    assert "[PHONE]" in cleaned
    assert "<b>" not in cleaned
    assert "Great battery" in cleaned
