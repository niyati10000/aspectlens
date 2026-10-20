"""Unit and golden tests for opinion linking, sentiment scorers, and end-to-end pipeline."""

import pytest
from nlp.pipeline import analyze_review, analyze_batch
from nlp.sentiment import get_scorer, VADERScorer, TransformerScorer, FineTunedScorer, ScoreResult
from nlp.opinions import split_into_clauses, extract_opinions_for_aspect
from nlp.aspects import get_spacy_model


GOLDEN_REVIEW = "Battery life is amazing, but the delivery was late and the price is too high."


def test_golden_review_vader():
    """Acceptance Test (VADER):
    'Battery life is amazing, but the delivery was late and the price is too high.'
    returns:
    - Battery -> positive (amazing), start=0, end=12
    - Delivery -> negative (late), start=33, end=41
    - Price -> negative (too high), start=59, end=64
    """
    result = analyze_review(GOLDEN_REVIEW, scorer="vader")

    assert result["text"] == GOLDEN_REVIEW
    assert result["scorer"] == "vader"
    assert len(result["aspects"]) == 3

    aspects_by_canon = {a["canonical"]: a for a in result["aspects"]}

    # 1. Battery life
    assert "Battery" in aspects_by_canon
    bat = aspects_by_canon["Battery"]
    assert bat["term"] == "Battery life"
    assert bat["start"] == 0
    assert bat["end"] == 12
    assert GOLDEN_REVIEW[bat["start"]:bat["end"]] == "Battery life"
    assert bat["sentiment"] == "positive"
    assert "amazing" in bat["opinion_words"]

    # 2. Delivery
    assert "Delivery" in aspects_by_canon
    deliv = aspects_by_canon["Delivery"]
    assert deliv["term"] == "delivery"
    assert deliv["start"] == 33
    assert deliv["end"] == 41
    assert GOLDEN_REVIEW[deliv["start"]:deliv["end"]] == "delivery"
    assert deliv["sentiment"] == "negative"
    assert "late" in deliv["opinion_words"]

    # 3. Price
    assert "Price" in aspects_by_canon
    pr = aspects_by_canon["Price"]
    assert pr["term"] == "price"
    assert pr["start"] == 59
    assert pr["end"] == 64
    assert GOLDEN_REVIEW[pr["start"]:pr["end"]] == "price"
    assert pr["sentiment"] == "negative"
    assert any("high" in op for op in pr["opinion_words"])


def test_golden_review_transformer():
    """Acceptance Test (Transformer):
    'Battery life is amazing, but the delivery was late and the price is too high.'
    returns:
    - Battery -> positive (amazing), start=0, end=12
    - Delivery -> negative (late), start=33, end=41
    - Price -> negative (too high), start=59, end=64
    """
    result = analyze_review(GOLDEN_REVIEW, scorer="transformer")

    assert result["text"] == GOLDEN_REVIEW
    assert result["scorer"] == "transformer"
    assert len(result["aspects"]) == 3

    aspects_by_canon = {a["canonical"]: a for a in result["aspects"]}

    # 1. Battery life
    assert "Battery" in aspects_by_canon
    bat = aspects_by_canon["Battery"]
    assert bat["term"] == "Battery life"
    assert bat["start"] == 0
    assert bat["end"] == 12
    assert bat["sentiment"] == "positive"
    assert "amazing" in bat["opinion_words"]

    # 2. Delivery
    assert "Delivery" in aspects_by_canon
    deliv = aspects_by_canon["Delivery"]
    assert deliv["term"] == "delivery"
    assert deliv["start"] == 33
    assert deliv["end"] == 41
    assert deliv["sentiment"] == "negative"
    assert "late" in deliv["opinion_words"]

    # 3. Price
    assert "Price" in aspects_by_canon
    pr = aspects_by_canon["Price"]
    assert pr["term"] == "price"
    assert pr["start"] == 59
    assert pr["end"] == 64
    assert pr["sentiment"] == "negative"
    assert any("high" in op for op in pr["opinion_words"])


