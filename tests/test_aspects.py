"""Unit tests for aspect extraction methods, preprocessing, and filtering rules."""

from nlp.aspects import (
    extract_aspects,
    get_spacy_model,
    is_generic_noun,
)
from nlp.preprocess import (
    clean_text,
    expand_contractions,
    preprocess_review,
)

# 15 Hand-written test sentences covering laptops, phones, electronics, restaurants
HANDWRITTEN_SENTENCES = [
    # 1. Copular subject
    "The battery life is amazing and lasts all day.",
    # 2. Multi-aspect contrast
    "Delivery was late, but the customer service was very helpful.",
    # 3. Compound aspect
    "The screen resolution is crystal clear and bright.",
    # 4. Predicate adjective
    "The build quality feels cheap and plasticky.",
    # 5. Prepositional phrase
    "Sound quality through the speakers is exceptional.",
    # 6. Restaurant domain
    "The food was delicious, but the ambience was noisy.",
    # 7. Generic nouns (all should be filtered out!)
    "This product is an awesome item that works in every way.",
    # 8. Modifiers with blacklist words
    "Fast charging speed saves me a lot of time.",
    # 9. Direct object aspect
    "The camera takes stunning pictures in low light.",
    # 10. Multi-compound feedback
    "Keyboard has great tactile feedback and key travel.",
    # 11. Contrast with performance
    "The price is too high for such mediocre performance.",
    # 12. Passive subject
    "Packaging was damaged upon arrival, but the phone itself was fine.",
    # 13. Subject plural compound
    "Software updates frequently freeze the device.",
    # 14. Service domain
    "Staff was courteous and attentive to our table.",
    # 15. The golden review anchor
    "Battery life is amazing, but the delivery was late and the price is too high.",
]


def test_pii_and_whitespace_cleaning():
    """Verify HTML removal, PII masking, and whitespace normalization."""
    raw = "<div>Contact user@test.org or 800-555-0199 for   support.<br>Awesome!</div>"
    cleaned = clean_text(raw)
    assert "<div>" not in cleaned
    assert "[EMAIL]" in cleaned
    assert "[PHONE]" in cleaned
    assert "  " not in cleaned
    assert "user@test.org" not in cleaned


def test_contraction_expansion():
    """Verify contraction expansion on common patterns."""
    text = "It's great, but they won't fix it and we can't recommend it."
    expanded = expand_contractions(text)
    assert "cannot recommend" in expanded
    assert "will not fix" in expanded


def test_sentence_splitting_and_offsets():
    """Verify sentence splitting preserves exact character offsets into original clean text."""
    nlp = get_spacy_model()
    text = "Battery life is great. Screen resolution is sharp! Delivery was late."
    doc = preprocess_review(text, spacy_model=nlp)

    assert len(doc.sentences) == 3
    assert doc.clean_text_lower == text.lower()

    for span in doc.sentences:
        # Offsets must exactly reproduce the sentence text
        assert text[span.start_char : span.end_char] == span.text
        assert span.lower_text == span.text.lower()


def test_generic_noun_blacklist():
    """Verify blacklist drops generic non-aspect nouns."""
    generics = ["product", "item", "thing", "time", "day", "way", "lot", "bit", "stuff"]
    for word in generics:
        assert is_generic_noun(word) is True

    aspects = ["battery", "screen", "price", "delivery", "keyboard", "sound", "camera"]
    for word in aspects:
        assert is_generic_noun(word) is False


def test_candidate_character_offsets_invariant():
    """Rule 2 verification: text[char_start:char_end] == term for all extractors across all 15 sentences."""
    for sentence in HANDWRITTEN_SENTENCES:
        for method in ["nltk_regex", "spacy_chunks", "spacy_deps", "all"]:
            candidates = extract_aspects(sentence, method=method)
            for c in candidates:
                extracted_slice = sentence[c.char_start : c.char_end]
                assert extracted_slice == c.term, (
                    f"Offset mismatch for method '{method}' in '{sentence}': "
                    f"expected '{c.term}', got '{extracted_slice}'"
                )


def test_golden_review_extraction():
    """Verify golden test review extracts battery life, delivery, and price across all extractors."""
    golden = "Battery life is amazing, but the delivery was late and the price is too high."
    for method in ["nltk_regex", "spacy_chunks", "spacy_deps", "all"]:
        candidates = extract_aspects(golden, method=method)
        lemmas = [c.lemma for c in candidates]
        assert any("battery" in lem for lem in lemmas), f"Battery missing in {method}"
        assert any("delivery" in lem for lem in lemmas), f"Delivery missing in {method}"
        assert any("price" in lem for lem in lemmas), f"Price missing in {method}"


def test_all_15_sentences_extraction():
    """Run all 15 sentences through each extractor and verify non-empty extraction for non-generic sentences."""
    for idx, sentence in enumerate(HANDWRITTEN_SENTENCES, 1):
        cands_regex = extract_aspects(sentence, method="nltk_regex")
        cands_chunks = extract_aspects(sentence, method="spacy_chunks")
        cands_deps = extract_aspects(sentence, method="spacy_deps")

        # Sentence 7 is purely generic ("This product is an awesome item that works in every way.")
        if idx == 7:
            assert len(cands_regex) == 0
            assert len(cands_chunks) == 0
            assert len(cands_deps) == 0
        else:
            # At least one extractor must successfully find aspect candidates
            combined = cands_regex + cands_chunks + cands_deps
            assert len(combined) > 0, f"No candidates found for sentence {idx}: '{sentence}'"


def test_frequency_filter_across_product_reviews():
    """Rule 4: verify candidates appearing in < min_freq reviews for a product are dropped."""
    # 5 reviews for product A
    product_reviews = [
        "The battery life is stellar.",
        "Loved the battery life and build.",
        "Terrible battery life on this unit.",
        "Fast delivery, but battery life is short.",
        "Battery life lasts through the night.",
    ]
    # Unique aspect mentioned only once in a separate review
    test_review = "The battery life is okay, but the packaging had a weird dent."

    # With min_freq=5: 'battery life' appears in all 6 reviews (>=5), 'packaging' appears in only 1 (<5)
    filtered = extract_aspects(
        test_review,
        method="spacy_chunks",
        min_freq=5,
        product_reviews=product_reviews,
    )
    lemmas = [c.lemma for c in filtered]
    assert any("battery" in lem for lem in lemmas)
    assert not any("packaging" in lem for lem in lemmas), (
        "Infrequent aspect 'packaging' should be pruned!"
    )
