"""Tests for the Phase 9 Evaluation framework and benchmark metrics."""

import csv
import json
from pathlib import Path

from eval.error_analysis import categorize_error
from eval.extraction_eval import compute_prf, evaluate_extraction_lists, evaluate_overlap_lists
from eval.sentiment_eval import evaluate_scorer_on_instances
from nlp.sentiment import VADERScorer

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "eval" / "results"


def test_compute_prf_metrics():
    """Verify standard Precision, Recall, and F1 calculations and edge cases."""
    p, r, f1 = compute_prf(tp=10, fp=5, fn=10)
    assert p == round(10 / 15, 4)
    assert r == round(10 / 20, 4)
    assert f1 == round(2 * p * r / (p + r), 4)

    # Zero division edge cases
    p_zero, r_zero, f1_zero = compute_prf(tp=0, fp=0, fn=0)
    assert p_zero == 0.0 and r_zero == 0.0 and f1_zero == 0.0


def test_evaluate_extraction_exact_and_overlap():
    """Test exact and token-overlap evaluation matching."""
    golds = [["battery life", "touchscreen"], ["cord"]]
    preds = [["battery life", "screen"], ["power cord"]]

    # Exact match
    res_exact = evaluate_extraction_lists(preds, golds)
    assert res_exact["tp"] == 1  # "battery life" matches exactly
    assert res_exact["fp"] == 2  # "screen", "power cord"
    assert res_exact["fn"] == 2  # "touchscreen", "cord"

    # Overlap match
    res_overlap = evaluate_overlap_lists(preds, golds)
    assert res_overlap["f1_overlap"] > res_exact["f1"]
    # "power cord" overlaps with "cord"


def test_categorize_error_modes():
    """Verify linguistic error categorization for all 6 failure modes."""
    # 1. Comparison
    cat1, _ = categorize_error(
        sentence="The screen is much better than Dell laptops.",
        clause="The screen is much better than Dell laptops",
        aspect="screen",
        gold="positive",
        pred="negative",
        other_aspects_in_sentence=["screen"],
    )
    assert cat1 == "comparison"

    # 2. Sarcasm
    cat2, _ = categorize_error(
        sentence="Great job Apple, the battery died in two days!",
        clause="Great job Apple",
        aspect="battery",
        gold="negative",
        pred="positive",
        other_aspects_in_sentence=["battery"],
    )
    assert cat2 == "sarcasm"

    # 3. Negation
    cat3, _ = categorize_error(
        sentence="I do not like the noisy fan.",
        clause="I do not like the noisy fan",
        aspect="fan",
        gold="negative",
        pred="positive",
        other_aspects_in_sentence=["fan"],
    )
    assert cat3 == "negation"

    # 4. Multi-aspect clause
    cat4, _ = categorize_error(
        sentence="The battery is awesome and the keyboard is horrible.",
        clause="The battery is awesome and the keyboard is horrible",
        aspect="battery",
        gold="positive",
        pred="negative",
        other_aspects_in_sentence=["battery", "keyboard"],
    )
    assert cat4 == "multi-aspect clause"

    # 5. Implicit aspect
    cat5, _ = categorize_error(
        sentence="It fits in my pocket easily.",
        clause="",
        aspect="it",
        gold="positive",
        pred="neutral",
        other_aspects_in_sentence=["it"],
    )
    assert cat5 == "implicit aspect"

    # 6. Other (e.g. neutral fact classified as positive, or polarity mismatch without explicit markers)
    cat6, _ = categorize_error(
        sentence="The laptop has Windows 8 installed.",
        clause="The laptop has Windows 8 installed",
        aspect="Windows 8",
        gold="neutral",
        pred="positive",
        other_aspects_in_sentence=["Windows 8"],
    )
    assert cat6 == "other"


def test_scorer_evaluation_on_mock_instances():
    """Test evaluate_scorer_on_instances function."""
    vader = VADERScorer()
    instances = [
        {
            "clause": "Battery life is amazing",
            "aspect": "Battery life",
            "opinion_words": ["amazing"],
            "gold_polarity": "positive",
        },
        {
            "clause": "Delivery was terrible and slow",
            "aspect": "Delivery",
            "opinion_words": ["terrible", "slow"],
            "gold_polarity": "negative",
        },
        {
            "clause": "The case is plastic",
            "aspect": "case",
            "opinion_words": [],
            "gold_polarity": "neutral",
        },
    ]

    res = evaluate_scorer_on_instances(vader, instances)
    assert res["scorer"] == "vader"
    assert res["total_instances"] == 3
    assert 0.0 <= res["accuracy"] <= 1.0
    assert 0.0 <= res["macro_f1"] <= 1.0
    assert "positive" in res["per_class"]
    assert "negative" in res["per_class"]
    assert "neutral" in res["per_class"]


def test_persisted_benchmark_artifacts_exist():
    """Verify that all 7 JSON and 6 CSV benchmark result files exist on disk."""
    expected_jsons = [
        "extraction_ablation.json",
        "sentiment_benchmark.json",
        "baseline_comparison.json",
        "amazon_mixed_sentiment.json",
        "latency_benchmark.json",
        "error_analysis.json",
        "summary_metrics.json",
    ]
    for jf in expected_jsons:
        p = RESULTS_DIR / jf
        assert p.exists(), f"Missing expected JSON artifact: {jf}"
        assert p.stat().st_size > 0

    expected_csvs = [
        "extraction_ablation.csv",
        "sentiment_benchmark.csv",
        "baseline_comparison.csv",
        "amazon_mixed_sentiment.csv",
        "latency_benchmark.csv",
        "error_analysis.csv",
    ]
    for cf in expected_csvs:
        p = RESULTS_DIR / cf
        assert p.exists(), f"Missing expected CSV artifact: {cf}"
        assert p.stat().st_size > 0

        # Validate CSV is parseable
        with open(p, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) >= 2, f"CSV {cf} should have header and at least one data row"


def test_summary_metrics_structure():
    """Validate summary_metrics.json contains all required KPI fields."""
    summary_path = RESULTS_DIR / "summary_metrics.json"
    with open(summary_path, encoding="utf-8") as f:
        data = json.load(f)

    assert "generated_at" in data
    assert "aspect_extraction" in data
    assert "aspect_sentiment" in data
    assert "amazon_value" in data
    assert "system_performance" in data
    assert "error_analysis" in data

    assert data["aspect_sentiment"]["winner"] in ("vader", "transformer")
    assert 0.0 <= data["amazon_value"]["high_star_with_negative_aspect_pct"] <= 100.0
    assert 0.0 <= data["amazon_value"]["low_star_with_positive_aspect_pct"] <= 100.0
