"""Aspect sentiment scoring interface and implementations.

Implements three switchable scorers behind one unified Scorer Protocol:
1. VADERScorer: Lexicon and rule-based scorer with domain adaptation, negation,
   and intensifier handling.
2. TransformerScorer: Pretrained transformer (cardiffnlp/twitter-roberta-base-sentiment-latest
   with distilbert-base-uncased-finetuned-sst-2-english fallback) applied to the clause containing the aspect.
3. FineTunedScorer: Clean stub taking (clause, aspect, opinion_words) pair for ABSA fine-tuned models.

Adheres to BRAIN.md Non-negotiable NLP Rule 6:
If an aspect has no opinion word, return neutral with low confidence (0.30). Do not guess.
"""

import logging
import re
from dataclasses import dataclass
from typing import Protocol

import nltk
import torch
import torch.nn.functional as F
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Standardized sentiment scoring output matching ARCHITECTURE.md contract."""

    label: str  # "positive" | "negative" | "neutral"
    confidence: float  # 0.0 to 1.0
    opinion_words: list[str]  # List of opinion phrases supporting this classification
    score: float  # Continuous polarity score in range [-1.0, 1.0]


class Scorer(Protocol):
    """Unified Protocol for all aspect sentiment scorers."""

    name: str

    def score(self, clause: str, aspect: str, opinion_words: list[str]) -> ScoreResult:
        """Score the sentiment of an aspect within its clause context."""
        ...


# ----------------------------------------------------------------------
# 1. VADER Scorer with Domain and Intensifier Enhancements
# ----------------------------------------------------------------------
# Review domain lexicon adjustments (sentiment words missing or misplaced in generic VADER)
DOMAIN_VADER_LEXICON: dict[str, float] = {
    # Delivery and fulfillment
    "late": -1.8,
    "delayed": -1.8,
    "slow": -1.5,
    "arrived": 0.5,
    "missing": -2.0,
    "lost": -2.0,
    # Price and value
    "overpriced": -2.2,
    "expensive": -1.8,
    "costly": -1.6,
    "affordable": 1.8,
    "bargain": 2.0,
    # Hardware and condition
    "damaged": -2.5,
    "broken": -2.5,
    "defective": -2.5,
    "faulty": -2.2,
    "scratched": -1.8,
    "flimsy": -2.0,
    "sturdy": 2.0,
    "durable": 2.0,
    "premium": 2.2,
    # Performance and software
    "lag": -1.8,
    "laggy": -2.0,
    "lags": -1.8,
    "sluggish": -1.8,
    "buggy": -2.0,
    "bugs": -1.6,
    "crash": -2.2,
    "crashes": -2.2,
    "crashing": -2.2,
    "drain": -1.6,
    "drains": -1.8,
    "draining": -1.8,
    "responsive": 2.0,
    "snappy": 2.0,
    "smooth": 1.8,
    # Display and audio
    "crisp": 1.8,
    "blurry": -1.8,
    "dim": -1.5,
    "dull": -1.5,
    "faint": -1.2,
    "muffled": -1.8,
    # General review descriptors
    "subpar": -2.0,
    "mediocre": -1.4,
    "horrible": -2.5,
    "terrible": -2.5,
    "awful": -2.5,
    "poor": -2.0,
    "superb": 2.5,
    "fantastic": 2.5,
    "awesome": 2.5,
    "amazing": 2.5,
    "excellent": 2.5,
}

# Domain phrase substitutions for multi-word excess and negation handling in VADER
DOMAIN_PHRASE_RULES = [
    (re.compile(r"\btoo high\b", re.IGNORECASE), "excessively_high_neg", -2.0),
    (re.compile(r"\btoo expensive\b", re.IGNORECASE), "excessively_expensive_neg", -2.2),
    (re.compile(r"\btoo slow\b", re.IGNORECASE), "excessively_slow_neg", -2.0),
    (re.compile(r"\btoo loud\b", re.IGNORECASE), "excessively_loud_neg", -1.8),
    (re.compile(r"\btoo heavy\b", re.IGNORECASE), "excessively_heavy_neg", -1.8),
    (re.compile(r"\btoo hot\b", re.IGNORECASE), "excessively_hot_neg", -2.0),
    (re.compile(r"\btoo warm\b", re.IGNORECASE), "excessively_warm_neg", -1.5),
    (re.compile(r"\btoo small\b", re.IGNORECASE), "excessively_small_neg", -1.5),
    (re.compile(r"\btoo big\b", re.IGNORECASE), "excessively_big_neg", -1.5),
    (re.compile(r"\bnever worked\b", re.IGNORECASE), "never_worked_neg", -2.5),
    (re.compile(r"\bnever arrived\b", re.IGNORECASE), "never_arrived_neg", -2.5),
    (re.compile(r"\bno issues\b", re.IGNORECASE), "no_issues_pos", 2.0),
    (re.compile(r"\bno complaints\b", re.IGNORECASE), "no_complaints_pos", 2.0),
    (re.compile(r"\bno problems\b", re.IGNORECASE), "no_problems_pos", 2.0),
    (re.compile(r"\bnot good\b", re.IGNORECASE), "not_good_neg", -1.8),
    (re.compile(r"\bnot working\b", re.IGNORECASE), "not_working_neg", -2.2),
]


class VADERScorer:
    """VADER-based sentiment scorer with domain adjustments, negation, and intensifier handling."""

    name: str = "vader"

    def __init__(self):
        try:
            self.sia = SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
            self.sia = SentimentIntensityAnalyzer()

        # Update lexicon with domain knowledge
        self.sia.lexicon.update(DOMAIN_VADER_LEXICON)
        for _, token, score in DOMAIN_PHRASE_RULES:
            self.sia.lexicon[token] = score

    def score(self, clause: str, aspect: str, opinion_words: list[str]) -> ScoreResult:
        # Rule 6: No opinion word found -> return neutral with low confidence
        if not opinion_words:
            return ScoreResult(
                label="neutral",
                confidence=0.30,
                opinion_words=[],
                score=0.0,
            )

        # Apply multi-word domain phrase substitutions to clause
        text_to_score = clause.strip() if clause.strip() else " ".join(opinion_words)
        for pattern, token, _ in DOMAIN_PHRASE_RULES:
            text_to_score = pattern.sub(token, text_to_score)

        polarity = self.sia.polarity_scores(text_to_score)
        compound = polarity["compound"]

        # If clause score is neutral or weak, also check opinion words directly
        if abs(compound) < 0.05 and opinion_words:
            op_text = " ".join(opinion_words)
            for pattern, token, _ in DOMAIN_PHRASE_RULES:
                op_text = pattern.sub(token, op_text)
            op_polarity = self.sia.polarity_scores(op_text)
            if abs(op_polarity["compound"]) > abs(compound):
                polarity = op_polarity
                compound = op_polarity["compound"]

        # Map compound score to label and confidence
        if compound >= 0.05:
            label = "positive"
            conf = min(0.99, max(0.55, 0.50 + abs(compound) * 0.50))
        elif compound <= -0.05:
            label = "negative"
            conf = min(0.99, max(0.55, 0.50 + abs(compound) * 0.50))
        else:
            label = "neutral"
            conf = 0.50

        return ScoreResult(
            label=label,
            confidence=round(conf, 2),
            opinion_words=opinion_words,
            score=round(compound, 3),
        )


# ----------------------------------------------------------------------
# 2. Transformer Scorer (RoBERTa / DistilBERT fallback)
# ----------------------------------------------------------------------
_TRANSFORMER_TOKENIZER = None
_TRANSFORMER_MODEL = None
_TRANSFORMER_LOADED_NAME = None


def get_transformer_model(model_name: str | None = None):
    """Load and cache the Hugging Face transformer model and tokenizer once."""
    global _TRANSFORMER_TOKENIZER, _TRANSFORMER_MODEL, _TRANSFORMER_LOADED_NAME
    target_model = model_name or settings.SENTIMENT_MODEL

    if _TRANSFORMER_MODEL is None or _TRANSFORMER_LOADED_NAME != target_model:
        try:
            logger.info("Loading sentiment transformer model: %s", target_model)
            _TRANSFORMER_TOKENIZER = AutoTokenizer.from_pretrained(target_model)
            _TRANSFORMER_MODEL = AutoModelForSequenceClassification.from_pretrained(target_model)
            _TRANSFORMER_MODEL.eval()
            _TRANSFORMER_LOADED_NAME = target_model
        except Exception as e:
            logger.warning(
                "Failed to load %s (%s). Attempting DistilBERT fallback.", target_model, e
            )
            fallback = "distilbert-base-uncased-finetuned-sst-2-english"
            _TRANSFORMER_TOKENIZER = AutoTokenizer.from_pretrained(fallback)
            _TRANSFORMER_MODEL = AutoModelForSequenceClassification.from_pretrained(fallback)
            _TRANSFORMER_MODEL.eval()
            _TRANSFORMER_LOADED_NAME = fallback

    return _TRANSFORMER_TOKENIZER, _TRANSFORMER_MODEL


class TransformerScorer:
    """Pretrained transformer sentiment scorer operating on the aspect's clause."""

    name: str = "transformer"

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.SENTIMENT_MODEL
        self.tokenizer, self.model = get_transformer_model(self.model_name)
        self.id2label = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        self.is_binary = len(self.id2label) == 2

    def score(self, clause: str, aspect: str, opinion_words: list[str]) -> ScoreResult:
        # Rule 6: No opinion word found -> return neutral with low confidence
        if not opinion_words:
            return ScoreResult(
                label="neutral",
                confidence=0.30,
                opinion_words=[],
                score=0.0,
            )

        text_input = clause.strip() if clause.strip() else f"{aspect} is {' '.join(opinion_words)}"

        inputs = self.tokenizer(
            text_input,
            return_tensors="pt",
            truncation=True,
            max_length=128,
        )

        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = F.softmax(logits, dim=-1)[0]

        if not self.is_binary:
            # 3-class model (negative, neutral, positive)
            pred_idx = int(torch.argmax(logits, dim=-1).item())
            raw_label = self.id2label.get(pred_idx, "neutral")

            # Normalize label
            if "pos" in raw_label:
                label = "positive"
            elif "neg" in raw_label:
                label = "negative"
            else:
                label = "neutral"

            conf = float(probs[pred_idx].item())

            # Find positive and negative indices for score
            pos_prob = 0.0
            neg_prob = 0.0
            for idx, name in self.id2label.items():
                if "pos" in name:
                    pos_prob = float(probs[idx].item())
                elif "neg" in name:
                    neg_prob = float(probs[idx].item())
            continuous_score = pos_prob - neg_prob

        else:
            # 2-class model (NEGATIVE: 0, POSITIVE: 1)
            neg_prob = float(probs[0].item())
            pos_prob = float(probs[1].item())
            diff = pos_prob - neg_prob

            # Low confidence on binary classifier maps to neutral
            if max(pos_prob, neg_prob) < 0.60:
                label = "neutral"
                conf = 0.50
            elif pos_prob > neg_prob:
                label = "positive"
                conf = pos_prob
            else:
                label = "negative"
                conf = neg_prob

            continuous_score = diff

        return ScoreResult(
            label=label,
            confidence=round(conf, 2),
            opinion_words=opinion_words,
            score=round(continuous_score, 3),
        )


