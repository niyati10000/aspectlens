"""Error Analysis for Aspect Extraction and Sentiment Classification.

Curates and categorizes misclassified instances on SemEval-2014 Task 4 into six linguistic failure modes:
1. implicit aspect: Sentiment conveyed without explicit lexical noun.
2. negation: Complex, double, or distant negation confusing opinion scope.
3. sarcasm: Sarcastic, ironic, or rhetorical expressions with reversed polarity.
4. multi-aspect clause: Multiple co-occurring aspects sharing clause boundary with conflicting sentiment.
5. comparison: Comparative structures ('better than', 'worse than') confusing target aspect polarity.
6. other: Domain-specific jargon, rare idioms, or ambiguous neutral statements.

Saves results to:
- eval/results/error_analysis.json (full categorised breakdown)
- eval/results/error_analysis.csv (at least 50 detailed misclassified rows)
"""

import csv
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from nlp.aspects import get_spacy_model
from nlp.opinions import extract_opinions_for_aspect, split_into_clauses
from nlp.sentiment import VADERScorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "processed_semeval.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"

COMPARISON_PATTERNS = [
    re.compile(
        r"\b(better|worse|faster|slower|cheaper|smaller|bigger|longer|shorter)\s+than\b", re.I
    ),
    re.compile(r"\b(more|less)\s+\w+\s+than\b", re.I),
    re.compile(r"\bcompared\s+to\b", re.I),
    re.compile(r"\bunlike\b", re.I),
    re.compile(r"\bas\s+\w+\s+as\b", re.I),
]

NEGATION_TOKENS = {
    "not",
    "n't",
    "never",
    "no",
    "neither",
    "nor",
    "hardly",
    "barely",
    "scarcely",
    "seldom",
    "rarely",
    "without",
    "nothing",
    "nobody",
}

SARCASM_INDICATORS = [
    re.compile(r"\b(great job|thanks for|brilliant|just perfect|wonderful)\b.*[!]", re.I),
    re.compile(r"['\"][a-zA-Z]+['\"]", re.I),  # quotation marks around words indicating irony
    re.compile(r"[!]{2,}", re.I),
]


def categorize_error(
    sentence: str,
    clause: str,
    aspect: str,
    gold: str,
    pred: str,
    other_aspects_in_sentence: list[str],
) -> tuple[str, str]:
    """Classify the linguistic failure mode and provide an explanation."""
    sent_lower = sentence.lower()
    clause_lower = clause.lower()

    # 1. Comparison check
    for pat in COMPARISON_PATTERNS:
        if pat.search(sent_lower):
            return (
                "comparison",
                "Comparative construct shifts sentiment relative to another entity.",
            )

    # 2. Sarcasm / Irony check
    if gold == "negative" and pred == "positive":
        for spat in SARCASM_INDICATORS:
            if spat.search(sentence):
                return (
                    "sarcasm",
                    "Sarcastic or ironic phrasing using positive words to express dissatisfaction.",
                )

    # 3. Negation check
    has_neg = any(
        tok in clause_lower.split() or tok in sent_lower.split() for tok in NEGATION_TOKENS
    )
    if has_neg and (gold != pred):
        return "negation", "Complex or scoped negation inverted intended aspect sentiment."

    # 4. Multi-aspect clause check
    if len(other_aspects_in_sentence) > 1:
        co_occurring = [
            a
            for a in other_aspects_in_sentence
            if a.lower() != aspect.lower() and a.lower() in clause_lower
        ]
        if co_occurring:
            return (
                "multi-aspect clause",
                f"Clause contains multiple co-occurring aspects ({', '.join(co_occurring)}) with diverging polarity.",
            )

    # 5. Implicit aspect check
    if (
        aspect.lower()
        in {
            "it",
            "this",
            "everything",
            "something",
            "anything",
            "part",
            "overall",
            "quality",
            "price",
        }
        and not clause.strip()
    ):
        return (
            "implicit aspect",
            "Aspect depends on implicit conversational context without explicit local modifier.",
        )
    if not clause.strip() or pred == "neutral" and gold != "neutral":
        return (
            "implicit aspect",
            "Reviewer implies sentiment without standard evaluative adjectives.",
        )

    # 6. Other (Lexical gap, domain idiom, or mixed nuances)
    return "other", "Domain-specific vocabulary or subtle nuance outside general sentiment lexicon."


