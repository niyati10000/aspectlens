"""Comprehensive tests for text preprocessing, PII stripping, contractions, and offset mapping."""

from nlp.preprocess import (
    clean_text,
    expand_contractions,
    preprocess_review,
    strip_pii,
)


def test_html_cleaning():
    """Verify HTML tags, breaks, and entities are cleaned safely."""
    raw = "<p>The <b>screen</b> is crisp and bright!<br/>Love it.</p>"
    cleaned = clean_text(raw)
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned
    assert "<br/>" not in cleaned
    assert "The screen is crisp and bright! Love it." in cleaned


def test_whitespace_normalization():
    """Verify multiple spaces, tabs, and excess newlines are normalized."""
    raw = "Great   phone.\n\n\nBattery   lasts\t\ttwo   days."
    cleaned = clean_text(raw)
    assert "   " not in cleaned
    assert "\t" not in cleaned
    assert "\n\n" not in cleaned
    assert "Great phone.\nBattery lasts two days." == cleaned


def test_pii_stripping_emails():
    """Verify email addresses are anonymized."""
    raw = "Contact support at help@example.com or john.doe@company.org immediately."
    cleaned = strip_pii(raw)
    assert "help@example.com" not in cleaned
    assert "john.doe@company.org" not in cleaned
    assert "[EMAIL]" in cleaned


def test_pii_stripping_phone_numbers():
    """Verify phone numbers in multiple formats are anonymized."""
    samples = [
        "Call 1-800-555-0199 for warranty.",
        "Reach me at (555) 123-4567 tomorrow.",
        "Customer desk: 555.234.5678.",
        "Mobile: +1-555-987-6543.",
    ]
    for s in samples:
        stripped = strip_pii(s)
        assert "[PHONE]" in stripped


def test_pii_stripping_urls():
    """Verify external URLs are stripped."""
    raw = "See benchmark at https://www.example.com/test-review?ref=123 for proof."
    cleaned = strip_pii(raw)
    assert "https://" not in cleaned
    assert "[URL]" in cleaned


def test_contraction_expansion():
    """Verify contractions are expanded correctly without corrupting text."""
    cases = [
        ("can't charge", "cannot charge"),
        ("won't connect", "will not connect"),
        ("it's amazing", "it is amazing"),
        ("they're late", "they are late"),
        ("I've noticed lag", "I have noticed lag"),
        ("I'd recommend", "I would recommend"),
        ("we're pleased", "we are pleased"),
    ]
    for contracted, expected in cases:
        expanded = expand_contractions(contracted)
        assert expected.lower() in expanded.lower()


def test_preprocess_review_offsets_and_sentences():
    """Verify preprocess_review sentence offsets exactly slice clean_text."""
    raw = "First sentence here. Second sentence! Is this third?"
    doc = preprocess_review(raw)
    assert len(doc.sentences) >= 2

    # Invariant: clean_text[s.start_char:s.end_char] == s.text
    for s in doc.sentences:
        assert doc.clean_text[s.start_char : s.end_char] == s.text
        assert s.lower_text == s.text.lower()


def test_rule_1_never_remove_stopwords_before_pos():
    """Rule 1: clean_text does NOT remove stopwords like 'the', 'is', 'a'."""
    raw = "The camera is a great addition to the phone."
    cleaned = clean_text(raw)
    words = cleaned.lower().split()
    assert "the" in words
    assert "is" in words
    assert "a" in words
    assert "to" in words
