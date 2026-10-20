"""Tests for clause-scoped opinion linking, contrast boundary enforcement, and negation handling."""

import pytest

from nlp.aspects import get_spacy_model
from nlp.opinions import (
    extract_opinions_for_aspect,
    split_into_clauses,
)


@pytest.fixture(scope="module")
def spacy_nlp():
    return get_spacy_model()


def test_contrast_word_boundary_isolation(spacy_nlp):
    """Rule 5: Opinions in one clause must never cross contrast markers into another clause."""
    # Sentence: "Battery life is amazing, but the delivery was late."
    # 'amazing' must belong ONLY to 'Battery life', and 'late' must belong ONLY to 'delivery'
    text = "Battery life is amazing, but the delivery was late."
    doc = spacy_nlp(text)
    clauses = split_into_clauses(doc)

    assert len(clauses) >= 2

    # Aspect 1: "Battery life" (start: 0, end: 12)
    ops_battery, clause_battery = extract_opinions_for_aspect(doc, 0, 12, clauses)
    assert any("amazing" in op for op in ops_battery)
    assert not any("late" in op for op in ops_battery)

    # Aspect 2: "delivery" (start: 33, end: 41)
    deliv_start = text.index("delivery")
    deliv_end = deliv_start + len("delivery")
    ops_delivery, clause_delivery = extract_opinions_for_aspect(
        doc, deliv_start, deliv_end, clauses
    )
    assert any("late" in op for op in ops_delivery)
    assert not any("amazing" in op for op in ops_delivery)


def test_contrast_words_variety(spacy_nlp):
    """Verify various contrast words establish clause boundaries."""
    contrast_markers = ["however", "although", "yet", "though", "nevertheless", "whereas"]
    for marker in contrast_markers:
        text = f"The screen is beautiful {marker} the price is terrible."
        doc = spacy_nlp(text)
        clauses = split_into_clauses(doc)

        screen_end = len("The screen")
        ops_screen, _ = extract_opinions_for_aspect(doc, 4, screen_end, clauses)
        assert any("beautiful" in op for op in ops_screen)
        assert not any("terrible" in op for op in ops_screen)


def test_negation_word_attachment(spacy_nlp):
    """Rule 7: Negation words ('not', 'never', 'hardly') attach to opinion adjectives."""
    cases = [
        ("The camera is not good.", "camera", "not good"),
        ("Delivery was never fast.", "Delivery", "never fast"),
        ("The sound is hardly clear.", "sound", "hardly clear"),
    ]
    for text, aspect_term, expected_op in cases:
        doc = spacy_nlp(text)
        clauses = split_into_clauses(doc)
        start = text.index(aspect_term)
        end = start + len(aspect_term)
        ops, _ = extract_opinions_for_aspect(doc, start, end, clauses)
        assert any(expected_op in op for op in ops), f"Expected '{expected_op}' in {ops}"


def test_intensifier_attachment(spacy_nlp):
    """Intensifiers ('too', 'very', 'extremely') attach to opinion adjectives."""
    cases = [
        ("The price is too high.", "price", "too high"),
        ("The screen is very bright.", "screen", "very bright"),
        ("The battery is extremely durable.", "battery", "extremely durable"),
    ]
    for text, aspect_term, expected_op in cases:
        doc = spacy_nlp(text)
        clauses = split_into_clauses(doc)
        start = text.index(aspect_term)
        end = start + len(aspect_term)
        ops, _ = extract_opinions_for_aspect(doc, start, end, clauses)
        assert any(expected_op in op for op in ops), f"Expected '{expected_op}' in {ops}"


def test_no_opinion_returns_empty_list(spacy_nlp):
    """Rule 6: When an aspect has no descriptive opinion words, return empty list."""
    text = "The usb cable was in the box."
    doc = spacy_nlp(text)
    clauses = split_into_clauses(doc)

    start = text.index("usb cable")
    end = start + len("usb cable")
    ops, clause = extract_opinions_for_aspect(doc, start, end, clauses)
    assert len(ops) == 0