def run_error_analysis(
    data_path: Path = DATA_PATH,
    results_dir: Path = RESULTS_DIR,
    target_count: int = 60,
) -> dict[str, Any]:
    """Extract real misclassified examples from SemEval test set and categorize failure modes."""
    logger.info("Loading SemEval test data from %s", data_path)
    with open(data_path, encoding="utf-8") as f:
        all_data = json.load(f)

    test_docs = [r for r in all_data if r.get("split") == "test" and r.get("aspect_terms")]

    nlp = get_spacy_model()
    vader = VADERScorer()

    collected_errors: list[dict[str, Any]] = []
    category_counts: Counter = Counter()

    logger.info("Analyzing %d test sentences for misclassifications...", len(test_docs))

    for row in test_docs:
        sentence = row["text"]
        aspects = row.get("aspect_terms", [])
        all_aspect_terms = [a["term"] for a in aspects]

        doc = nlp(sentence)
        clauses = split_into_clauses(doc)

        for a in aspects:
            gold_polarity = a.get("polarity", "").strip().lower()
            if gold_polarity not in {"positive", "negative", "neutral"}:
                continue

            term = a["term"]
            ops, clause = extract_opinions_for_aspect(doc, a["from"], a["to"], clauses)
            res = vader.score(clause, term, ops)
            pred_polarity = res.label

            if pred_polarity != gold_polarity:
                cat, reason = categorize_error(
                    sentence=sentence,
                    clause=clause,
                    aspect=term,
                    gold=gold_polarity,
                    pred=pred_polarity,
                    other_aspects_in_sentence=all_aspect_terms,
                )

                category_counts[cat] += 1
                collected_errors.append(
                    {
                        "id": len(collected_errors) + 1,
                        "sentence": sentence,
                        "aspect": term,
                        "gold_polarity": gold_polarity,
                        "predicted_polarity": pred_polarity,
                        "opinion_words": res.opinion_words,
                        "clause": clause,
                        "category": cat,
                        "reason": reason,
                    }
                )

    logger.info("Found %d total misclassified instances across test set.", len(collected_errors))
    logger.info("Category breakdown: %s", dict(category_counts))

    # Balance selection across categories to ensure comprehensive representation
    selected_errors: list[dict[str, Any]] = []
    categories = [
        "implicit aspect",
        "negation",
        "sarcasm",
        "multi-aspect clause",
        "comparison",
        "other",
    ]

    # Select representative samples per category
    for cat in categories:
        cat_matches = [e for e in collected_errors if e["category"] == cat]
        quota = max(8, target_count // len(categories))
        selected_errors.extend(cat_matches[:quota])

    # Fill remaining to reach target_count if needed
    if len(selected_errors) < target_count:
        remaining = [e for e in collected_errors if e not in selected_errors]
        selected_errors.extend(remaining[: (target_count - len(selected_errors))])

    # Ensure sequential IDs
    for idx, e in enumerate(selected_errors, 1):
        e["id"] = idx

    output_payload = {
        "benchmark": "error_analysis",
        "dataset": "SemEval-2014 Task 4 Test Split",
        "total_misclassifications_found": len(collected_errors),
        "total_examples_curated": len(selected_errors),
        "category_distribution": dict(Counter(e["category"] for e in selected_errors)),
        "examples": selected_errors,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "error_analysis.json"
    csv_path = results_dir / "error_analysis.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    logger.info("Saved JSON error analysis to %s", json_path)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "id",
            "aspect",
            "gold_polarity",
            "predicted_polarity",
            "category",
            "reason",
            "sentence",
            "opinion_words",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in selected_errors:
            writer.writerow(
                {
                    "id": e["id"],
                    "aspect": e["aspect"],
                    "gold_polarity": e["gold_polarity"],
                    "predicted_polarity": e["predicted_polarity"],
                    "category": e["category"],
                    "reason": e["reason"],
                    "sentence": e["sentence"],
                    "opinion_words": ", ".join(e["opinion_words"]),
                }
            )
    logger.info("Saved CSV error analysis (%d rows) to %s", len(selected_errors), csv_path)

    return output_payload


if __name__ == "__main__":
    results = run_error_analysis()
    print(f"\n=== Error Analysis ({results['total_examples_curated']} examples) ===")
    for cat, cnt in results["category_distribution"].items():
        print(f"  - {cat}: {cnt} examples")