# ----------------------------------------------------------------------
# 3. Fine-Tuned Scorer Stub (ABSA Sentence + Aspect Pair)
# ----------------------------------------------------------------------
class FineTunedScorer:
    """Stub scorer for future domain/ABSA fine-tuned models (Phase 11).

    Accepts (clause, aspect, opinion_words) pair. When trained weights exist,
    evaluates paired cross-encoder; otherwise provides clean fallback.
    """

    name: str = "finetuned"

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or "models/finetuned_absa"
        self._fallback_scorer: Scorer | None = None

    def score(self, clause: str, aspect: str, opinion_words: list[str]) -> ScoreResult:
        if not opinion_words:
            return ScoreResult(
                label="neutral",
                confidence=0.30,
                opinion_words=[],
                score=0.0,
            )

        # In stub mode before Phase 11 training, fall back gracefully to VADERScorer
        if self._fallback_scorer is None:
            self._fallback_scorer = VADERScorer()

        return self._fallback_scorer.score(clause, aspect, opinion_words)


# ----------------------------------------------------------------------
# Scorer Factory and Registry
# ----------------------------------------------------------------------
_SCORER_INSTANCES: dict[str, Scorer] = {}


def get_scorer(name: str = "vader") -> Scorer:
    """Retrieve or instantiate a cached sentiment scorer by name ('vader', 'transformer', 'finetuned')."""
    key = name.lower().strip()
    if key not in _SCORER_INSTANCES:
        if key == "vader":
            _SCORER_INSTANCES[key] = VADERScorer()
        elif key in ("transformer", "roberta"):
            _SCORER_INSTANCES[key] = TransformerScorer()
        elif key == "finetuned":
            _SCORER_INSTANCES[key] = FineTunedScorer()
        else:
            raise ValueError(
                f"Unknown scorer: '{name}'. Choose from 'vader', 'transformer', 'finetuned'."
            )
    return _SCORER_INSTANCES[key]
