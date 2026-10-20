"""Unit tests for aspect canonical grouping, seed lexicon, WordNet, and MiniLM clustering."""

import pytest
import numpy as np
from nlp.grouping import (
    AspectGrouper,
    get_aspect_grouper,
    group_aspect_term,
)


def test_acceptance_criteria_price_grouping():
    """Acceptance test: 'cost', 'price', 'value for money' map to Price."""
    grouper = get_aspect_grouper()

    for term in ["cost", "price", "value for money"]:
        canonical, origin, conf = grouper.group_aspect(term)
        assert canonical == "Price", f"Expected 'Price' for '{term}', got '{canonical}' (via {origin})"


def test_all_11_canonical_aspects_coverage():
    """Verify mapping across all 11 locked-in canonical aspects."""
    test_cases = [
        ("battery life", "Battery"),
        ("power bank", "Battery"),
        ("charger", "Battery"),
        ("expensive", "Price"),
        ("pricing", "Price"),
        ("shipping", "Delivery"),
        ("arrival", "Delivery"),
        ("screen resolution", "Display"),
        ("touchscreen", "Display"),
        ("camera", "Camera"),
        ("photos", "Camera"),
        ("speed", "Performance"),
        ("multitasking", "Performance"),
        ("durability", "Build Quality"),
        ("build quality", "Build Quality"),
        ("customer service", "Customer Service"),
        ("warranty", "Customer Service"),
        ("packaging", "Packaging"),
        ("bubble wrap", "Packaging"),
        ("sound quality", "Sound"),
        ("speakers", "Sound"),
        ("software updates", "Software"),
        ("firmware", "Software"),
    ]

    grouper = get_aspect_grouper()
    for term, expected_canonical in test_cases:
        canonical, origin, _ = grouper.group_aspect(term)
        assert canonical == expected_canonical, (
            f"Mapping failed for '{term}': expected '{expected_canonical}', got '{canonical}' (via {origin})"
        )


def test_seed_lexicon_priority_over_conflicts():
    """Verify that seed lexicon takes strict priority over embedding and WordNet matches."""
    grouper = get_aspect_grouper()
    # 'cord' in Battery keywords
    canonical, origin, conf = grouper.group_aspect("cord", use_seed=True, use_wordnet=True, use_embeddings=True)
    assert canonical == "Battery"
    assert origin == "seed"
    assert conf == 1.0


def test_switchable_ablation_flags():
    """Verify each tool is individually switchable for ablation studies."""
    grouper = get_aspect_grouper()

    # With seed only
    can_seed, orig_seed, _ = grouper.group_aspect("cost", use_seed=True, use_wordnet=False, use_embeddings=False)
    assert can_seed == "Price"
    assert orig_seed == "seed"

    # With wordnet only
    can_wn, orig_wn, _ = grouper.group_aspect("cost", use_seed=False, use_wordnet=True, use_embeddings=False)
    assert can_wn == "Price"
    assert orig_wn == "wordnet"

    # With embeddings only
    can_emb, orig_emb, _ = grouper.group_aspect("cost", use_seed=False, use_wordnet=False, use_embeddings=True)
    assert can_emb == "Price"
    assert orig_emb == "embedding"

    # With all disabled: falls back to title-cased unmatched
    can_none, orig_none, _ = grouper.group_aspect("cost", use_seed=False, use_wordnet=False, use_embeddings=False)
    assert can_none == "Cost"
    assert orig_none == "unmatched"


def test_embedding_cache():
    """Verify embedding cache stores vectors and avoids redundant model encoding."""
    grouper = get_aspect_grouper()
    term = "unique test term for cache verification"
    assert term not in grouper.embedding_cache

    emb1 = grouper.get_embedding(term)
    assert term in grouper.embedding_cache
    assert isinstance(emb1, np.ndarray)

    emb2 = grouper.get_embedding(term)
    assert np.array_equal(emb1, emb2)


def test_agglomerative_clustering_unmatched():
    """Verify AgglomerativeClustering groups semantically related unmatched terms."""
    grouper = get_aspect_grouper()
    unmatched_terms = [
        "rubber bumper", "protective bumper", "silicone bumper",
        "car adapter", "vehicle adapter", "lighter adapter"
    ]

    clusters = grouper.cluster_unmatched(unmatched_terms, distance_threshold=0.45)
    assert len(clusters) >= 2, f"Expected at least 2 clusters, got {len(clusters)}"
    # Bumper terms should cluster together
    all_cluster_lists = list(clusters.values())
    bumper_cluster = [c for c in all_cluster_lists if any("bumper" in t for t in c)][0]
    assert sum("bumper" in t for t in bumper_cluster) >= 2