def test_negation_handling_vader_and_transformer():
    """Verify explicit negation phrases ('not good', 'never worked') are scored negative."""
    reviews = [
        ("The screen is not good.", "Display", "negative", "not good"),
        ("The device never worked.", "Performance", "negative", "never worked"),
    ]

    for review, expected_canon, expected_sent, expected_neg in reviews:
        for scorer_name in ["vader", "transformer"]:
            res = analyze_review(review, scorer=scorer_name)
            assert len(res["aspects"]) >= 1, f"No aspect extracted from '{review}'"
            aspect = res["aspects"][0]
            assert aspect["sentiment"] == expected_sent, (
                f"Failed on '{review}' with scorer {scorer_name}: expected {expected_sent}, got {aspect['sentiment']}"
            )
            assert any(expected_neg in op for op in aspect["opinion_words"]), (
                f"Expected '{expected_neg}' in opinion words, got {aspect['opinion_words']}"
            )


def test_rule_6_no_opinion_returns_neutral_low_confidence():
    """Rule 6: If an aspect has no opinion word, return neutral with low confidence (0.30). Do not guess."""
    # A review with an aspect noun and non-evaluative action verb
    review = "I bought this phone yesterday."
    
    # Direct scorer test when opinion_words=[]
    vader = get_scorer("vader")
    trans = get_scorer("transformer")

    v_res = vader.score(clause="I bought this phone yesterday.", aspect="phone", opinion_words=[])
    assert v_res.label == "neutral"
    assert v_res.confidence == 0.30
    assert v_res.opinion_words == []

    t_res = trans.score(clause="I bought this phone yesterday.", aspect="phone", opinion_words=[])
    assert t_res.label == "neutral"
    assert t_res.confidence == 0.30
    assert t_res.opinion_words == []


def test_contrast_word_isolation():
    """Verify that opinion words never cross contrast boundaries ('but', 'however')."""
    # Sentence with positive first clause and negative second clause
    text = "The camera is great, but the battery is terrible."
    res = analyze_review(text, scorer="vader")
    aspects = {a["canonical"]: a for a in res["aspects"]}

    assert "Camera" in aspects
    assert aspects["Camera"]["sentiment"] == "positive"
    assert "great" in aspects["Camera"]["opinion_words"]

    assert "Battery" in aspects
    assert aspects["Battery"]["sentiment"] == "negative"
    assert "terrible" in aspects["Battery"]["opinion_words"]

    # Flipped sentence: negative first clause and positive second clause
    text2 = "The battery is terrible, however the camera is stunning."
    res2 = analyze_review(text2, scorer="vader")
    aspects2 = {a["canonical"]: a for a in res2["aspects"]}

    assert aspects2["Battery"]["sentiment"] == "negative"
    assert aspects2["Camera"]["sentiment"] == "positive"


def test_offsets_integrity_invariant():
    """Verify that character start:end offsets in output slice the exact surface term."""
    reviews = [
        GOLDEN_REVIEW,
        "The screen resolution is sharp and colors are vibrant.",
        "Customer service was extremely helpful during the replacement.",
        "Terrible sound quality with distorted bass.",
    ]

    for rev in reviews:
        res = analyze_review(rev, scorer="vader")
        for a in res["aspects"]:
            slice_text = res["text"][a["start"]:a["end"]]
            assert slice_text == a["term"], f"Offset slice '{slice_text}' does not match term '{a['term']}'"


def test_finetuned_scorer_stub():
    """Verify that FineTunedScorer stub conforms to Scorer Protocol and returns ScoreResult."""
    scorer = get_scorer("finetuned")
    assert isinstance(scorer, FineTunedScorer)
    assert scorer.name == "finetuned"

    res = scorer.score("The battery life is excellent", "battery life", ["excellent"])
    assert isinstance(res, ScoreResult)
    assert res.label == "positive"
    assert res.confidence > 0.5


def test_analyze_batch():
    """Verify that analyze_batch runs across multiple reviews."""
    batch = [
        "Great battery life and clear screen.",
        "Slow delivery and damaged packaging.",
    ]
    results = analyze_batch(batch, scorer="vader")
    assert len(results) == 2
    assert len(results[0]["aspects"]) >= 1
    assert len(results[1]["aspects"]) >= 1
