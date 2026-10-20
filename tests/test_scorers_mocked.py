"""Unit tests for sentiment scorers with mocked heavy models and edge cases."""

from unittest.mock import MagicMock

import pytest
import torch

from nlp.sentiment import (
    FineTunedScorer,
    TransformerScorer,
    VADERScorer,
    get_scorer,
)


def test_vader_domain_lexicon():
    """Verify VADER domain adaptations correctly penalize hardware/delivery failure words."""
    vader = VADERScorer()

    res_late = vader.score("The delivery was late", "delivery", ["late"])
    assert res_late.label == "negative"
    assert res_late.score < 0

    res_overpriced = vader.score("The phone is overpriced", "phone", ["overpriced"])
    assert res_overpriced.label == "negative"
    assert res_overpriced.score < 0

    res_bargain = vader.score("The price is a real bargain", "price", ["bargain"])
    assert res_bargain.label == "positive"
    assert res_bargain.score > 0


def test_vader_no_opinion_returns_neutral():
    """Rule 6: If no opinion words exist, return neutral with low confidence (0.30)."""
    vader = VADERScorer()
    res = vader.score("The unit comes with a charger", "charger", [])
    assert res.label == "neutral"
    assert res.confidence == 0.30
    assert res.score == 0.0


def test_finetuned_scorer_fallback():
    """Verify FineTunedScorer cleanly acts as a stub falling back to VADER before Phase 11."""
    ft = FineTunedScorer()
    res_pos = ft.score("Battery life is great", "battery", ["great"])
    assert res_pos.label == "positive"

    res_empty = ft.score("Has a keyboard", "keyboard", [])
    assert res_empty.label == "neutral"
    assert res_empty.confidence == 0.30


def test_transformer_scorer_mocked():
    """Test TransformerScorer classification and probability mapping using mocked model."""
    scorer = TransformerScorer.__new__(TransformerScorer)
    scorer.name = "transformer"
    scorer.model_name = "mock_model"
    scorer.id2label = {0: "negative", 1: "neutral", 2: "positive"}
    scorer.is_binary = False

    # Mock tokenizer
    mock_tok = MagicMock()
    mock_tok.return_value = {
        "input_ids": torch.tensor([[101, 102]]),
        "attention_mask": torch.tensor([[1, 1]]),
    }
    scorer.tokenizer = mock_tok

    # Mock model returning positive logits (neg: 1.0, neu: 2.0, pos: 8.0)
    mock_model = MagicMock()
    mock_output = MagicMock()
    mock_output.logits = torch.tensor([[1.0, 2.0, 8.0]])
    mock_model.return_value = mock_output
    scorer.model = mock_model

    res = scorer.score("The battery is incredible", "battery", ["incredible"])
    assert res.label == "positive"
    assert res.confidence > 0.8
    assert res.score > 0


def test_transformer_scorer_mocked_negative():
    """Test TransformerScorer output when model predicts negative."""
    scorer = TransformerScorer.__new__(TransformerScorer)
    scorer.name = "transformer"
    scorer.model_name = "mock_model"
    scorer.id2label = {0: "negative", 1: "neutral", 2: "positive"}
    scorer.is_binary = False

    mock_tok = MagicMock()
    mock_tok.return_value = {
        "input_ids": torch.tensor([[101, 102]]),
        "attention_mask": torch.tensor([[1, 1]]),
    }
    scorer.tokenizer = mock_tok

    mock_model = MagicMock()
    mock_output = MagicMock()
    mock_output.logits = torch.tensor([[7.0, 1.0, 0.5]])  # Strong negative
    mock_model.return_value = mock_output
    scorer.model = mock_model

    res = scorer.score("The camera is terrible", "camera", ["terrible"])
    assert res.label == "negative"
    assert res.confidence > 0.8
    assert res.score < 0


def test_scorer_registry_and_caching():
    """Verify get_scorer caches instances across calls."""
    s1 = get_scorer("vader")
    s2 = get_scorer("vader")
    assert s1 is s2

    with pytest.raises(ValueError):
        get_scorer("non_existent_scorer")
