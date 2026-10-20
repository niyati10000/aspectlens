"""End-to-end review analysis pipeline combining preprocessing, extraction, grouping, opinions, and sentiment.

Matches the API output contract defined in ARCHITECTURE.md Section 5:
{
  "text": "...",
  "scorer": "vader",
  "aspects": [
    {
      "term": "Battery life",
      "canonical": "Battery",
      "start": 0,
      "end": 12,
      "sentiment": "positive",
      "confidence": 0.91,
      "opinion_words": ["amazing"]
    }
  ],
  "latency_ms": 42
}
"""

from typing import List, Dict, Any, Optional
import time
import spacy

from app.config import settings
from nlp.preprocess import clean_text
from nlp.aspects import extract_aspects, get_spacy_model, AspectCandidate
from nlp.grouping import AspectGrouper
from nlp.opinions import extract_opinions_for_aspect, split_into_clauses
from nlp.sentiment import get_scorer, Scorer, ScoreResult

# Pipeline singleton caches
_PIPELINE_GROUPER: Optional[AspectGrouper] = None


def get_aspect_grouper() -> AspectGrouper:
    """Retrieve or initialize the global cached AspectGrouper."""
    global _PIPELINE_GROUPER
    if _PIPELINE_GROUPER is None:
        _PIPELINE_GROUPER = AspectGrouper()
    return _PIPELINE_GROUPER


def analyze_review(
    text: str,
    scorer: str = "vader",
    extractor: str = "spacy_chunks",
    min_freq: int = 1,
    product_reviews: Optional[List[str]] = None,
    spacy_nlp: Optional[spacy.language.Language] = None,
    grouper: Optional[AspectGrouper] = None,
) -> Dict[str, Any]:
    """Run the complete ABSA pipeline on a single review text.

    Steps:
    1. Preprocess: clean HTML, strip PII (emails, phones), and normalize whitespace.
    2. Extract aspects: extract candidates with exact character offsets referencing clean text.
    3. Group aspects: map each candidate to its canonical group (seed lexicon, WordNet, MiniLM).
    4. Link opinions: clause-scoped dependency arcs and fallback window (never crossing contrast markers).
    5. Score sentiment: evaluate clause with selected scorer (vader, transformer, finetuned).
    6. Return response conforming to ARCHITECTURE.md Section 5 contract.
    """
    t_start = time.perf_counter()

    # Step 1: Preprocess and clean text
    cleaned = clean_text(text)
    if not cleaned:
        return {
            "text": text,
            "scorer": scorer,
            "aspects": [],
            "latency_ms": round((time.perf_counter() - t_start) * 1000, 1),
        }

    nlp = spacy_nlp or get_spacy_model()
    aspect_grouper = grouper or get_aspect_grouper()
    scorer_instance: Scorer = get_scorer(scorer)

    # Step 2: Extract aspect candidates
    candidates: List[AspectCandidate] = extract_aspects(
        cleaned,
        method=extractor,
        min_freq=min_freq,
        product_reviews=product_reviews,
        nlp_spacy=nlp,
    )

    if not candidates:
        return {
            "text": cleaned,
            "scorer": scorer_instance.name,
            "aspects": [],
            "latency_ms": round((time.perf_counter() - t_start) * 1000, 1),
        }

    # Step 3: Parse sentences and clauses with spaCy
    doc = nlp(cleaned)
    clauses = split_into_clauses(doc)

    aspect_results: List[Dict[str, Any]] = []

    for cand in candidates:
        # Step 4: Map to canonical aspect group
        canonical_name, _, _ = aspect_grouper.group_aspect(cand.term)

        # Step 5: Extract clause-scoped opinion words
        opinion_words, clause_text = extract_opinions_for_aspect(
            doc,
            cand.char_start,
            cand.char_end,
            clauses,
        )

        # Step 6: Score sentiment
        score_res: ScoreResult = scorer_instance.score(
            clause=clause_text,
            aspect=cand.term,
            opinion_words=opinion_words,
        )

        # Invariant validation: ensure character offsets exactly slice the term
        assert cleaned[cand.char_start:cand.char_end] == cand.term, (
            f"Offset mismatch: '{cleaned[cand.char_start:cand.char_end]}' != '{cand.term}'"
        )

        aspect_results.append({
            "term": cand.term,
            "canonical": canonical_name,
            "start": cand.char_start,
            "end": cand.char_end,
            "sentiment": score_res.label,
            "confidence": score_res.confidence,
            "opinion_words": score_res.opinion_words,
        })

    latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

    return {
        "text": cleaned,
        "scorer": scorer_instance.name,
        "aspects": aspect_results,
        "latency_ms": latency_ms,
    }


def analyze_batch(
    reviews: List[str],
    scorer: str = "vader",
    extractor: str = "spacy_chunks",
    min_freq: int = 1,
) -> List[Dict[str, Any]]:
    """Analyze a batch of reviews reusing cached models and components."""
    nlp = get_spacy_model()
    grouper = get_aspect_grouper()
    return [
        analyze_review(
            r,
            scorer=scorer,
            extractor=extractor,
            min_freq=min_freq,
            spacy_nlp=nlp,
            grouper=grouper,
        )
        for r in reviews
    ]
